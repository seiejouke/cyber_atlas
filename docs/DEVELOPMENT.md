# Cyber Atlas developer guide

[Download and overview](../README.md) | [User guide](USER_GUIDE.md)

Run the commands below from the repository root.

## Development and release workflow

Implement ordinary changes and run the checks appropriate to each change.
Build installers and portable packages, bump the release version, or publish
an update only when the maintainer explicitly requests or approves that update.
This applies to Windows, Linux, macOS, and any future platform.
Several improvements can be collected into one release. Repository instructions
in [AGENTS.md](../AGENTS.md) record this workflow for coding agents.

## Run from source

Use a 64-bit CPython installation. This build was tested with **Python 3.12.3**
on Windows; the original build also ran on Python 3.13 on Linux.
You need Tkinter and a working graphical desktop/OpenGL driver.

This build uses **Tkinter for the interface and VTK for 3D rendering**. It does
not need PySide6, PyVista, a browser, JavaScript, a server, or an API key.
VTK is a substantial download; the source archive does not bundle its wheels.
After dependencies are installed, the app works offline.

Extract the archive, then open a terminal **inside the `cyber_atlas` folder**.

### Windows / PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

This does not activate a PowerShell script, so it does not require an
execution-policy change. Once setup is complete, `run.bat` starts the app.

### Linux / Arch / macOS

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python main.py
```

Once setup is complete, `sh run.sh` starts the app.

On Arch, missing Tk support can be installed with:

```bash
sudo pacman -S --needed tk
```

Check your Tk installation with `python3 -m tkinter`. It should open a test
window. On Sway/Wayland, Tk also needs a working XWayland display. A terminal-only
SSH session is not a graphical desktop.

If pip reports that no matching VTK wheel exists, check your Python version
and architecture. Use a supported 64-bit CPython build rather than changing
system packages or trying to compile VTK as a first step.

## The geometry

The OSI preset has **7 equal-height layers**; the design sets their count and
order. Each layer has an optional **center disk and
5 equal-width radial bands**. Each layer and radial position has **16 fixed
angular slots of 22.5 degrees**. A block saves its start slot and number of
slots; adding another block does not affect its mesh. The center radius and
each ring's radial thickness are 0.8 units,
so the center meets band 00 and neighboring bands share boundaries.

Equally sized blocks at the same layer and radial position have equal volumes.
Outer blocks have larger volumes because their circumference is longer,
while their radial thickness stays equal. Empty slots have no mesh or grid.
Blocks defaults to colored outlines, with only the selected volume filled.
Solid appearance restores the filled view. Outline edges take selection
priority over empty interiors; unrendered solid meshes keep interiors
selectable. Filters apply to both picking paths, and the selected solid still
occludes geometry behind it. Appearance is session state, outside atlas JSON.

The JSON saves each block's `slot` (0-15) and `span` (1, 2, 4, 8 or 16).
The UI displays start slots as 01-16. Geometry depends on these coordinates,
not on block count or node-list order. Occupancy checks include hidden blocks,
so filtering never allows accidental overlaps.

Nodes uses these same coordinates and occupancy rules, with a uniform sphere
at each note's position instead of its curved block mesh. Spheres do not grow
with saved block sizes. New nodes and moves use the editor's dropdowns and
sliders. Viewport clicks select saved nodes; **Move node** explicitly unlocks
their position controls. A full Center note sits on the layer axis.
Connections join neighbors on the same ring and nearest neighbors on the next
occupied ring, never across layers.

Protocols no longer reserve angular sectors. Choose a protocol, add your own
in Edit design, or use `Other` in the preset. Protocols can occur at different angles in
different rings. The old 595-coordinate limit no longer applies; files have
a 10,000-block limit and the existing 16 MiB size limit.

The map does not enforce a networking taxonomy. The example notes are learning
prompts, not a claim that every concept fits one exact OSI layer. In particular,
the TLS entry explicitly marks its layer placement as a learning convenience.

## Source map

```text
cyber_atlas/
  main.py                 Start the app; load or recover your atlas
  requirements.txt        Pinned rendering dependency
  run.bat / run.sh        Launchers after virtual-environment setup
  atlas/
    model.py              Design, stable references, notes, occupancy and migration
    design_editor.py      Layer/protocol editor, reassignment and label options
    design_draft.py       Temporary empty lists and pending block assignments
    geometry.py           Explicit slot/span -> closed curved meshes
    storage.py            JSON, atomic writes and a previous-version backup
    history.py            Compressed SQLite revisions, change summaries and save recovery
    history_ui.py         Separate read-only scene, revision browsing, restore and ZIP export
    flow.py               Manual branch traversal and world-space process curves
    flow_scene.py         Independent VTK process arrows and referenced orbital children
    flow_ui.py            Flow library, draft editor, study panel and view restoration
    study_text.py         Inert headings, emphasis, lists and stable concept links
    study_ui.py           Readable study text, concept search and shared-note editing
    scene.py              VTK rendering, camera and surface picking
    theme.py              Dark colors, widget styles and aligned position slider
    ui.py                 Window, editor and interaction handling
  examples/               Starter and empty atlases
  tests/                  Core tests and a real GUI smoke test
  docs/                   Preview, test results and references
