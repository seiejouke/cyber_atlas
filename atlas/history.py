"""Local, recoverable revision snapshots; independent of the portable atlas format."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
from uuid import uuid4
import zipfile
import zlib

from . import __version__
from .model import Atlas, AtlasError, VERSION
from .storage import MAX_FILE_BYTES, read_atlas, write_atlas


class HistoryError(AtlasError):
    """History cannot be read or safely extended."""


def _content(atlas: Atlas) -> bytes:
    content = json.dumps(atlas.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(content) > MAX_FILE_BYTES:
        raise HistoryError("The atlas is too large to record in history.")
    return content


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def describe_changes(before: Atlas, after: Atlas) -> list[dict]:
    """Describe saved differences by stable IDs; snapshots retain the actual values."""
    changes = []
    groups = (("node", before.nodes, after.nodes), ("subconcept", before.subconcepts, after.subconcepts),
              ("entry", before.information_entries, after.information_entries),
              ("layer", before.design.layers, after.design.layers), ("protocol", before.design.protocols, after.design.protocols))
    for entity, old_items, new_items in groups:
        old = {item.id: item for item in old_items}
        new = {item.id: item for item in new_items}
        for identity in sorted(old.keys() | new.keys(), key=lambda key: (type(key).__name__, str(key))):
            previous, current = old.get(identity), new.get(identity)
            if previous == current:
                continue
            item = current or previous
            if previous is None:
                action, fields = "added", []
            elif current is None:
                action, fields = "deleted", []
            else:
                fields = [name for name in item.__dataclass_fields__ if getattr(previous, name) != getattr(current, name)]
                positions = {"layer", "depth", "slot", "span", "orbit_slot", "parent_id"}
                action = "moved" if set(fields) <= positions else "edited"
            changes.append({"entity": entity, "id": identity, "name": getattr(item, "name", getattr(item, "title", "")),
                            "action": action, "fields": fields,
                            "concept_id": getattr(item, "concept_id", item.id if entity in ("node", "subconcept") else None),
                            "parent_id": getattr(item, "parent_id", None)})
    captions = [field for field in ("layer_caption", "protocol_caption", "label_mode")
                if getattr(before.design, field) != getattr(after.design, field)]
    if captions or before.design.layers != after.design.layers or before.design.protocols != after.design.protocols:
        # Explicitly retain list reordering, even when all named entries are unchanged.
        changes.append({"entity": "design", "id": "design", "name": "Atlas design", "action": "edited",
                        "fields": captions + (["layer order"] if tuple(x.id for x in before.design.layers) != tuple(x.id for x in after.design.layers) else [])
                        + (["protocol order"] if tuple(x.id for x in before.design.protocols) != tuple(x.id for x in after.design.protocols) else [])})
    return changes


def _summary(changes: list[dict]) -> str:
    if len(changes) == 1:
        change = changes[0]
        return f"{change['action'].capitalize()} {change['entity']}: {change['name']}"
    counts = {}
    for change in changes:
        counts[change["action"]] = counts.get(change["action"], 0) + 1
    return ", ".join(f"{action.capitalize()} {count}" for action, count in counts.items()) or "Saved atlas"


@dataclass(frozen=True)
class Revision:
    sequence: int
    id: str
    parent_id: str | None
    recorded_at: str
    kind: str
    summary: str
    app_version: str
    format_version: int
    content_hash: str
    changes: tuple[dict, ...]


@dataclass(frozen=True)
class SaveResult:
    changed: bool
    warning: str | None = None


class HistoryStore:
    def __init__(self, atlas_path: Path):
        self.atlas_path = Path(atlas_path)
        self.path = self.atlas_path.with_name(self.atlas_path.name + ".history.sqlite3")

    @contextmanager
    def _connect(self):
        connection = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.path, timeout=5)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA trusted_schema=OFF")
            connection.execute("PRAGMA synchronous=FULL")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise HistoryError("This history file requires a newer Cyber Atlas. Your atlas has not been changed.")
            if version == 0:
                with connection:
                    connection.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
                    connection.execute("""CREATE TABLE IF NOT EXISTS revisions (
                        sequence INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE, parent_id TEXT,
                        recorded_at TEXT NOT NULL, kind TEXT NOT NULL, summary TEXT NOT NULL,
                        app_version TEXT NOT NULL, format_version INTEGER NOT NULL,
                        content_hash TEXT NOT NULL, snapshot BLOB NOT NULL, changes TEXT NOT NULL,
                        state TEXT NOT NULL CHECK(state IN ('pending', 'committed')))""")
                    connection.execute("INSERT OR IGNORE INTO metadata VALUES ('atlas_id', ?)", (uuid4().hex,))
                    connection.execute("PRAGMA user_version=1")
            yield connection
        except sqlite3.Error as exc:
            raise HistoryError(f"Could not access atlas history: {exc}. The history file was preserved.") from exc
        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def _revision(row) -> Revision:
        try:
            changes = json.loads(row["changes"])
            if not isinstance(changes, list) or datetime.fromisoformat(row["recorded_at"]).tzinfo is None:
                raise ValueError("Invalid revision metadata")
            for change in changes:
                if (not isinstance(change, dict)
                        or not all(isinstance(change[key], str) for key in ("entity", "name", "action"))
                        or not isinstance(change["fields"], list)
                        or not all(isinstance(field, str) for field in change["fields"])):
                    raise ValueError("Invalid change summary")
            return Revision(*(row[key] for key in ("sequence", "id", "parent_id", "recorded_at", "kind", "summary",
                                                    "app_version", "format_version", "content_hash")), tuple(changes))
        except (ValueError, TypeError, KeyError, RecursionError) as exc:
            raise HistoryError("Revision metadata is damaged. The atlas and history file were preserved.") from exc

    @staticmethod
    def _decode(row) -> Atlas:
        try:
            decoder = zlib.decompressobj()
            content = decoder.decompress(row["snapshot"], MAX_FILE_BYTES + 1)
            if len(content) > MAX_FILE_BYTES or not decoder.eof or decoder.unused_data or _digest(content) != row["content_hash"]:
                raise ValueError("Snapshot integrity check failed")
            return Atlas.from_dict(json.loads(content))
        except (ValueError, TypeError, KeyError, zlib.error, UnicodeError, RecursionError) as exc:
            raise HistoryError("This saved revision is damaged or unsupported. Other revisions and the active atlas were preserved.") from exc

    @staticmethod
    def _head(connection):
        return connection.execute("SELECT * FROM revisions WHERE state='committed' ORDER BY sequence DESC LIMIT 1").fetchone()

    def _insert(self, connection, atlas, kind, summary=None, *, state="committed", before=None):
        head = self._head(connection)
        content = _content(atlas)
        changes = describe_changes(before if before is not None else (self._decode(head) if head else Atlas()), atlas)
        identity = uuid4().hex
        connection.execute("""INSERT INTO revisions
            (id,parent_id,recorded_at,kind,summary,app_version,format_version,content_hash,snapshot,changes,state)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (identity, head["id"] if head else None, datetime.now(timezone.utc).isoformat(timespec="microseconds"),
             kind, summary or _summary(changes), __version__, VERSION, _digest(content), zlib.compress(content),
             json.dumps(changes, ensure_ascii=False), state))
        return identity

    def _reconcile(self, connection, current: Atlas):
        digest = _digest(_content(current))
        pending = connection.execute("SELECT * FROM revisions WHERE state='pending' ORDER BY sequence").fetchall()
        if len(pending) > 1:
            raise HistoryError("Multiple unfinished saves need recovery. No history was overwritten.")
        if pending:
            row = pending[0]
            if row["content_hash"] == digest:
                connection.execute("UPDATE revisions SET state='committed' WHERE id=?", (row["id"],))
            else:
                connection.execute("DELETE FROM revisions WHERE id=?", (row["id"],))
        head = self._head(connection)
        if head is None:
            # Existing content is observed now; never invent original creation dates.
            previous = current
            backup = self.atlas_path.with_suffix(self.atlas_path.suffix + ".bak")
            try:
                previous = read_atlas(backup) if backup.exists() else current
            except (OSError, AtlasError):
                pass  # An unreadable old backup cannot prevent a valid baseline.
            if previous != current:
                self._insert(connection, previous, "backup", "Recovered previous backup; its original save date is unknown", before=previous)
            self._insert(connection, current, "baseline", "History recording began; existing concepts have unknown creation dates", before=previous)
        elif head["content_hash"] != digest:
            self._insert(connection, current, "external", "Observed atlas changes made outside this history")

    def initialize(self, current: Atlas):
        if self.atlas_path.exists():
            current = read_atlas(self.atlas_path)
        with self._connect() as connection, connection:
            self._reconcile(connection, current)

    def revisions(self) -> list[Revision]:
        with self._connect() as connection:
            return [self._revision(row) for row in connection.execute(
                "SELECT sequence,id,parent_id,recorded_at,kind,summary,app_version,format_version,content_hash,changes "
                "FROM revisions WHERE state='committed' ORDER BY sequence DESC")]

    def load(self, revision_id: str) -> Atlas:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM revisions WHERE id=? AND state='committed'", (revision_id,)).fetchone()
            if row is None:
                raise HistoryError("That revision could not be found.")
            return self._decode(row)

    def save(self, document: Atlas, *, expected: Atlas | None = None, kind="save", summary=None, writer=None) -> SaveResult:
        """Durably prepare history, atomically save JSON, then confirm the revision.

        A prepared revision is hidden until committed. Startup reconciles an
        interrupted save against the actual JSON content. The JSON stays authoritative.
        """
        writer = writer or write_atlas
        _content(document)
        current = read_atlas(self.atlas_path) if self.atlas_path.exists() else (expected or document)
        if expected is not None and current != expected:
            raise HistoryError("The atlas changed on disk. Reopen it before saving so those changes are preserved.")
        with self._connect() as connection, connection:
            self._reconcile(connection, current)
            if document == current:
                if not self.atlas_path.exists():
                    writer(self.atlas_path, document)
                return SaveResult(False)
            identity = self._insert(connection, document, kind, summary, state="pending", before=current)
        try:
            writer(self.atlas_path, document)
        except (OSError, AtlasError):
            # A failure before replacement must never appear as a saved revision.
            if self.atlas_path.exists() and read_atlas(self.atlas_path) == document:
                try:
                    self._finish(identity)
                except (OSError, HistoryError):
                    pass  # The durable pending record can be finalized after reopening.
                return SaveResult(True, "The atlas was saved; its interrupted history save will be reconciled when reopened.")
            try:
                with self._connect() as connection, connection:
                    connection.execute("DELETE FROM revisions WHERE id=? AND state='pending'", (identity,))
            except (OSError, HistoryError):
                pass  # Recovery will discard the pending record if JSON was not saved.
            raise
        try:
            self._finish(identity)
        except (OSError, HistoryError):
            return SaveResult(True, "Your atlas was saved. Its history revision is pending recovery; reopen History to finish recording it.")
        return SaveResult(True)

    def _finish(self, identity):
        with self._connect() as connection, connection:
            connection.execute("UPDATE revisions SET state='committed' WHERE id=?", (identity,))

    def export(self, destination: Path):
        """Export a consistent, self-contained ZIP of JSON states and revision metadata."""
        destination = Path(destination)
        protected = {self.atlas_path.resolve(), self.path.resolve(), self.atlas_path.with_suffix(self.atlas_path.suffix + ".bak").resolve()}
        protected.update(self.path.with_name(self.path.name + suffix).resolve() for suffix in ("-journal", "-wal", "-shm"))
        if destination.resolve() in protected:
            raise HistoryError("Choose a separate ZIP file; the atlas and history files cannot be replaced by an export.")
        current = read_atlas(self.atlas_path)
        self.initialize(current)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".history-export-", suffix=".zip", delete=False) as handle:
            temporary = Path(handle.name)
        try:
            with self._connect() as connection, connection, zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                connection.execute("BEGIN")
                head = self._head(connection)
                if head is None or self._decode(head) != current:
                    raise HistoryError("The atlas changed during export. Try again after saving.")
                manifest = {"type": "cyber-atlas-history", "version": 1,
                            "atlas_id": connection.execute("SELECT value FROM metadata WHERE key='atlas_id'").fetchone()[0], "revisions": []}
                archive.writestr("atlas.json", json.dumps(current.to_dict(), ensure_ascii=False, indent=2))
                for row in connection.execute("SELECT * FROM revisions WHERE state='committed' ORDER BY sequence"):
                    revision = self._revision(row)
                    filename = f"revisions/{revision.sequence:08d}.json"
                    archive.writestr(filename, json.dumps(self._decode(row).to_dict(), ensure_ascii=False))
                    manifest["revisions"].append({**revision.__dict__, "file": filename})
                archive.writestr("history.json", json.dumps(manifest, ensure_ascii=False, indent=2))
                archive.writestr("README.txt", "Cyber Atlas history export\n\natlas.json is the current portable atlas.\nEach revisions/*.json file is independently importable through Import JSON.\nhistory.json retains revision order, UTC recording times, change summaries and IDs.\nImporting one state creates a new saved revision in the destination atlas.\n")
            # Preserve a previous export if any step above failed.
            import os
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)

    @property
    def size_bytes(self):
        return self.path.stat().st_size if self.path.exists() else 0
