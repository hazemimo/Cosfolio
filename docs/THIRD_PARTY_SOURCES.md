# Corresponding source and replacement information

This portable build dynamically loads unmodified Qt/PySide6 libraries from its `_internal/` directory. Application source is available in this repository at the release tag. The build recipe is BUILDING.md, Cosfolio.spec, build.ps1 and tools/package_release.py.

## Qt/PySide6 6.12.0

The exact upstream source version is **6.12.0**. Qt for Python / Shiboken sources:

- https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.12.0-src/pyside-setup-everywhere-src-6.12.0.tar.xz
- https://code.qt.io/cgit/pyside/pyside-setup.git/?h=v6.12.0

Qt library and plugin sources (qtbase provides Core, GUI, Widgets, Network, and platform/image plugins; qtsvg provides SVG):

- https://download.qt.io/official_releases/qt/6.12/6.12.0/submodules/qtbase-everywhere-src-6.12.0.tar.xz
- https://download.qt.io/official_releases/qt/6.12/6.12.0/submodules/qtsvg-everywhere-src-6.12.0.tar.xz
- https://code.qt.io/cgit/qt/qtbase.git/?h=v6.12.0
- https://code.qt.io/cgit/qt/qtsvg.git/?h=v6.12.0

These are the complete corresponding upstream sources for the unmodified libraries, including upstream build instructions. Their own LICENSES directories and attribution files contain additional third-party license information. The published Windows download is accompanied by these source directions; they are not a promise of a different private license.

To use a modified compatible build, first keep a backup, build the relevant upstream libraries for Windows x64 with a compatible MSVC toolchain and CPython ABI, then replace the relevant PySide6/Shiboken extension modules and Qt DLLs/plugins under `_internal/`. Do not mix incompatible Qt minor releases. There is no application signature check or DRM preventing replacement. You may instead run or rebuild Cosfolio from its published source against your modified libraries.

## Other components

- CPython 3.12.14: https://github.com/python/cpython/tree/v3.12.14
- ONNX Runtime 1.31.0: https://github.com/microsoft/onnxruntime/tree/v1.31.0
- NumPy 2.3.5: https://github.com/numpy/numpy/tree/v2.3.5
- Pillow 12.3.0: https://github.com/python-pillow/Pillow/tree/12.3.0
- PyInstaller 6.22.3: https://github.com/pyinstaller/pyinstaller/tree/v6.22.3
- BiRefNet: https://github.com/ZhengPeng7/BiRefNet
- Bundled model download and SHA256: models/birefnet-general-lite.json

Third-party sources retain their upstream licenses. Cosfolio's license does not restrict rights provided by these upstream licenses.