```

Start reading with `model.py`, then `geometry.py`. Neither needs a GUI to be
understood or tested. `Scene` is independent of Tk widgets, so replacing the
rendering widget later does not require rewriting your data model or files.

VTK constructs and depth-renders actual meshes and ray-picks the nearest
visible surface. The prototype passes each rendered frame to Tk as an
in-memory image, avoiding platform-specific native-window embedding. Rendering
happens only when the view changes. Very large windows or dense atlases can
rotate more slowly because a frame must be copied to the GUI.

The standard note editor accepts Markdown **as text**. FlowNotes renders a small
study-text subset and manually authored concept references. Obsidian vault sync,
attachments, full-text global search, multi-note cells and multi-step undo are
not implemented. The flow picker searches concept names and locations.

## Tests and verification

Core tests, without a graphical desktop or VTK:

```bash
python -m unittest discover -s tests -v
```

GUI/rendering smoke test, with VTK installed and a graphical desktop:

```bash
python tests/smoke_ui.py
```

The current source includes **259 core tests** covering chosen angular
sizes, watertight center/ring meshes, equal radial spacing, stable neighboring
blocks, overlap rejection, gap reuse, design validation, stable references,
layer reassignment, optional protocols, shared node/block coordinates,
clearing and rebuilding lists, legacy migration and storage. The desktop smoke test exercises
the actual Tk controls, VTK rendering and picking, Center, Blocks placement,
Nodes creation, note editing and movement, deleting, protocol filtering,
design editing, view switching, JSON import/export and unsaved drafts. Movement
checks include cancellation that preserves text edits, hidden reservations,
save failures, Center transitions and the minimum window layout. Core tests
also cover error reporting without a console and safeguards for the packaged
self-test, release validation, verified downloads, safe update handoffs, orbital relationships
and revision history. The current source passes **259 core tests and 164 GUI
workflow checks** on Windows with Python 3.12.3, Tk 8.6 and VTK 9.6.2.
FlowNotes also passes 50 source runtime checks. It remains unpackaged; see
[FlowNotes source verification](flows-verification.json). These source counts
include flow validation, manual branches, shared-note updates, missing-reference
repair, schema-10 history compatibility, native rendering and view restoration.
Under Ubuntu, 110 tests covering flows, history, storage, clusters, information
and optional protocols pass. Its system Python lacks Tkinter, so the complete
Linux desktop suite has not been verified for this source change.
The published 0.9.3 packages pass 44 frozen runtime checks on Windows and 43 per
format on Linux. An isolated real 0.9.2-to-0.9.3 Windows update and four Debian
installer lifecycle checks also pass. See
[navigation release verification](navigation-verification.json).

The published 0.9.2 release passed 215 core tests and 132 GUI checks; its 25
history tests also passed under Ubuntu. Packaged applications passed 38 runtime checks on Windows and
37 per format on Linux. See the [history release verification](history-verification.json)
and the packaged runtime/installation reports in `docs/`.

The minimum window size is 1020 x 780. Source code and Windows packaging
configuration are included.

## Orientation compass

`atlas/orientation.py` defines the world-axis view conventions and an
orthonormal camera basis. Z is the layer axis. From +X, screen-right is +Y;
from +Y, screen-left is +X. From +Z, +X is right and +Y is up. The matching
bottom view keeps +Y upright. The scene uses this same basis for view-up and
panning, avoiding a singular view-up vector at either pole.

`atlas/compass_ui.py` supplies the shared Tk control for the main viewport and
the independent History scene. Axis tips animate the camera orientation with
the shortest yaw transition; clicking an active axis flips its sign. Home
restores only the default yaw/elevation. Zoom, target, atlas data and history
are outside the control. Manual input, external camera changes and window
closure cancel pending animation callbacks. The compass reserves label space
and keeps a fixed size and position through camera changes.

`tests/test_orientation.py` checks all six signed directions, screen-axis
conventions and orthonormal bases at and near both poles without Tk or VTK.
`tests/compass_view_checks.py`, included in the GUI smoke runner, compares real
VTK projections with the compass, clicks through both representations, checks
draft/file/history preservation, interrupts animations and checks the minimum
layout and independent History control. The compass, navigation panel and stable labels are included in version 0.9.3.
Earlier release-verification reports retain their original version numbers.

## Retractable navigation panel

`atlas/navigation_ui.py` embeds the main compass above a discrete layer slider
and supplies the edge tab that restores the panel when collapsed. Its reserved
label/picking region shrinks with the collapsed panel. Layer choices go through
the existing filter handler, which synchronizes the dropdown, keeps protocol
filtering and preserves drafts and the camera, including when filtering ends
cluster focus. The slider derives equal intervals from the current layer order;
single-layer designs avoid division by zero, while dense lists thin number
labels without removing stops or keyboard access.

`atlas/view_settings.py` atomically saves the collapsed preference in
`view-settings.json` in the application's settings directory. Reads fall back
to expanded for missing or malformed settings; writes preserve other preference
keys. A failed write leaves the panel usable for the session and reports that
the preference could not be remembered. No atlas/history write is involved.
History retains its separate compass and camera.

`tests/test_view_settings.py` covers persistence, invalid files and failed atomic
replacement. `tests/navigation_view_checks.py` is included in the desktop smoke
runner and exercises synchronization, mouse/keyboard input, dirty drafts,
protocol filtering, collapse/reopen, saved preferences, failed preference writes,
focused clusters and custom designs with one to 64 layers.

## Stable label placement

`atlas/label_layout.py` is a renderer-independent placement engine. It remembers
offsets relative to projected anchors, retains valid cached positions and gives
selection/hover priority over ordinary labels. A larger search includes nearby
offsets, wider columns and edge callouts. Controls and each label's own node
remain protected; priority callouts may displace softer decorations. Sparse
views use the available canvas, while crowded views report omitted labels.

`atlas/label_ui.py` supplies one layout for main notes and expanded suborbitals.
Camera movement retains cached visibility/offsets; a short debounce schedules
collision resolution after motion stops. Small offset changes transition over
120 ms when the path stays clear of UI reservations. Mouse presses pause label
transitions to keep clicks predictable. Hit boxes follow displayed label boxes,
and window closure cancels pending settle/animation callbacks. Cache entries
are pruned when concepts disappear; offsets never enter atlas JSON or history.

In Nodes view, `Scene.label_visible` samples the projected rim if the centre
pixel is covered, including for orbital children. Fully covered spheres remain
unlabelled unless selection/hover requests a priority callout. Blocks retains
its surface/outline visibility rules. Parent indicators use the same sphere
visibility check.

`tests/test_label_layout.py` covers stable offsets, camera motion, sparse and
crowded placement, priorities, reservations, bounds and pruning without Tk/VTK.
`tests/label_view_checks.py` uses the real renderer for the four-node physical
layer, constant-offset pan, partial/full sphere and child occlusion, shared
suborbital placement, crowded minimum layouts and read-only label clicks.

## FlowNotes architecture (current source)

Format 11 adds immutable `FlowNote`, `FlowStep` and `FlowConnection` records to
`Atlas`. Steps reference stable node/subconcept IDs; their saved concept names
are fallback labels for deleted references. Repeated concepts have distinct
step IDs. End-flow edges have a null target. Each branch has a unique nonempty
label. Limits are 256 flows, 256 steps per flow and 1,024 connections per flow,
within the existing 16 MiB document limit. Missing concept references remain
loadable and repairable. Invalid endpoints, duplicate IDs/edges, malformed text
and ambiguous branch labels are rejected before a save.

`flow.FlowRun` follows only explicit outgoing edges and retains a visit trail
for Previous, including terminal choices and manual loops. Jumping starts a new
trail. `flow_scene.FlowScene` draws trimmed world-space curves and cone heads
using independent non-pickable VTK actors, caches the overlay between scene
changes, and supplies referenced child spheres for multiple parent orbits.
Neither adjacency nor `information_heat` reads flow references. Node coordinates
and heat fill colours are unchanged; dimming is temporary actor opacity.

`flow_ui.FlowManager` maintains a validated draft outside the active document.
It supports concept search, step reordering and relinking, labelled connections,
branch selection and explicit save. Reader traversal and camera/filter operations
never commit data. The original inspector draft stays intact. Exit restores
the camera, representation, filters and orbital focus. Canonical note editing
uses the same atomic save/history path as ordinary notes and refreshes all
occurrences. Save failure retains the draft; conflicting unsaved inspector
notes must be finished before editing that same shared concept.

`study_text` parses a bounded, inert subset: headings, lists, bold, italic,
inline code and `[label](concept:percent-encoded-id)` links. `StudyText` renders
Tk tags without HTML, a browser engine, external navigation or script execution.
Flow labels use the shared placement engine with a separate temporary cache;
ordinary atlas label offsets remain available when the flow closes.

Design edits and protocol clearing retain flows. Deleting a concept retains
its flow steps with missing-reference markers. Atomic JSON saves, exports,
backups and complete history snapshots include flows; change summaries identify
flow edits. History's independent viewer lists and reads saved flows. History
reconciliation compares decoded content across supported schema versions, so
loading a format-10 snapshot under format 11 does not create a false revision
or rewrite its recorded timestamp or hash.

`tests/test_flows.py` covers the data model, storage/history, old files, traversal
and text parsing; `tests/flow_view_checks.py` adds 16 real Tk/VTK workflows to
the full smoke runner. `self_test.py` covers flow editing, native rendering,
branches and canonical notes using the runtime that executes it. No package
was built for this change. To refresh real source screenshots and the example:

```bash
python tools/capture_flows.py --example examples/packet_flow_atlas.json --output build/flows-previews
```

## Orbital cluster architecture

Schema 9 retains the existing `nodes` grid and adds a separate `subconcepts`
list. `Subconcept` stores its stable ID, grid parent ID, name, notes, local slot
(0–7), and `type_of` relationship. Atlas validation rejects orphan parents,
nested clusters, duplicate concept IDs and occupied local slots. The total
limit of 10,000 concepts and 16 MiB file limit include children. Versions 1–8
migrate without moving existing grid nodes; first save keeps the original backup.

`geometry.orbit_position` places children at stable offsets in their parent's
horizontal plane. `orbit_scene.OrbitScene` adds independent actors, spokes,
ring, picking, filter inheritance and reversible focus to the existing renderer.
`cluster_ui.ClusterManager` owns the child editor, list, preview and consent
flow. The ordinary selected grid node remains the parent; child edits do not
reuse or overwrite its text fields. Design reassignment and protocol removal
preserve the child collection. Parent deletion requires explicit cluster deletion.

The first release has one local ring, eight slots and one expanded cluster.
Focus hides unrelated geometry without moving saved nodes; Show atlas restores
the camera. Blocks keeps the root mesh and exposes the child list. No source
integration, information scaling, mastery scores or nested orbits are inferred.

Run `python tools/capture_clusters.py` on a graphical desktop to refresh the real
cluster screenshots from an isolated example atlas.

## Spatial connections

`geometry.adjacent_node_pairs` indexes the saved footprints by layer, band and
occupied slot. Two nodes connect only across a shared angular edge or across
overlapping slots on consecutive bands. Empty cells, corner contact and other
layers cannot create edges. The index runs in proportion to occupied cells.

`Scene` computes pairs before applying visibility filters, includes valid draft
positions, and exposes the visible spatial pairs as `connection_pairs`.
Layer markers never create automatic spokes. The central spine is a reference
guide; explicit parent–subconcept relationships remain in `Atlas.subconcepts`
and are rendered separately. Spatial pairs and guides do not establish semantic
relationships or information counts. Heat uses explicit entries and
parent–subconcept data, as described below.

## Recorded information and heat

Schema 10 stores `InformationEntry` records separately from `Node.notes` and
`Subconcept.notes`. Entries have an immutable concept owner, stable ID, title
and nonempty body. Atlas validation rejects missing owners, duplicate IDs and
identical entries within a concept. Deleting concepts cascades through their
owned records; design reassignment preserves them. Versions 1–9 load without
inventing entries or changing existing notes. Normal atomic saves retain the
previous file as the backup.

The heat model gives each saved concept one main-note item automatically,
then adds its additional records and each direct child's own count. Exact
main-note text copies stay saved but do not
double-count the main note. Spatial adjacency and reference guides are not
inputs. Numeric totals have no heat ceiling; only the color saturates.

`heat_color` uses saturated blue, cyan, yellow, orange and red anchors, with
no white or green. Shades interpolate within these bands; cyan switches
directly to yellow to avoid introducing an unrequested color. Counts remain
equally spaced. Presets rescale that same
palette to 9, 16 or 32, with Balanced 16 as the initial choice. `Scene` caches
metrics on document changes independently
of filtering. Overview and focus both use total-information fills.

The Tk overlay draws neutral parent rings and count badges before labels.
They persist when collapsed and do not affect VTK geometry, spatial topology
or heat. Visibility checks suppress filtered and occluded indicators; badge
clicks select their parent. Selection uses corner marks instead of a ring.

`information_ui.InformationManager` provides a modal entry editor, independent
draft handling, inspector counts, palette controls and legend. Entry commits
preserve dirty main-note fields. Color and range settings last for the session.
Blocks continues to use layer colors and the original meshes.

Run `python tools/capture_information.py --main-notes` on a graphical desktop
to generate the 84-concept main-note example and capture both application
views. Add `--example-only` to write the example without opening a GUI.
The default invocation still captures the earlier recorded-entry example.
Core and GUI checks cover automatic counts, saved-copy compatibility, exact
totals, green-free gradual colors, every equally spaced tick, all three presets,
ring persistence and removal, filtering, failed saves, export/import and minimum
windows. Runtime self-checks also cover main notes, the default linear scale
and collapsed-parent rings. Version 0.9.2 includes these improvements and
saved-state history in Windows and Linux packages. Windows passed 38 bundled
runtime checks; Linux passed 37 per format. An isolated real 0.9.1-to-0.9.2
Windows update passed seven lifecycle checks, preserving the atlas byte for
byte and recording the current state and valid previous backup in history.

## Saved-state history architecture

`history.HistoryStore` stores compressed, complete JSON snapshots (format 11
in current source; format 10 in published 0.9.3) in
an adjacent `.history.sqlite3` database. History schema 1 has a stable atlas ID,
UUID revision IDs, increasing sequence numbers, parent links, UTC recording
times, application/data-format versions, content hashes and structured changes
with affected entity/concept IDs. Snapshot loading bounds decompression and
checks hashes before model validation. Existing atlas JSON needs no migration.

`AtlasApp._commit` routes content saves through the recorder, including the
cluster, entry and design editors. Exports and session view changes bypass it.
Identical content is a no-op. A changed save commits a hidden pending snapshot,
uses the existing atomic JSON writer, then confirms the revision. Startup and
History opening reconcile pending content against the authoritative JSON:
completed replacements are confirmed; failed replacements are discarded.
History preparation failure prevents the JSON write; a failure confirming an
already saved atlas returns success with a recovery warning. Saves reject a
stale document when a different atlas state is found on disk.

Initial recording observes the current state and, if valid and different, the
previous backup without claiming original save/creation dates. Later changes
from older applications become observed external revisions. Revision order
uses sequence numbers rather than wall-clock sorting. Keep the existing
one-window-per-atlas restriction; this is not a multi-writer transaction system.

`history_ui.HistoryManager` renders a separate VTK scene in a modal browser.
It never replaces the active in-memory document for preview. Navigation,
inspection and heat/view controls are read-only, with a fixed inherited heat
range. Restoration calls the ordinary save pipeline with a restore milestone.
ZIP export reads a consistent history transaction and writes each state as
portable JSON with a lineage/timestamp manifest. A temporary archive protects
an existing export from write failure. Whole-history import and automated
timeline playback are deferred; neither is required to begin recording now.

On Windows, run `python tools/capture_history.py` for an actual browser screenshot with
disposable example data. The focused checks are in `tests/history_view_checks.py`
and run as part of `tests/smoke_ui.py`; core crash/recovery coverage is in
`tests/test_history.py`. No history retention policy silently removes revisions.

## Update distribution

`atlas/updates.py` reads the public GitHub latest-release endpoint without
credentials. Checks accept stable versions from this repository, select the
matching platform asset, require its size and SHA-256 digest, and restrict
download redirects to HTTPS GitHub release hosts. Downloads are staged and
verified before replacing the cached file. Network work runs on daemon threads;
Tk receives results through a queue. Defaults, settings and timestamps are
stored in `updates.json` beside the normal application data, outside atlas JSON.

The Windows helper is bundled as `atlas/update_helper.ps1`, copied outside the
installation, and started hidden after the user chooses Restart and update.
A readiness handshake prevents the app from closing if the helper cannot start.
It waits for the parent, refuses to close other application instances, rechecks
the installer hash, applies the installer to the existing folder, and restarts
the same executable with the original `--file` path. A failed handoff or installer
leaves a result report and installation log under the update cache.

AppImages stage the replacement beside the current image, preserve a previous
copy, and restore it if starting the replacement fails. Debian packages use
the system software installer. Portable Windows and source copies use the
release page. Automatic checks are opt-in and limited to once per day; no
automatic downloads or installations run.

After a Windows build, test the real upgrade helper without replacing an
existing user installation:

```powershell
.\.venv\Scripts\python.exe tools\test_windows_updater.py --previous-zip dist\CyberAtlas-0.9.1-windows-x64.zip
```

This compiles isolated installers with a separate AppId, upgrades the old binary,
checks the parent wait and restart, and verifies that the saved atlas and actual
application registration remain unchanged. It requires Inno Setup and the old ZIP.

## Build the Windows release

On Windows x64, use the project virtual environment and install the build tools:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe tools\build_windows.py
```

