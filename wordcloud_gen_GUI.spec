# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build recipe for the WordcloudGen desktop app.

    pip install -r requirements-dev.txt
    python build_exe.py            # downloads NLTK data, then runs this spec

One analysis, two builds:

    dist/WordcloudGen/WordcloudGen.exe   a folder; starts quickly
    dist/WordcloudGen-portable.exe       a single file; unpacks itself on each start

Every path is resolved at build time, so nothing here is machine-specific.
"""

import os
import re
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)

# Set WORDCLOUDGEN_CONSOLE=1 before building to keep a console window attached,
# which is the only practical way to read a traceback out of a frozen GUI app.
CONSOLE = os.environ.get("WORDCLOUDGEN_CONSOLE") == "1"

VERSION = re.search(r'__version__ = "([^"]+)"',
                    Path("wordcloudgen/__init__.py").read_text(encoding="utf-8"))[1]
ICON = "assets/icon.ico"


def version_resource(filename):
    """The details Windows shows under Properties > Details, and in Task Manager."""
    numbers = tuple(int(n) for n in re.findall(r"\d+", VERSION)[:3])
    numbers = (numbers + (0, 0, 0, 0))[:4]
    return VSVersionInfo(
        ffi=FixedFileInfo(filevers=numbers, prodvers=numbers, mask=0x3F, flags=0x0,
                          OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
        kids=[
            StringFileInfo([StringTable("040904B0", [
                StringStruct("CompanyName", "biagio11"),
                StringStruct("FileDescription", "WordcloudGen"),
                StringStruct("FileVersion", VERSION),
                StringStruct("InternalName", "WordcloudGen"),
                StringStruct("LegalCopyright", "biagio11. Licensed under CC BY-NC-SA 4.0."),
                StringStruct("OriginalFilename", filename),
                StringStruct("ProductName", "WordcloudGen"),
                StringStruct("ProductVersion", VERSION),
            ])]),
            VarFileInfo([VarStruct("Translation", [1033, 1200])]),
        ],
    )


# customtkinter ships .json themes and wordcloud its stopword list and default
# font, none of which PyInstaller's import scan can see. tkinterdnd2's native
# library is handled by the hook in pyinstaller-hooks-contrib.
datas = collect_data_files("customtkinter") + collect_data_files("wordcloud")

# NLTK corpora, downloaded into build/nltk_data by build_exe.py, so the packaged
# app works offline and does not hit the network on first launch.
nltk_data = Path("build") / "nltk_data"
if nltk_data.is_dir():
    datas.append((str(nltk_data), "nltk_data"))

# Sample fonts, palettes, the demo text (used by --selftest) and the icons.
for folder in ("fonts", "input", "assets"):
    if Path(folder).is_dir():
        datas.append((folder, folder))
# Palettes, minus any a pre-1.1 app auto-saved into a developer's checkout.
for palette in sorted(Path("colors").glob("*.json")):
    if not re.match(r"colors_\d{4}-", palette.name):
        datas.append((str(palette), "colors"))

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

# UPX is off on purpose: UPX-packed executables are a classic antivirus false
# positive, and an unsigned app has enough trouble with SmartScreen already.
common = dict(
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=CONSOLE,  # windowed app unless WORDCLOUDGEN_CONSOLE=1
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON,
)

# --- Folder build ----------------------------------------------------------

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="WordcloudGen",
    version=version_resource("WordcloudGen.exe"),
    **common,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="WordcloudGen",
)

# --- Single-file build -------------------------------------------------------

# Unpacking takes a few seconds. Without a splash nothing seems to happen, and
# people double-click again and end up with two copies running.
splash = Splash(
    "assets/splash.png",
    binaries=a.binaries,
    datas=a.datas,
    text_pos=(36, 206),
    text_size=9,
    text_color="#98a2ab",
    text_default="Starting...",
    minify_script=True,
    always_on_top=False,
)

portable = EXE(
    pyz,
    a.scripts,
    splash,
    splash.binaries,
    a.binaries,
    a.datas,
    [],
    name="WordcloudGen-portable",
    version=version_resource("WordcloudGen.exe"),
    runtime_tmpdir=None,
    **common,
)
