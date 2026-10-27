# Code signing policy

**Status: preparation only. SignPath approval and account configuration are
pending. No existing Cyber Atlas download has been signed by this change.**

## Responsibility

The project maintainer is [Jouke Seinstra (`seiejouke`)](https://github.com/seiejouke).
The maintainer currently performs the author, reviewer and signing-approver
roles. Contributions from other authors must be reviewed before inclusion.
If more maintainers join, list their roles here before granting signing access.

Signing and source-control accounts must use multi-factor authentication.
Every release needs explicit maintainer approval. Each SignPath request uses
the `release-signing` policy and must require manual approval in SignPath.

## What may be signed

Only the Cyber Atlas application, updater script, generated uninstaller and
installer built from this project's reviewed source may be signed under this
policy. Third-party DLLs and executables retain their original signatures and
notices; this workflow does not sign them using the project's signing identity.

The proposed provider is SignPath Foundation, subject to its approval and
[conditions](https://signpath.org/terms.html). After activation, signed-release
pages must carry this acknowledgement:

> Free code signing provided by [SignPath.io](https://signpath.io), certificate by [SignPath Foundation](https://signpath.org).

The provider's certificate identifies SignPath Foundation as publisher; the
application's author and installer metadata identify the Cyber Atlas maintainer.
Do not describe the service as active before approval and the first verified
signed build.

## Build and verification

The signing workflow is manual, runs on GitHub-hosted Windows runners, and is
restricted to this repository's `main` branch. SignPath retrieves uploaded
workflow artifacts and verifies their build origin. Protect `main` and configure
the `windows-signing` environment before enabling this workflow.

Two requests are made: application/updater/uninstaller, followed by the assembled
installer. The artifact configurations restrict file paths and PE product
name/version and request SHA-256 signatures. Configure trusted RFC 3161
timestamping with SHA-256 through the provider; missing timestamps fail local
verification. The first production run must confirm the provider's timestamp
settings as well as artifact metadata against actual outputs.

Windows verifies embedded signatures, certificate trust and timestamps, and the
build requires the approved certificate's SHA-256 fingerprint. Returned payloads
are compared with the originals. The bundle is checked for changes between
stages, and signatures are verified before ZIP/checksum creation. Failed checks
stop the build; there is no unsigned fallback in the signing workflow.

The output is a signed candidate, with desktop validation explicitly pending.
Validate the signed installer on a disposable Windows account before publishing.
The workflow never creates a release, tag or version change automatically.

Signing establishes publisher identity and integrity. It does not guarantee the
absence of SmartScreen, antivirus, administrative or enterprise-policy prompts.

## Privacy

See the [privacy policy](PRIVACY.md). Notes and history remain local. Update
checks and downloads contact GitHub only through user-requested actions or
previously enabled automatic checks. Development-time signing sends build
artifacts to GitHub Actions and SignPath; it does not send users' atlas files.

## Certificate changes

Verify a replacement certificate through the approved provider before updating
`WINDOWS_SIGNING_CERT_SHA256`. A mismatched certificate stops verification.
If signing credentials are compromised, disable signing, revoke affected access,
notify the provider and document affected release versions before resuming.
