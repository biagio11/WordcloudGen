"""Build the standalone WordcloudGen app.

    pip install -r requirements-dev.txt
    python build_exe.py                 # add --no-selftest to skip running the builds

Downloads the NLTK corpora into build/nltk_data so the packaged app works
offline, runs PyInstaller with wordcloud_gen_GUI.spec, checks that both builds
can render a word cloud, and leaves release-ready copies in dist/release/.
"""

import hashlib
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NLTK_DIR = ROOT / "build" / "nltk_data"
DIST = ROOT / "dist"
SUFFIX = ".exe" if sys.platform == "win32" else ""

# Bundle exactly the corpora the app asks for at runtime, so a packaged build
# never has to reach the network to find one that is missing.
sys.path.insert(0, str(ROOT))
from wordcloudgen import __version__  # noqa: E402
from wordcloudgen.core import NLTK_PACKAGES, SUPPORTED_LANGUAGES  # noqa: E402

FOLDER_BUILD = DIST / "WordcloudGen"
FOLDER_EXE = FOLDER_BUILD / f"WordcloudGen{SUFFIX}"
PORTABLE_EXE = DIST / f"WordcloudGen-portable{SUFFIX}"
RELEASE = DIST / "release"


def platform_tag() -> str:
    if sys.platform == "win32":
        return "windows-x64" if platform.machine().endswith("64") else "windows-x86"
    return f"{platform.system().lower()}-{platform.machine().lower()}"


def download_nltk_data() -> None:
    import nltk

    NLTK_DIR.mkdir(parents=True, exist_ok=True)
    for package in NLTK_PACKAGES:
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


def pyinstaller_env() -> dict:
    """The environment to run PyInstaller in.

    A conda env keeps Tcl/Tk, sqlite and libffi in Library/bin, which is only
    on PATH while the env is activated. Called directly (.venv/python.exe
    build_exe.py) PyInstaller can't find them and ships an app that has no Tk
    and no working ctypes, so put that folder on PATH ourselves.
    """
    env = dict(os.environ)
    library_bin = Path(sys.prefix) / "Library" / "bin"
    if library_bin.is_dir():
        env["PATH"] = f"{library_bin}{os.pathsep}{env.get('PATH', '')}"
    return env


def selftest(exe: Path) -> bool:
    """Run a build with --selftest, which renders a cloud without a window."""
    started = time.perf_counter()
    try:
        result = subprocess.run([str(exe), "--selftest"], cwd=ROOT, timeout=300)
    except subprocess.TimeoutExpired:
        print(f"  {exe.name}: no answer after 5 minutes. Antivirus software sometimes "
              "holds a new executable this long while it inspects it.")
        return False
    except OSError as exc:
        # "Access is denied" on a file we just built almost always means
        # antivirus software is blocking an unsigned executable it hasn't seen.
        print(f"  {exe.name}: Windows refused to start it ({exc}).\n"
              "    If you use antivirus software, it is probably blocking the new file.\n"
              "    Allow it there, or rebuild with --no-selftest and try the app by hand.")
        return False
    elapsed = time.perf_counter() - started
    ok = result.returncode == 0
    print(f"  {exe.name}: {'OK' if ok else f'FAILED (exit {result.returncode})'} "
          f"in {elapsed:.1f} s")
    return ok


def package_release() -> list[Path]:
    """Name the builds for the release and write their checksums."""
    RELEASE.mkdir(parents=True, exist_ok=True)
    stem = f"WordcloudGen-v{__version__}-{platform_tag()}"

    portable = RELEASE / f"{stem}{SUFFIX}"
    shutil.copy2(PORTABLE_EXE, portable)
    # The zip holds a WordcloudGen/ folder, so "extract here" can't scatter
    # hundreds of files across someone's Downloads folder.
    archive = Path(shutil.make_archive(str(RELEASE / stem), "zip",
                                       root_dir=DIST, base_dir=FOLDER_BUILD.name))

    files = [portable, archive]
    lines = [f"{_sha256(path)}  {path.name}" for path in files]
    (RELEASE / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return files


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


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
    print(f"Building WordcloudGen {__version__}")
    print("Downloading NLTK corpora...")
    download_nltk_data()
    prune_nltk_data()

    # PyInstaller caches the collected file list in its work path. Wipe it along
    # with the old output, or a rebuild silently ships the previous run's files.
    workpath = ROOT / "build" / "pyinstaller"
    for stale in (FOLDER_BUILD, PORTABLE_EXE, RELEASE, workpath):
        if stale.exists():
            print(f"Removing {stale.relative_to(ROOT)}")
            _remove(stale)

    print("Running PyInstaller...")
    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
         "--workpath", str(workpath), "wordcloud_gen_GUI.spec"],
        cwd=ROOT,
        env=pyinstaller_env(),
    )
    if result.returncode != 0:
        return result.returncode

    if "--no-selftest" in sys.argv:
        print("\nSkipping the self-test. Try both builds by hand before publishing them.")
    else:
        print("\nChecking both builds can render a word cloud...")
        if not all([selftest(FOLDER_EXE), selftest(PORTABLE_EXE)]):
            print("A packaged build failed its self-test, so nothing was packaged.")
            return 1

    print("\nPackaging...")
    for path in package_release():
        print(f"  {path.relative_to(ROOT)}  ({path.stat().st_size / (1024 * 1024):.0f} MB)")
    print(f"\nDone. Run {PORTABLE_EXE.relative_to(ROOT)} to try it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
