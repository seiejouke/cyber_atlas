# Session handoff — 27 October 2026

Saved at the user's request so work can resume in another session. This is a
technical handoff, not a complete transcript. Read [AGENTS.md](../AGENTS.md)
and check `git status` before continuing; later user instructions take priority.

## Resume here

**Linux signing preparation is implemented locally but awaits owner setup and a
real signed run.** The next choice is how, if at all, the Linux signing identity
will be made available to the manual GitHub workflow. Until then, its Linux
build remains unsigned. Windows service activation, real signed builds and
publication remain pending.

Suggested instruction for a new session:

> Read AGENTS.md and docs/SESSION_HANDOFF.md, preserve the current release
> boundaries, and continue distribution preparation from the Linux signing
> owner actions. Keep package builds and publication manual.

## User's chosen direction and workflow

- Move forward with open-source GPL-3.0-only licensing, Windows signing through
  SignPath Foundation if approved, existing `.deb`/AppImage distribution and
  eventual Arch AUR distribution using a `cyber-atlas-bin` recipe.
- Work step by step. After each step, explain what the owner must do manually.
- Do not introduce a tester programme; the user explicitly set that aside.
- Ordinary source improvements do **not** authorize package builds, CI packaging
  dispatch, version bumps, tags, source uploads or publication. Request approval
  for the specific release/update when needed. This applies to every OS.
- Keep packaging workflows manual (`workflow_dispatch`).
- Do not submit applications, change account settings, generate signing identities
  or request credentials as if those actions were already completed.
- Do not claim signing eliminates all Windows/Linux warnings. No existing release
  was signed or changed by this work.

## Repository and release state

- Workspace: `C:\Users\Jouke\cyber_atlas` (PowerShell).
- GitHub: `seiejouke/cyber_atlas`, public repository.
- Starting commit for the resumed work: `a5963ec`, "Refactor legal file
  handling and signing process for Windows".
- Application version remains `0.10.0`; published v0.10.0 assets remain unchanged.
- The Linux signing preparation from the resumed session is in the working tree
  as uncommitted changes. It has not been pushed or backed up to GitHub.
- No application packages were built, signing requests submitted, or source
  changes uploaded during the licensing/signing preparation.

## Completed step 1: licensing and notices

Files and integration:

- `LICENSE`: unmodified GPLv3 text, SPDX `GPL-3.0-only`.
- `COPYRIGHT.txt`: 2026 Jouke Seinstra and Cyber Atlas contributors. Owner review
  of attribution and rights to included material is still required before public
  distribution. The notice does not license users' personal notes/imports.
- `THIRD_PARTY_NOTICES.md`: dependency overview and limits of the notice inventory.
- `.gitattributes`: preserves LF line endings for verbatim upstream license files.
- `packaging/licenses/`: reviewed CPython/Tcl/Tk fallback notices and provenance.
- `tools/release_legal.py`: shared Windows/Linux license collection. Preserves the
  complete supplied VTK/NumPy notice directories, runtime notices and PyInstaller
  terms; missing required notices stop the build. Includes a version/hash manifest
  and an application source ZIP in future bundles. Untracked source files in a
  Git checkout must be tracked before packaging; they are not silently archived.
- `tools/build_windows.py`, `tools/build_linux.py`, `packaging/windows.iss`:
  integration of licenses, attribution/source records and Debian copyright docs.
- `tests/test_release_legal.py`: 14 focused tests.

The included application source ZIP does not contain third-party dependency
sources. Reviewing native libraries and any additional notice, source or
relinking obligations is still part of preparation for an actual release.

## Completed step 2: Windows signing preparation

Files and behavior:

- `tools/windows_signing.py`: certificate SHA-256 pin validation, SDK SignTool
  discovery, Windows verification calls, unchanged-payload checks and bundle
  inventory checks.
- `tools/verify_windows_signature.ps1`: requires a valid embedded Authenticode
  signature, a timestamp, the approved certificate fingerprint, and successful
  SignTool verification. `RemoteSigned` is set only for its child PowerShell
  process; machine/user execution policies are not changed.
- `tools/sign_windows.py`: `preflight`, `prepare`, `assemble`, `finalize`, `verify`.
  Two signing rounds: application/updater/generated uninstaller first, then the
  assembled installer. Verifies returned files before creating final archives and
  checksums. No private keys, service submissions or publication in this script.
- `tools/build_windows.py`: supports `--bundle-only`; deferring desktop checks
  is allowed only for bundle preparation. The normal local build remains unsigned.
- `packaging/windows.iss`: conditional signed-uninstaller cache integration and
  consistent PE product metadata. Four-part PE product version, e.g. `0.10.1.0`,
  while the application/release version remains three-part.
- `packaging/signpath/windows-inputs-v1.xml` and `windows-installer-v1.xml`:
  explicit first-party signing paths, product/version constraints and SHA-256.
- `.github/workflows/windows-signing.yml`: manual only, GitHub-hosted Windows,
  repository/main restriction, `windows-signing` environment and setup preflight.
  Uses pinned actions and two manually approved `release-signing` requests.
  Produces a **candidate**, with `desktop_validation: pending`; never publishes.
- `tests/test_windows_signing.py`: 26 focused tests, with synthetic files for
  stage/payload tests. These do not establish a real provider round trip.

**Not yet exercised:** actual SignPath approval/API signing, the two complete
compiler/service handoffs, or a newly signed Cyber Atlas installation. Do not
describe these as production verified. Hosted CI intentionally defers desktop/
OpenGL validation; use a disposable Windows account for candidate validation.

