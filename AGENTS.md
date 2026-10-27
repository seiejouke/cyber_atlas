# Development and release workflow

- Apply this policy to every OS and packaging target, including Windows, Linux,
  macOS, and any future platforms.
- Treat "Build it" as a request to implement the code change and run appropriate
  checks. Finish ordinary improvements without building distributable packages.
- After completing an application code change, summarize the result and ask
  whether the user wants it packaged as an update.
- Building installers for any OS, creating portable packages, dispatching
  packaging workflows, bumping release versions, creating release tags, and
  publishing releases require the user's explicit request or approval for that
  update. Approval for a previous release does not authorize the next release.
- When the user explicitly requests packaging or a release, proceed within that
  approved scope without asking for the same approval again.
- Keep packaging workflows manual on every platform, using `workflow_dispatch`
  for GitHub Actions. Ordinary commits and quality-of-life changes must not
  trigger package builds.

# Resuming distribution work

- Read [docs/SESSION_HANDOFF.md](docs/SESSION_HANDOFF.md) when resuming the
  licensing, signing and Arch distribution work. Check the current working tree
  against that dated handoff before acting; it records context, not permission
  to build packages, upload sources, activate services or publish a release.
