# Cyber Atlas developer guide

[Download and overview](../README.md) | [User guide](USER_GUIDE.md)

Run the commands below from the repository root.

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

Notes accept Markdown **as text**. Markdown preview, Obsidian vault sync,
links between blocks, attachments, global search, multi-note cells and
multi-step undo are not implemented in this version.

## Tests and verification

Core tests, without a graphical desktop or VTK:

```bash
python -m unittest discover -s tests -v
```

GUI/rendering smoke test, with VTK installed and a graphical desktop:

```bash
python tests/smoke_ui.py
```

The desktop build includes **152 core tests** covering chosen angular
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
self-test, release validation, verified downloads, safe update handoffs, and orbital relationships. All **152 core tests and 102 GUI workflow checks passed** on Windows with Python
3.12.3, Tk 8.6 and VTK 9.6.2. Test outputs are in `docs/`.

The minimum window size is 1020 x 780. Source code and Windows packaging
configuration are included.

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
relationships or information counts. No heat calculation is implemented.

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
.\.venv\Scripts\python.exe tools\test_windows_updater.py --previous-zip dist\CyberAtlas-0.8.0-windows-x64.zip
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
- `CyberAtlas-0.8.1-windows-x64.zip`: complete folder for ZIP distribution.
- `CyberAtlas-0.8.1-Setup.exe`: installer for the current Windows account.
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
x86_64 with Python 3.12.3. It runs automatically when the application or Linux
packaging changes, and can also be started manually from the Actions tab.
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

- `cyber-atlas_0.8.1_amd64.deb`
- `CyberAtlas-0.8.1-x86_64.AppImage`
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
