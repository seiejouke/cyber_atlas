# Cyber Atlas 0.10.1 — editable layer concepts

Windows and Linux packages are built and verified. Publication is pending.

Every new layer starts with its own editable central concept. Click its sphere
or layer label to write an overview, add information or subconcepts, and use the
concept in FlowNotes. New atlases and the Blank template include these concepts
automatically.

- Central concepts have persistent identities and use normal saving, backups,
  information heat and saved-state history.
- **Edit layer** opens the selected layer's naming and ordering controls. Its
  central concept stays on the axis; its title and the layer name can differ.
- **New node / Add here** from a central concept starts an outward concept on
  the same layer.
- Existing center notes, IDs and references are preserved. Clicking an older
  reference marker opens a named draft; **Create node** saves it. Opening the
  draft alone leaves the saved atlas unchanged.
- Repeating **Empty atlas** preserves the previous backup when only fresh
  default center notes remain. Removing an unused layer also removes its default
  center from the design draft; notes and referenced concepts remain protected.
- The README includes the combined development roadmap and groups node sizing
  with the implemented information-heat feature.

Atlas format remains **11**, compatible with Cyber Atlas 0.10.0. Older split
center layouts keep their existing blocks and notes. Existing saved atlases are
not automatically populated with new notes when opened.

The packages include the GPL-3.0-only application license, copyright and
third-party notices, a notice inventory and an application source archive.
Windows and Linux signing activation remains pending; these candidates are
unsigned.

Verification: 318 core tests on Windows and Ubuntu 22.04, 173 Windows desktop
workflow checks, 50 Windows frozen runtime checks, 49 checks per Linux format,
seven isolated Windows upgrade checks and four Debian installation checks.
The AppImage also passes 49 runtime checks on Ubuntu 24.04 under WSLg.
See the [verification record](layer-centers-verification.json).

Prepared files:

- `CyberAtlas-0.10.1-Setup.exe`
- `CyberAtlas-0.10.1-windows-x64.zip`
- `cyber-atlas_0.10.1_amd64.deb`
- `CyberAtlas-0.10.1-x86_64.AppImage`
- `SHA256SUMS.txt` and `SHA256SUMS-linux.txt`
