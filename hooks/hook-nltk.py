"""Override PyInstaller's stock NLTK hook.

The contributed hook copies *every* directory listed in ``nltk.data.path`` into
the bundle. On a developer machine that means the full ~100 MB corpus cache in
the user's home folder, and it silently overrides the trimmed copy that
build_exe.py prepares in build/nltk_data.

User hooks take precedence over the contributed ones, so this file keeps the
nltk package's own data files and leaves the corpora to build_exe.py.
"""

from PyInstaller.utils.hooks import collect_data_files

datas = collect_data_files("nltk", False)

hiddenimports = ["nltk.chunk.named_entity"]
