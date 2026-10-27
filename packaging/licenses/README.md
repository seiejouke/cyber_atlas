# Upstream license texts

These files are unmodified upstream notices used only when the build's
interpreter or Tcl/Tk installation does not supply a copy. A notice supplied
by the actual runtime takes precedence. Do not substitute a notice for an
unreviewed runtime version.

| File | Upstream source | SHA-256 |
| --- | --- | --- |
| Python-3.12.3.txt | https://github.com/python/cpython/blob/v3.12.3/LICENSE | `3b2f81fe21d181c499c59a256c8e1968455d6689d269aa85373bfb6af41da3bf` |
| Tcl-8.6.13.txt | https://github.com/tcltk/tcl/blob/core-8-6-13/license.terms | `c0a69a2bfd757361ec7e6143973b103c90409316b49e9c88db26ad6388e79f16` |
| Tk-8.6.13.txt | https://github.com/tcltk/tk/blob/core-8-6-13/license.terms | `2cde822b93ca16ae535c954b7dfe658b4ad10df2a193628d1b358f1765e8b198` |

The Tcl and Tk license texts were compared with the corresponding files in
the `core-8-6-12` and `core-8-6-14` tags on 26 October 2026. Each is byte-for-byte
identical to its 8.6.13 copy. The fallback therefore covers these three patch
versions only. The package's `init.tcl` and `tk.tcl` identify the bundled
versions without starting a graphical desktop.

The project's root LICENSE is the unmodified GPLv3 text from
https://github.com/spdx/license-list-data/blob/main/text/GPL-3.0-only.txt,
SHA-256 `fb981668c18a279e285fc4d83fba1e836cc84dd4daa73c9697d3cfd2d8aca6e0`.
