# Cyber Atlas

A local Python desktop notebook built around your Munsell-inspired design.

**Height = OSI layer. Angle = protocol. Radius = service/detail band.**
Only occupied coordinates become solid volumes. Nothing shifts when another
note is added, and no empty cell grid is drawn.

![The running Python prototype](docs/preview.png)

## Start here

Use a 64-bit CPython installation, preferably **Python 3.13** (the tested
version). Python 3.11-3.14 is the recommended range for this pinned build.
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

## First use

The first launch creates a local atlas containing the 14 starter notes from
the HTML concept. Select a volume to edit its title, coordinates, and notes.

**New -> choose layer, protocol and band -> write your note -> Save node.**

Saving allocates one solid wedge at that coordinate. Deleting its last/only
note removes the wedge. The other volumes stay in place. A coordinate can
hold one note in this prototype; an attempted collision is rejected rather
than overlapping or replacing another note.

Use the layer dropdown to isolate an OSI layer. The Labels checkbox controls
annotations, not the volumes themselves. Labels that would overlap or belong
to obscured surfaces are omitted to keep the view readable. The selected note
is prioritized. You can still rotate the map, filter a layer, or use Tab to
reach a note whose label is hidden.

The layer filter affects only the view. It does not delete data or change the
note in the editor. Saving a note outside the active filter resets the view
to all layers so the saved volume is visible.

## Controls

| Action | Control |
| --- | --- |
| Rotate the atlas | Left-button drag |
| Pan | Shift + drag, or middle-button drag |
| Zoom | Mouse wheel; `+` / `-` with viewport focused |
| Select a volume | Click a visible surface or label |
| Reset the camera | Reset view, or `R` in the viewport |
| Rotate using keys | Arrow keys in the viewport |
| Next / previous visible note | Tab / Shift + Tab in the viewport |
| Move from viewport to editor | Enter |
| Select a radial band | Click or drag its slider; left/right keys when focused |
| Save node | Ctrl + S |
| New node | Ctrl + N |
| Import JSON | Ctrl + O |
| Export JSON | Ctrl + Shift + S |

## Saving and recovery

**Save node immediately writes the atlas to disk.** Deletions and successful
imports are also saved immediately. Text still being typed is a draft: it is
not saved on every keystroke. Before selecting another note, creating a new
one, importing, or closing, the app asks whether to save a changed draft.

Default data locations:

| System | File |
| --- | --- |
| Windows | `%LOCALAPPDATA%\CyberAtlas\atlas.json` |
| Linux | `~/.local/share/CyberAtlas/atlas.json` (or under `$XDG_DATA_HOME`) |
| macOS | `~/Library/Application Support/CyberAtlas/atlas.json` |

Writes use a temporary file and atomic replacement. The previous valid
version is retained as `atlas.json.bak`. If the active atlas becomes unreadable
and a valid backup exists, startup offers recovery and preserves the unreadable
original as a timestamped `.broken-...` file.

This backup is **one previous version**, not unlimited undo or a separate
backup strategy. Export named JSON copies for milestones. Use only one app
window per atlas; this is not a concurrent multi-user editor.

The JSON is readable plaintext, not encrypted storage. Do not put passwords,
recovery codes, or other secrets in these notes.

### Portable files and the original HTML prototype

Export JSON saves a complete portable copy. Import JSON **replaces** the active
atlas after confirmation; it does not merge atlases. Malformed files and
coordinate collisions are rejected without partially importing a document.

The importer supports the earlier HTML prototype's JSON versions 1, 2 and 3,
as well as this application's version 4. Legacy integer IDs become strings.
An empty atlas is a valid file and can be imported/exported.

Use a different working file from the command line:

```bash
python main.py --file my-atlas.json
```

Start with no example nodes in a **new** file:

```bash
python main.py --file my-empty-atlas.json --empty
```

`--empty` never clears a file that already exists. The examples folder also
contains a fresh starter atlas and an empty atlas for import.

## The geometry

There are **7 equal-height levels x 17 equal-angle sectors x 5 equal-width
radial bands = 595 addresses**. These are logical addresses, not 595 rendered
objects. A mesh is built only for an occupied address.

The shape is cylindrical, not a Cartesian voxel grid. Equal increments in
radius and angle do **not** create equal physical volumes: outer wedges are
larger. This is intentional and follows the reference design.

The protocol ordering is fixed and included in every version-4 export.
Reordering it would rotate existing knowledge into different positions, so
files with incompatible grid definitions are rejected. Adding new protocol
sectors through the UI is outside this prototype's scope; use the existing
`Other` sector for an unlisted concept for now.

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
    model.py              Notes, fixed coordinates and validation
    geometry.py           Coordinate -> closed curved wedge
    storage.py            JSON, atomic writes and a previous-version backup
    scene.py              VTK rendering, camera and surface picking
    theme.py              Dark colors, widget styles and discrete band slider
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

The delivered build passed **34 core tests** and **13 GUI workflow checks** on
Linux using Python 3.13.5, Tk 8.6, VTK 9.6.2 and NumPy 2.3.5. GUI checks ran under
Xvfb, a virtual display, and used actual VTK rendering and Tk widgets. Test
outputs are in `docs/`. The preview is a capture of that running application,
not a design mockup.

Windows, macOS, physical GPU drivers, and your particular Arch/Sway setup have
**not** been verified here. The minimum window size is 1020 x 780. Source code
and launch instructions are included; this is not a packaged `.exe`.

## References

Official library documentation and package references are recorded in
`docs/REFERENCES.md`.