## Owner actions still pending

The full instructions and application draft are in [SIGNPATH_SETUP.md](SIGNPATH_SETUP.md).

1. Review copyright attribution and permission to license original code, images,
   examples and contributed material under GPLv3.
2. Publish the reviewed license and policy files when a source upload is approved.
   They are currently local and cannot yet be reviewed on GitHub by SignPath.
3. Enable MFA and apply to SignPath Foundation. No application has been submitted.
4. After approval, configure the trusted GitHub build origin, two artifact
   configurations, production certificate, timestamps and manual approval policy.
5. Configure the `windows-signing` GitHub environment:
   - Secret: `SIGNPATH_API_TOKEN`.
   - Variables: `SIGNPATH_ORGANIZATION_ID`, `SIGNPATH_PROJECT_SLUG`,
     `WINDOWS_SIGNING_CERT_SHA256`, `SIGNPATH_READY`.
   - Set `SIGNPATH_READY` to `true` only after provider/setup review.
   - The fingerprint is 64 hexadecimal digits for SHA-256, not the usual SHA-1
     Windows thumbprint. Never paste tokens/private keys into chat or Git.

SignPath decides eligibility; its Foundation conditions exclude commercial dual
licensing, and its certificate identifies SignPath Foundation as publisher.
The next signed candidate build requires separate release/build authorization.

## Step 3: Linux signing preparation — implementation present, setup pending

`tools/build_linux.py --sign` creates an embedded AppImage signature and a
GPG-signed SHA-256 manifest, then verifies both against the configured full
fingerprint before reporting success. `tools/linux_signing.py verify` performs
independent verification using a temporary keyring containing only the supplied
public key. Unsigned builds remain the default. The manual GitHub Linux workflow
has not been connected to a signing identity and still produces unsigned
artifacts.

Owner actions: choose and establish a release-signing key; securely back up its
private key and revocation certificate; configure that key as GPG's default for
`appimagetool`; publish the public key and full fingerprint; install the
AppImageUpdate `validate` tool. Never place private keys or passphrases in
source control. No owner's Linux key has been generated, installed or used, and
no signed package build has been run.

A signed APT repository remains deferred. The `.deb` is covered by the signed
checksum manifest, not by a native package signature or APT trust. AppImage
signatures do not universally suppress desktop prompts.

## Later step 4: Arch distribution

Prepare `PKGBUILD`, `.SRCINFO`, dependencies, launcher integration and a manual
validation workflow, provisionally for `cyber-atlas-bin` (check availability).
Reuse a versioned Linux build and verify its checksum/signature. Arch-installed
copies should direct updates through package management rather than `.deb`.
No Arch packaging or Arch runtime validation has been implemented yet.

Owner action before AUR publication: AUR account and dedicated SSH access.
Complete actual Arch install/render/save/upgrade/removal checks before claiming
support. A signed pacman repository is deferred; AUR is unofficial distribution.

## Verification already performed

On 26 October 2026:

- All **299 core tests passed on Windows** using `.venv\Scripts\python.exe`.
- All **14 licensing tests** and **26 signing tests** passed under Ubuntu WSL.
- Full Ubuntu suite could not complete because its system Python lacks Tkinter;
  this was an environment limitation, and Tkinter was not installed for this work.
- Real dependency notice staging collected 22 notice files and validated the
  application source ZIP and Debian copyright document without building packages.
- Both SignPath XML configurations passed validation against the provider's
  published v1 XSD.
- Actionlint 1.7.12 accepted the new Windows and existing Linux workflows.
- Both Inno configuration branches preprocessed successfully with compilation
  disabled. No installer was compiled for these checks.
- Native Windows signature verification rejected the existing unsigned Cyber Atlas
  executable and accepted a timestamped Microsoft-signed SDK tool when pinned to
  its certificate. This was a verifier test, not project certificate activation.

On 27 October 2026, for Linux signing preparation:

- All **306 tests passed on Windows** using `.venv\Scripts\python.exe`.
- `tools/build_linux.py --help` and `tools/linux_signing.py --help` completed.
- Python byte-compilation and `git diff --check` passed.
- No Linux package build, GPG key operation or real signature verification was
  run. The signed path still needs validation with an owner-managed key and the
  AppImageUpdate `validate` tool.

Useful commands when changes justify rerunning checks:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_windows_signing.py -q
.\.venv\Scripts\python.exe tools/sign_windows.py --help
git diff --check
git status --short
```

The Windows SDK x64 SignTool and local Inno Setup are available. Ignored helper
downloads include `build/tools/actionlint-1.7.12/` and
`build/signpath-artifact-configuration-v1.xsd`. They are optional local checking
tools, not project release assets. WSL enumeration/execution required sandbox
escalation in this environment. No approval-review rejection is currently pending.

## Preserve earlier unrelated work

README already had an uncommitted **planned multi-atlas workspace** section
before licensing began. It describes independent complete atlases in one shared
viewport, with add-empty/template/import-alongside actions and stable local
coordinates. This feature is explicitly deferred and not part of v0.10.0.
Preserve that section and its contents/status-table links; do not implement the
feature as part of signing or distribution work.

## Related documents

- [Distribution checklist](DISTRIBUTION.md)
- [SignPath setup and owner actions](SIGNPATH_SETUP.md)
- [Code signing policy](CODE_SIGNING.md)
- [Privacy policy](PRIVACY.md)
- [Developer guide](DEVELOPMENT.md)

This handoff and working files are local. A Git commit/push, remote backup,
release, account application and signing activation have not been performed by
saving this session.
