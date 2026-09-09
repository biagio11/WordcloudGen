"""Build the standalone WordcloudGen executable.

    pip install -r requirements-dev.txt
    python build_exe.py

Downloads the NLTK corpora into build/nltk_data so the packaged app works
offline, then hands over to PyInstaller using wordcloud_gen_GUI.spec.
"""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NLTK_DIR = ROOT / "build" / "nltk_data"

# Bundle exactly the corpora the app asks for at runtime, so a packaged build
# never has to reach the network to find one that is missing.
sys.path.insert(0, str(ROOT))
from wordcloudgen.core import NLTK_PACKAGES, SUPPORTED_LANGUAGES  # noqa: E402

PACKAGES = NLTK_PACKAGES


def download_nltk_data() -> None:
    import nltk

    NLTK_DIR.mkdir(parents=True, exist_ok=True)
    for package in PACKAGES:
        print(f"  - {package}")
        if not nltk.download(package, download_dir=str(NLTK_DIR), quiet=True):
            raise SystemExit(f"Failed to download the NLTK package '{package}'.")


def prune_nltk_data() -> None:
    """Drop corpora the app cannot reach, to keep the download reasonable.

    NLTK ships punkt models for ~18 languages and keeps both the archive and
    its extracted copy; we need neither the unsupported languages nor the
    duplicate archives.
    """
    before = _folder_size(NLTK_DIR)
    languages = set(SUPPORTED_LANGUAGES)

    # Where a corpus was extracted, the .zip beside it is dead weight.
    for archive in NLTK_DIR.rglob("*.zip"):
        if archive.with_suffix("").is_dir():
            _remove(archive)

    # Keep only the sentence tokenizers for languages the UI offers.
    for models in (NLTK_DIR / "tokenizers" / "punkt" / "PY3",
                   NLTK_DIR / "tokenizers" / "punkt_tab"):
        if not models.is_dir():
            continue
        for entry in models.iterdir():
            if entry.stem.lower() not in languages:
                _remove(entry)

    after = _folder_size(NLTK_DIR)
    print(f"  pruned NLTK data: {before:.0f} MB -> {after:.0f} MB")


def _remove(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    elif path.exists():
        path.unlink()


def _folder_size(path: Path) -> float:
    if not path.is_dir():
        return 0.0
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / (1024 * 1024)


def main() -> int:
    print("Downloading NLTK corpora...")
    download_nltk_data()
    prune_nltk_data()

    dist = ROOT / "dist" / "WordcloudGen"
    # PyInstaller caches the collected file list in its work path. Wipe both,
    # or a rebuild silently ships the previous run's (unpruned) data files.
    workpath = ROOT / "build" / "pyinstaller"
    for stale in (dist, workpath):
        if stale.exists():
            print(f"Removing {stale}")
            shutil.rmtree(stale, ignore_errors=True)

    print("Running PyInstaller...")
    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
         "--workpath", str(workpath), "wordcloud_gen_GUI.spec"],
        cwd=ROOT,
    )
    if result.returncode != 0:
        return result.returncode

    exe = dist / "WordcloudGen.exe"
    print("\nVerifying the build...")
    check = subprocess.run([str(exe), "--selftest"], cwd=ROOT, timeout=300)
    if check.returncode != 0:
        print("The packaged app failed its self-test.")
        return check.returncode

    size = _folder_size(dist)
    print(f"\nDone. The app is in {dist} ({size:.0f} MB)")
    print(f"Run it with {exe}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
