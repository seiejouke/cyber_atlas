# Windows signing setup

Repository preparation is implemented. The service is **not activated**, no
signing requests have been submitted, and no packages were built for this step.
The actual SignPath round trips and compiler handoffs still need their first
approved end-to-end build. The existing v0.10.0 downloads remain unchanged.

## 1. Owner actions before applying

1. Complete the licensing attribution/ownership review in [DISTRIBUTION.md](DISTRIBUTION.md).
2. Publish the reviewed license, [code signing policy](CODE_SIGNING.md) and
   [privacy policy](PRIVACY.md) when you approve uploading these source changes.
   Local files are not yet visible to the service's reviewers.
3. Enable MFA on GitHub and on the signing-service account.
4. Apply through [SignPath Foundation](https://signpath.org/apply.html). Applying
   is an owner action; the coding agent has not submitted an application.

Application information to review and reuse:

| Field | Proposed content |
| --- | --- |
| Project | Cyber Atlas |
| Repository | https://github.com/seiejouke/cyber_atlas |
| Maintainer | Jouke Seinstra / `seiejouke` |
| License | GPL-3.0-only |
| Function | Offline desktop notebook for spatial knowledge maps, orbital subconcepts and interactive learning/process guides |
| Platform | Windows x64, with Linux distributions maintained separately |
| Existing release | v0.10.0; currently unsigned |
| Build origin | Manual GitHub Actions workflow on GitHub-hosted Windows runners |
| Signing scope | Own application, own updater script, generated uninstaller and installer; no upstream third-party binaries |
| Requested policy | `release-signing`, manual approval for every request |

SignPath decides eligibility. Its conditions exclude commercial dual licensing.
Its Foundation-issued certificate identifies SignPath Foundation as publisher.

## 2. Configure the approved service

Create the project (the slug can be `cyber-atlas`) and link the GitHub.com trusted
build system to this repository. Install/authorize the SignPath GitHub integration
as directed by the provider. Restrict origin to this repository, `main`, and
`.github/workflows/windows-signing.yml`; allow GitHub-hosted runners only.

Create the following artifact configurations from the checked-in XML:

- `windows-inputs-v1`: [application/updater/uninstaller](../packaging/signpath/windows-inputs-v1.xml).
- `windows-installer-v1`: [outer installer](../packaging/signpath/windows-installer-v1.xml).

Use `release-signing` with a production certificate and manual approval, not an
automatic/test signing policy. Both configurations receive the exact four-part
Windows product version, e.g. `0.10.1.0`; PE product-name must be `Cyber Atlas`.
Do not loosen metadata constraints to make an unexpected sample pass. Review
the first actual Inno uninstaller metadata and provider schema before enabling
production requests. Enable trusted RFC 3161/SHA-256 timestamping as supported
by the provider; the scripts reject missing timestamps.

Record the approved signing certificate's **SHA-256** fingerprint from the
provider, independently of downloaded artifacts. The usual 40-digit SHA-1
Windows certificate thumbprint is not the value used here. Check the 64 hex
digits against the provider's certificate before configuring the workflow.

## 3. Configure GitHub

Create a `windows-signing` environment. Restrict deployment branches to `main`
and configure appropriate owner approval/branch protection. Add these values
as environment secrets/variables; none is written into source files:

| Type | Name | Value |
| --- | --- | --- |
| Secret | `SIGNPATH_API_TOKEN` | Dedicated submitter token for the approved project/policy |
| Variable | `SIGNPATH_ORGANIZATION_ID` | Assigned SignPath organization ID |
| Variable | `SIGNPATH_PROJECT_SLUG` | Approved project slug |
| Variable | `WINDOWS_SIGNING_CERT_SHA256` | Approved certificate's 64-digit SHA-256 fingerprint |
| Variable | `SIGNPATH_READY` | Set to `true` only after provider approval and configuration review |

The workflow checks configuration before building or requesting signatures.
The local verifier uses `RemoteSigned` for its child PowerShell process only;
it does not change user/machine execution policies or override Group Policy.
The signing action and other actions are pinned to reviewed commits. API tokens
are supplied only as masked action/environment inputs; private keys stay with
the provider. Do not paste tokens into chat or commit them.

## 4. First approved candidate build

Request a package build separately after these changes have been reviewed and
tracked in Git. Dispatch **Prepare signed Windows candidate** manually from
`main` only when that release is approved. Be available in SignPath to approve
two successive requests (each waits up to 20 minutes). The first run must verify
that the provider accepts the actual generated metadata and Inno cache handoff.
No end-to-end provider run has been performed during repository preparation.

The workflow uses Windows SDK `signtool.exe` and Inno Setup from the hosted
runner. If either is absent, preflight fails before a build/request; use a
reviewed pinned tool installation when updating runner tooling.

The stages are:

1. Build the application folder and collect notices/source. No release ZIP or
   installer is emitted. A deliberate first Inno compilation stops at its
   external uninstaller-signing handoff and captures that uninstaller.
2. Upload just `CyberAtlas.exe`, `update_helper.ps1` and `uninstaller.exe` as a
   GitHub workflow artifact. SignPath verifies origin and signs those files.
3. Verify returned signatures, timestamp, certificate fingerprint and unchanged
   payloads. Restore the signed uninstaller to its exact Inno cache name, then
   assemble an installer containing the signed application/updater/uninstaller.
4. Upload that installer as a second workflow artifact and request its signature.
5. Verify it and recheck the bundle before producing the candidate ZIP, checksums
   and `windows-signing-report.json`. Missing, altered or incorrectly signed
   files stop the build. No unsigned fallback or automatic publication exists.

GitHub-hosted builds defer desktop/OpenGL checks; the report explicitly says
`desktop_validation: pending`. A successful signing job alone is not evidence
of successful rendering, installation, upgrade or removal.

## 5. Validate and publish separately

Download the `cyber-atlas-windows-signed-candidate` artifact through the trusted
GitHub Actions run. In a disposable Windows account/VM without Cyber Atlas
installed, put the candidate files in `dist/` in the matching source checkout.
Keep existing installations and notes untouched. Set the approved public
certificate fingerprint, then run:

```powershell
$env:WINDOWS_SIGNING_CERT_SHA256 = 'APPROVED_64_HEX_DIGITS'
.\.venv\Scripts\python.exe tools/sign_windows.py verify
```

This verifies the installer before executing it, then checks installed
application/updater/uninstaller signatures and the actual desktop self-test,
reinstallation and removal using disposable test data. An existing installation
causes the installer check to be skipped and validation to remain pending.
No candidate is published by this command. Retain its reports, review native
dependency/source obligations, and complete any cross-version upgrade check
appropriate for that release before publishing through an approved release step.

Add the code-signing-policy link and provider acknowledgement to the future
signed release page. SmartScreen can still prompt on a new signed release;
do not promise that all Windows warnings disappear.

## References

- [SignPath GitHub origin verification](https://docs.signpath.io/trusted-build-systems/github)
- [SignPath artifact configuration](https://docs.signpath.io/artifact-configuration/)
- [Inno signed uninstallers](https://jrsoftware.org/ishelp/topic_setup_signeduninstaller.htm)
- [Windows SignTool](https://learn.microsoft.com/en-us/windows/win32/seccrypto/signtool)
