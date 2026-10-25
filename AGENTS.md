# Development and release workflow

- Treat "Build it" as a request to implement the code change and run appropriate
  checks. Finish ordinary improvements without building distributable packages.
- After completing an application code change, summarize the result and ask
  whether the user wants it packaged as an update.
- Building Windows or Linux installers, creating portable packages, dispatching
  packaging workflows, bumping release versions, creating release tags, and
  publishing releases require the user's explicit request or approval for that
  update. Approval for a previous release does not authorize the next release.
- When the user explicitly requests packaging or a release, proceed within that
  approved scope without asking for the same approval again.
- Keep Linux packaging manual through `workflow_dispatch`. Ordinary commits and
  quality-of-life changes must not trigger package builds.
