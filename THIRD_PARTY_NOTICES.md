# Third-party software and model notices

The PolyForm Noncommercial license applies to Cosfolio application code only. The components below retain their original licenses; no commercial-use restriction is imposed on those components by Cosfolio.

| Component | Included version | License / upstream |
|---|---|---|
| BiRefNet general lite | bundled ONNX SHA256 recorded in models/birefnet-general-lite.json | MIT; https://github.com/ZhengPeng7/BiRefNet |
| ONNX conversion/distribution | danielgatis/rembg model release | MIT; https://github.com/danielgatis/rembg |
| ONNX Runtime | 1.31.0 | MIT; https://github.com/microsoft/onnxruntime |
| NumPy | 2.3.5 | BSD-3-Clause and bundled component notices; https://numpy.org/ |
| Pillow | 12.3.0 | HPND and bundled component notices; https://python-pillow.org/ |
| Python runtime | CPython 3.12.14 | PSF license; https://www.python.org/ |
| PySide6 Essentials / Shiboken6 | 6.12.0 | LGPL-3.0; https://pypi.org/project/PySide6-Essentials/6.12.0/ |
| Qt Core, GUI, Widgets, Network, SVG and runtime plugins | 6.12.0 | LGPL-3.0 and applicable bundled third-party terms; https://www.qt.io/ |
| PyInstaller bootloader | 6.22.3 | GPL with distribution exception; https://pyinstaller.org/ |

License texts and collected package notices are in licenses/, and the BiRefNet license is in resources/BiRefNet-LICENSE.txt. The PyPI PySide6 wheel is valid for LGPL usage as documented on its upstream project page, even where an included optional commercial-license notice is also present.

Qt and PySide6 libraries are dynamically loaded and have not been modified for this release. You may replace compatible libraries, relink them, and reverse-engineer the combined work where necessary to debug modifications to these LGPL components. Cosfolio's noncommercial license must not be interpreted to restrict those LGPL rights. Complete corresponding source locations and replacement notes are in docs/THIRD_PARTY_SOURCES.md.

Windows fonts are read from the local operating system; no separate Windows font files are distributed. Scene images and reference media are described separately in ASSET_RIGHTS.md and are not relicensed under this software notice.
