"""Capture the actual read-only history browser using disposable example data."""
from dataclasses import replace
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time
import tkinter as tk

from PIL import ImageGrab

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from atlas.model import InformationEntry, Subconcept, example_atlas
from atlas.storage import write_atlas
from atlas.ui import AtlasApp


def main():
    if sys.platform != "win32":
        raise SystemExit("This screenshot tool currently requires Windows window-only capture.")
    with TemporaryDirectory(prefix="cyber-atlas-history-preview-") as folder:
        path = Path(folder) / "atlas.json"
        document = example_atlas()
        write_atlas(path, document, backup=False)
        root = tk.Tk()
        app = AtlasApp(root, path, document, settings_directory=path.parent, automatic_updates=False)
        try:
            parent = document.nodes[5]
            document = document.with_node(replace(parent, name="TCP", notes="TCP provides a reliable, ordered byte stream.\n\nThis revision records my original explanation before adding packet-capture observations."))
            document = document.with_child(Subconcept("history-handshake", parent.id, "Three-way handshake", "SYN → SYN/ACK → ACK establishes the connection.\n\nBoth endpoints agree initial sequence numbers.", 0))
            document = document.with_child(Subconcept("history-flow", parent.id, "Flow control", "The advertised receive window limits how much data can be in flight for this receiver.", 3))
            app._commit(document, summary="Added TCP explanations and two suborbitals")
            for index, (title, body) in enumerate((("Sequence numbers", "Bytes are numbered for ordered delivery."), ("Acknowledgements", "ACK identifies the next expected byte."), ("Retransmission", "Lost data is sent again."))):
                document = document.with_entry(InformationEntry(f"capture-{index}", parent.id, title, body))
                app._commit(document)
            earlier = app.history.store.revisions()[0]
            document = document.with_node(replace(document.get(parent.id), notes="Updated explanation after a packet-capture exercise.\n\nI can now identify sequence numbers, acknowledgements and retransmissions."))
            app._commit(document, summary="Updated TCP notes after a packet capture")
            document = document.without_child("history-flow")
            app._commit(document, summary="Removed Flow control from the current atlas")
            app._load_editor(document.get(parent.id))
            app.set_view_mode("nodes")
            app.information.color_mode.set("Information heat")
            app.information.change_color()
            app.history.open()
            app.history.dialog.geometry("1300x820+35+35")
            app.history.tree.selection_set(earlier.id)
            app.history.show_revision(earlier.id)
            app.history.selected_id = parent.id
            index = next(i for i, concept in enumerate(app.history.concepts) if concept.id == parent.id)
            app.history.concept_list.selection_clear(0, "end")
            app.history.concept_list.selection_set(index)
            app.history._selected_concept()
            for _ in range(12):
                root.update()
                time.sleep(.03)
            window = app.history.dialog
            destination = ROOT / "docs/history-browser.png"
            # Capture only this window, even when another application is in front.
            ImageGrab.grab(window=window.winfo_id()).save(destination)
            print("Captured actual history browser with disposable example revisions.")
        finally:
            app.shutdown()


if __name__ == "__main__":
    main()
