# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build recipe for the WordcloudGen GUI.

Unlike a hand-written `--add-data` command line, this resolves every package
path at build time, so it works on any machine and in CI:

    pip install -r requirements-dev.txt
    python build_exe.py            # downloads NLTK data, then runs this spec

The result is dist/WordcloudGen/WordcloudGen.exe plus the folders it needs.
"""

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Set WORDCLOUDGEN_CONSOLE=1 before building to keep a console window attached,
# which is the only practical way to read a traceback out of a frozen GUI app.
CONSOLE = os.environ.get("WORDCLOUDGEN_CONSOLE") == "1"

# The CustomTkinter family ships .json themes and .png assets that PyInstaller's
# module scan cannot see, so collect each package's data files explicitly.
CTK_PACKAGES = [
    "customtkinter",
    "CTkColorPicker",
    "CTkMessagebox",
    "CTkToolTip",
    "CTkListbox",
    "wordcloud",  # bundled stopwords list and the default DroidSansMono font
]

datas = []
for package in CTK_PACKAGES:
    datas += collect_data_files(package, include_py_files=True)

# NLTK corpora, downloaded into build/nltk_data by build_exe.py, so the packaged
# app works offline and does not hit the network on first launch.
nltk_data = Path("build") / "nltk_data"
if nltk_data.is_dir():
    datas.append((str(nltk_data), "nltk_data"))

# Ship the sample assets next to the executable.
for folder in ("colors", "fonts", "input"):
    if Path(folder).is_dir():
        datas.append((folder, folder))

hiddenimports = collect_submodules("wordcloudgen") + [
    "PIL._tkinter_finder",
    "nltk.stem.wordnet",
    "nltk.tokenize.punkt",
    "nltk.corpus",
]

a = Analysis(
    ["wordcloud_gen_GUI.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=["hooks"],  # our hook-nltk.py overrides the stock one
    hooksconfig={},
    runtime_hooks=[],
    # matplotlib itself must stay: the wordcloud package imports it at module
    # level. Only its unused GUI backends and the usual dev-only packages go.
    excludes=[
        "PyQt5", "PyQt6", "PySide2", "PySide6", "wx",
        "matplotlib.backends.backend_qt5agg",
        "matplotlib.backends.backend_qtagg",
        "matplotlib.backends.backend_wxagg",
        "matplotlib.backends.backend_webagg",
        "pytest", "IPython", "jupyter", "notebook",
        # Note: do not exclude "unittest" - pyparsing, and therefore
        # matplotlib, imports it at module level.
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="WordcloudGen",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=CONSOLE,  # windowed app unless WORDCLOUDGEN_CONSOLE=1
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="docs/icon.ico" if Path("docs/icon.ico").is_file() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="WordcloudGen",
)
