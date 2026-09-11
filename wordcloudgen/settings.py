"""Where the desktop app keeps its files, and how it remembers settings.

Nothing here is required for the app to work: if the settings file is missing,
corrupt or unwritable, the app starts with defaults and carries on.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

APP_NAME = "WordcloudGen"

log = logging.getLogger("wordcloudgen")


def config_dir() -> Path:
    """Per-user folder for settings, saved palettes and the log file."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / APP_NAME


def _windows_pictures_dir() -> Path | None:
    """The real Pictures folder, which OneDrive often moves somewhere else."""
    try:
        import ctypes
        import uuid
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                        ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

        folder_id = uuid.UUID("33E28130-4E1E-4676-835A-98395C3BC3BB")  # FOLDERID_Pictures
        guid = GUID(folder_id.fields[0], folder_id.fields[1], folder_id.fields[2],
                    (ctypes.c_ubyte * 8)(*folder_id.bytes[8:]))
        result = ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(
                ctypes.byref(guid), 0, None, ctypes.byref(result)) != 0:
            return None
        try:
            return Path(result.value)
        finally:
            ctypes.windll.ole32.CoTaskMemFree(result)
    except (AttributeError, OSError, ValueError):
        return None


def pictures_dir() -> Path:
    if sys.platform == "win32":
        found = _windows_pictures_dir()
        if found:
            return found
    return Path.home() / "Pictures"


def default_output_dir(app_dir: Path, frozen: bool) -> Path:
    """Where images go until the user picks a folder.

    A source checkout keeps using its own output/ folder. The packaged app
    could live anywhere, including a read-only or throwaway folder, so it saves
    to Pictures/WordcloudGen instead.
    """
    if frozen:
        return pictures_dir() / APP_NAME
    return app_dir / "output"


def load_settings(path: str | os.PathLike) -> dict:
    """Read the settings file. Anything wrong with it just means no settings."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        log.warning("Ignoring unreadable settings file %s: %s", path, exc)
        return {}
    return data if isinstance(data, dict) else {}


def save_settings(path: str | os.PathLike, data: dict) -> bool:
    """Write the settings file atomically. Returns False instead of raising."""
    path = Path(path)
    temp = path.with_name(path.name + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        # Replacing in one step means a crash mid-write can't leave half a file.
        os.replace(temp, path)
    except (OSError, TypeError, ValueError) as exc:
        log.warning("Could not save settings to %s: %s", path, exc)
        return False
    return True
