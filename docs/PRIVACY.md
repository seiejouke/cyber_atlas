# Privacy

Cyber Atlas stores your notes, information entries, FlowNotes, atlas history,
settings and logs on your computer. It has no account system, advertising,
analytics or automatic crash-report uploads. Its application code does not send
your notes, imported atlases or history to the project maintainer.

The application works offline after installation. Exported JSON and history ZIP
files are created locally; you choose where to store or share them. Removing the
application preserves its saved user data. See the [user guide](USER_GUIDE.md)
for storage paths and backups.

## Updates and external links

Choosing **Updates** contacts GitHub to check the project's releases. Automatic
daily checks are off by default and run only if you enable them. Downloads start
when you choose to download an update. GitHub receives ordinary network-request
information, such as your IP address and the application's user-agent header.
No atlas content is included in these requests.

Opening a release or other external link uses your web browser; the destination
site's privacy policy applies. GitHub's handling of requests is described in its
[privacy statement](https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement).

## Build and signing services

The project's development workflow may upload build artifacts to GitHub Actions
and, after service approval, SignPath for code signing. This is a maintainer
operation, not an activity performed by the installed application. Personal
atlas files and private signing keys must not be included in those artifacts.
See [SignPath's privacy policy](https://about.signpath.io/privacy-policy).

## Contact

For questions, use the [project's GitHub issues](https://github.com/seiejouke/cyber_atlas/issues).
Do not attach private notes or logs unless you intend them to be public.
