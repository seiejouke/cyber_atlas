# Third-party software

Cyber Atlas's GPL-3.0-only license applies to its original work. It does not
replace the licenses or copyright notices of its dependencies.

| Component | Purpose | License information |
| --- | --- | --- |
| [CPython](https://www.python.org/) | Bundled Python interpreter and standard library | Python license agreement and the additional notices supplied by the Python distribution |
| [Tcl/Tk](https://www.tcl-lang.org/) | Desktop interface | Tcl/Tk license terms, including their original copyright notices |
| [VTK](https://vtk.org/) | 3D rendering | BSD-style license; native third-party components may have additional terms |
| [NumPy](https://numpy.org/) | Frame-array conversion | BSD-3-Clause and the additional notices supplied with the installed wheel, including its bundled numerical libraries |
| [PyInstaller](https://pyinstaller.org/) | Builds the executable and supplies its bootloader | GPL-2.0-or-later with the PyInstaller bootloader exception; some files use Apache-2.0 |

Future package builds copy the complete license directories supplied by the
installed VTK and NumPy distributions into **Third-party notices/**. They also
include Python and Tcl/Tk notices and a manifest of versions and copied-file
hashes. A missing required notice stops the build. The PyInstaller license and
bootloader exception are included for reference.

Build-only dependencies such as Pillow and pyinstaller-hooks-contrib keep
their own licenses. Their presence in the build environment does not mean
that the complete packages are shipped in the application.

The collected notices are an inventory of supplied license files, not a
certification that every native library has been audited. Before publishing
a release, review the actual bundled libraries and satisfy any additional
notice, corresponding-source or relinking requirements. See the
[distribution checklist](docs/DISTRIBUTION.md).

Operating-system graphics drivers and libraries supplied by the user's
system are not included by this notice collector.