The build needs Inno Setup 6/7. It finds `ISCC.exe` on PATH, in its normal
installation folder, or in `build/tools/InnoSetup/`. You can pass
`--iscc "C:\path\to\ISCC.exe"`, or use `--skip-installer` to build only the
application folder and ZIP.

The script runs the core tests, generates the icon and executable version
information, bundles the runtime, includes third-party license notices, and
tests the actual executable with Python and Tcl/Tk environment overrides removed.
It checks native rendering and picking, saving, moving, cancellation, templates,
backups and the minimum window layout. The test uses a fresh temporary atlas.
The installer is also checked by installing to a temporary folder, running the
installed executable, upgrading it and uninstalling it while preserving saved
test data. An existing Cyber Atlas installation is left in place and this
installer check is skipped.

Outputs in `dist/`:

- `CyberAtlas/`: application folder containing `CyberAtlas.exe` and its runtime.
- `CyberAtlas-0.9.3-windows-x64.zip`: complete folder for ZIP distribution.
- `CyberAtlas-0.9.3-Setup.exe`: installer for the current Windows account.
- `SHA256SUMS.txt`: hashes for the distributable files.
- `packaged-test-results.json`: results from the bundled executable.
- `installed-test-results.json`: results from running the installed executable.
- `installer-test-results.json`: installation, upgrade and removal checks.

