# Distribution preparation

This checklist records repository preparation separately from service setup,
package builds and publication. It does not claim that an existing download is
signed or that a new license removes operating-system warnings.

## Step 1: licensing and notices

Repository changes:

- GPL-3.0-only in the root LICENSE and a separate copyright notice.
- First-party attribution: Jouke Seinstra and Cyber Atlas contributors, 2026.
- README licensing information and a third-party component overview.
- Shared notice collection for Windows and Linux. The collector preserves the
  complete VTK/NumPy license trees, collects Python/Tcl/Tk and PyInstaller
  notices, and records versions and hashes. Missing required notices stop a build.
- An application source ZIP inside future bundles, with build scripts and
  instructions. Personal root-level atlas files, build directories and virtual
  environments are excluded. In a Git checkout, new source files must be tracked
  before packaging; untracked files are never archived.
- Copyright information in the Windows installer and standard Debian
  documentation location.

Verification on 26 October 2026: all 273 core tests passed on Windows; all
14 new licensing tests passed under Ubuntu WSL. An isolated staging check
with the installed Windows dependencies collected 22 notice files, validated
the application source archive and created Debian copyright documentation.
No application packages were built. The full Ubuntu suite could not complete
because that WSL Python installation lacks Tkinter; it was not installed or
changed as part of this step.

Before publication:

1. **Manual owner review:** confirm the copyright attribution and that you can license the included
   original code, illustrations, examples and contributed material under GPLv3.
   User notes outside this repository are not relicensed by this change.
2. **Release preparation:** review the actual native library inventory for each platform. Supplied wheel
   notices are preserved, but are not a complete audit of everything frozen by
   PyInstaller. Retain additional notices and provide any required corresponding
   dependency sources/relinking material. Do not assume an upstream link alone
   meets an obligation to distribute corresponding source.
3. Publish the exact release source with build instructions alongside the
   binaries. The included application source ZIP helps recipients rebuild the
   application; it is not a substitute for reviewing dependency obligations.
4. Build and publish only after the maintainer explicitly requests that release.

References: [GPLv3](https://www.gnu.org/licenses/gpl-3.0.html),
[PyInstaller licensing](https://pyinstaller.org/en/stable/license.html),
[Debian copyright documentation](https://www.debian.org/doc/debian-policy/ch-docs.html#copyright-information).

## Step 2: Windows signing — prepared, service setup pending

The staged signing tool, signature verifier, SignPath artifact configurations
and manual GitHub Actions workflow are implemented. Signatures require the
approved certificate fingerprint, Windows trust and a timestamp. Returned
payloads and the bundle are checked for changes before archival. The workflow
creates a signed candidate with desktop validation pending; it never publishes.
The provider round trips and Inno handoffs still need their first approved
end-to-end build. No existing release has been signed or rebuilt.

Follow the [manual SignPath setup guide](SIGNPATH_SETUP.md), including the
application draft, exact account variables, two signing requests and Windows
candidate validation. See the [code signing policy](CODE_SIGNING.md) and
[privacy policy](PRIVACY.md).

Verification on 26 October 2026: all 299 core tests passed on Windows and the
26 new signing tests passed on Ubuntu. Both artifact configurations validate
against SignPath's published v1 XML schema. Actionlint 1.7.12 accepts the manual
Windows and existing Linux workflows. Inno's signed and unsigned configuration
branches preprocess successfully with compilation disabled. The native Windows
verifier rejects the existing unsigned Cyber Atlas executable and accepts a
timestamped Microsoft-signed SDK tool when pinned to its certificate.
These are local checks, not a SignPath production signing run.

Manual setup: apply to SignPath Foundation, enable the required account security,
obtain project approval and configure its signing service. Do not commit account
credentials or private keys. SignPath's conditions prohibit commercial dual
licensing, and its certificate identifies SignPath Foundation as publisher.

Signed applications can still receive SmartScreen reputation prompts. This work
does not promise that antivirus products or every Windows policy will accept a
release without a warning.

References: [SignPath conditions](https://signpath.org/terms.html),
[Microsoft SmartScreen guidance](https://learn.microsoft.com/windows/apps/package-and-deploy/smartscreen-reputation).

## Step 3: Linux signing — pending

Add support for GPG-signed checksum manifests and embedded AppImage signatures.
Verify signatures before a signed release can be published. A signed APT
repository is deferred; the current distribution remains `.deb` and AppImage.

Manual setup: establish the release-signing key, preserve a secure backup and
revocation certificate, and publish the public key and fingerprint through the
project's release documentation. Never add private keys or passphrases to Git.

An AppImage signature needs a verifier; it does not universally remove launcher
prompts. See [AppImage signing](https://docs.appimage.org/packaging-guide/optional/signatures.html).

## Step 4: Arch Linux — pending

Prepare a versioned `cyber-atlas-bin` recipe (subject to name availability),
`.SRCINFO`, dependencies and desktop integration, plus manual Arch validation.
Use an approved Linux release artifact and verify its checksum/signature.
Arch-installed copies should direct updates through package management.

Manual setup before AUR publication: create an AUR account, register a dedicated
SSH public key, check for existing packages, and review the recipe. Complete an
actual Arch install/render/save/upgrade/removal check before claiming support.
An AUR listing is unofficial community distribution, not Arch endorsement.

Reference: [AUR submission guidelines](https://wiki.archlinux.org/title/AUR_submission_guidelines).

## Release boundary

All packaging workflows remain manual (`workflow_dispatch`). Preparing scripts
does not authorize dispatching them, bumping a version, signing an existing
release, creating a tag, uploading sources, or publishing packages. Follow the
maintainer's release request and [repository workflow](../AGENTS.md).