Application logs are written to `logs/cyber-atlas.log` beside the active atlas
file. For the default atlas this is `%LOCALAPPDATA%\CyberAtlas\logs`.
Logs rotate and startup failures also display a dialog in the windowed build.
The build does not sign or publish the application.

## Build the Linux release

The **Build Linux packages** GitHub Actions workflow builds on Ubuntu 22.04
x86_64 with Python 3.12.3. After an update is approved for packaging, start it
manually from the Actions tab using **Run workflow**. Code pushes do not start
package builds.
The build uses pinned actions and verifies downloaded AppImage tool hashes.

For a local build, install the dependencies listed in
[linux-release.yml](../.github/workflows/linux-release.yml), then run:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-build.txt
xvfb-run -a -s "-screen 0 1440x1000x24" .venv/bin/python tools/build_linux.py
```

The packages include Python, Tk and VTK, a desktop icon, and third-party
notices. The Debian package installs under `/opt/cyber-atlas` with a
`/usr/bin/cyber-atlas` launcher. The AppImage is portable. Both use the existing
per-user atlas path, outside the application directory.

The build checks the frozen executable and the AppImage through their own
bundled runtime. The workflow adds `--test-install` to install, upgrade and
purge the Debian package on the disposable runner while checking saved data.
This option requires passwordless sudo and refuses to replace an existing
Cyber Atlas installation. A normal local build does not install the package.

Outputs and reports are in `dist/linux/`:

- `cyber-atlas_0.9.3_amd64.deb`
- `CyberAtlas-0.9.3-x86_64.AppImage`
- `SHA256SUMS-linux.txt`
- `linux-build-report.json` and runtime/installation test reports

Linux releases require glibc 2.35 or newer and host OpenGL/C++ libraries.
The workflow uses Xvfb and Mesa software rendering. Packages are uploaded as
workflow artifacts; publishing them to a GitHub release is a separate step
after checking those artifacts.

## References

Official library documentation and package references are recorded in
[REFERENCES.md](REFERENCES.md).

## Refresh the README screenshots

Capture the actual Nodes and Blocks interface without running the workflow suite:

```powershell
.\.venv\Scripts\python.exe tests\smoke_ui.py --screenshots-only --nodes-preview docs\nodes-preview.png --preview docs\preview.png
```

This needs a graphical desktop and Pillow. Each capture uses example data in a temporary
atlas and leaves your saved notes untouched.
