"""Desktop app for WordcloudGen (customtkinter)."""

import logging
import logging.handlers
import os
import queue
import random
import re
import subprocess
import sys
import threading
import time
import tkinter
import traceback
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox

import customtkinter
from PIL import Image, ImageColor, ImageDraw, ImageFont

# Make the app importable no matter where it is launched from, including from
# inside a PyInstaller bundle.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from wordcloudgen import __version__
from wordcloudgen.core import (
    AUTO_LANGUAGE,
    DEFAULT_COLORS,
    DOCUMENT_EXTENSIONS,
    IMAGE_EXTENSIONS,
    SUPPORTED_LANGUAGES,
    WordcloudError,
    check_size,
    clean_palette,
    export_image,
    generate_word_cloud,
    load_colors,
    normalize_exclusions,
    write_palette,
)
from wordcloudgen.settings import config_dir, default_output_dir, load_settings, save_settings

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:  # drag and drop is a nicety, the app works without it
    TkinterDnD = None

log = logging.getLogger("wordcloudgen")

customtkinter.set_appearance_mode("System")
customtkinter.set_default_color_theme("green")

AUTO_LABEL = "Detect automatically"
DEFAULT_FONT_LABEL = "Default"
OTHER_FONT_LABEL = "Other font file..."
OPEN_PALETTE_LABEL = "Open palette file..."
CUSTOM_LABEL = "Custom"

SIZE_PRESETS = {
    "Widescreen  1920 × 1080": (1920, 1080),
    "4K  3840 × 2160": (3840, 2160),
    "Square  2048 × 2048": (2048, 2048),
    "Portrait  1080 × 1350": (1080, 1350),
    "Phone story  1080 × 1920": (1080, 1920),
    "A4 print  3508 × 2480": (3508, 2480),
}

BACKGROUNDS = {"White": "white", "Dark": "#14181f", "Transparent": "transparent"}
CUSTOM_BACKGROUND = "Custom..."

QUICK_COLORS = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b", "#e377c2", "#7f7f7f",
    "#bcbd22", "#17becf", "#0d3b66", "#f4d35e", "#ee964b", "#f95738", "#101820", "#ffffff",
]

MIN_WINDOW = (900, 600)
MAX_PALETTE = 24
SWATCH_COLUMNS = 8
TOP_WORDS = 10
MUTED = ("gray40", "gray62")
ERROR_TEXT = ("#a61b1b", "#ff9b9b")
ERROR_FILL = ("#fde7e7", "#4a2323")
OK_TEXT = ("#1e7a4a", "#7ddca8")


# ------------------------------------------------------------------- paths

def app_dir() -> Path:
    """The folder the app runs from: the source checkout, or the .exe's folder."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def resource_dir() -> Path:
    """Read-only folder holding the bundled colors/, fonts/ and assets/.

    PyInstaller unpacks bundled data under sys._MEIPASS, which is *not* the
    folder the .exe lives in.
    """
    return Path(getattr(sys, "_MEIPASS", None) or app_dir())


def find_asset(*parts: str) -> Path | None:
    """Look for an asset next to the app first, then in the bundle."""
    for base in (app_dir(), resource_dir()):
        candidate = base.joinpath(*parts)
        if candidate.exists():
            return candidate
    return None


def user_palette_dir() -> Path:
    return config_dir() / "palettes"


def open_in_system(path: Path) -> None:
    """Open a file or folder with whatever the OS normally uses for it."""
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    else:
        subprocess.run(["xdg-open", str(path)], check=False)


def reveal_in_folder(path: Path) -> None:
    """Open the containing folder with the file selected, where the OS allows it."""
    if sys.platform == "win32":
        subprocess.Popen(["explorer", "/select,", str(path)])
    elif sys.platform == "darwin":
        subprocess.run(["open", "-R", str(path)], check=False)
    else:
        open_in_system(path.parent)


# -------------------------------------------------------------- font names

def font_display_name(path: Path) -> str:
    """The name a font gives itself ("Century Gothic"), not its file name."""
    try:
        family, style = ImageFont.truetype(str(path), 12).getname()
    except OSError:
        return path.stem.replace("_", " ")
    family, style = (family or "").strip(), (style or "").strip()
    if not family:
        return path.stem.replace("_", " ")
    if style.lower() in ("", "regular", "normal", "book", "roman"):
        return family
    return f"{family} {style}"


def palette_display_name(path: Path) -> str:
    stem = re.sub(r"_colors$", "", path.stem)
    return stem.replace("_", " ").replace("-", " ").strip().title() or path.stem


def is_autosaved_palette(path: Path) -> bool:
    """Palettes 1.0 wrote on every run (colors_YYYY-MM-DD_HH-MM-SS.json)."""
    return re.fullmatch(r"colors_\d{4}-\d\d-\d\d_\d\d-\d\d-\d\d(_\d+)?", path.stem) is not None


# --------------------------------------------------------------- imaging

def checkerboard(size, cell: int = 10) -> Image.Image:
    """The grey-and-white grid image editors use to mean "transparent"."""
    tile = Image.new("RGBA", (cell * 2, cell * 2), "#ffffff")
    draw = ImageDraw.Draw(tile)
    draw.rectangle((0, 0, cell - 1, cell - 1), fill="#e3e3e3")
    draw.rectangle((cell, cell, cell * 2 - 1, cell * 2 - 1), fill="#e3e3e3")
    board = Image.new("RGBA", size)
    for x in range(0, size[0], cell * 2):
        for y in range(0, size[1], cell * 2):
            board.paste(tile, (x, y))
    return board


def make_preview(path, max_side: int = 1600) -> Image.Image:
    """A screen-sized copy of a result, with transparency shown as a checkerboard."""
    with Image.open(path) as opened:
        opened.load()
        image = opened.copy()
    image.thumbnail((max_side, max_side))
    if image.mode in ("RGBA", "LA"):
        image = image.convert("RGBA")
        board = checkerboard(image.size)
        board.alpha_composite(image)
        image = board
    return image.convert("RGB")


def font_sample(path: str | None, color: str) -> Image.Image | None:
    """A short line of text drawn in the chosen font, for the sidebar."""
    try:
        font = ImageFont.truetype(path, 30) if path else None
    except OSError:
        return None
    if font is None:
        from wordcloud import wordcloud as wc_module

        try:
            font = ImageFont.truetype(wc_module.FONT_PATH, 30)
        except (OSError, AttributeError):
            return None
    text = "Word cloud 123"
    left, top, right, bottom = font.getbbox(text)
    image = Image.new("RGBA", (max(1, right - left + 4), max(1, bottom - top + 4)), (0, 0, 0, 0))
    ImageDraw.Draw(image).text((2 - left, 2 - top), text, font=font, fill=color)
    return image


def swatch_hover(color: str) -> str:
    """A slightly darker (or lighter, for dark colors) shade for hover feedback."""
    r, g, b = ImageColor.getrgb(color)[:3]
    factor = 1.25 if (r * 299 + g * 587 + b * 114) / 1000 < 60 else 0.85
    return "#{:02x}{:02x}{:02x}".format(*(min(255, int(c * factor)) for c in (r, g, b)))


def to_hex(color: str) -> str | None:
    try:
        r, g, b = ImageColor.getrgb(color.strip())[:3]
    except (ValueError, AttributeError):
        return None
    return f"#{r:02x}{g:02x}{b:02x}"


# ------------------------------------------------------------ small widgets

class Tooltip:
    """A hint that appears when the mouse rests on a widget."""

    def __init__(self, widget, text: str, delay: int = 500):
        self.widget, self.text, self.delay = widget, text, delay
        self._pending = None
        self._window = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _event=None):
        self._cancel()
        self._pending = self.widget.after(self.delay, self._show)

    def _cancel(self):
        if self._pending:
            self.widget.after_cancel(self._pending)
            self._pending = None

    def _show(self):
        self._pending = None
        if self._window or not self.text or not self.widget.winfo_ismapped():
            return
        x = self.widget.winfo_rootx() + 10
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self._window = window = tkinter.Toplevel(self.widget)
        window.wm_overrideredirect(True)
        window.wm_attributes("-topmost", True)
        tkinter.Label(window, text=self.text, justify="left", wraplength=320,
                      bg="#2f3337", fg="#f1f1f1", padx=9, pady=5,
                      font=("Segoe UI", 9) if sys.platform == "win32" else None).pack()
        window.wm_geometry(f"+{x}+{y}")

    def _hide(self, _event=None):
        self._cancel()
        if self._window:
            self._window.destroy()
            self._window = None


class ColorDialog(customtkinter.CTkToplevel):
    """Pick a color from a swatch, by typing a hex code or name, or with the system picker."""

    def __init__(self, master, title: str, initial: str = "#1f77b4"):
        super().__init__(master)
        self.title(title)
        self.resizable(False, False)
        self.transient(master)
        self.result = None
        initial = to_hex(initial) or "#1f77b4"

        body = customtkinter.CTkFrame(self, fg_color="transparent")
        body.pack(padx=18, pady=18)

        self.preview = customtkinter.CTkFrame(body, height=54, corner_radius=8, fg_color=initial,
                                              border_width=1, border_color=("gray70", "gray35"))
        self.preview.pack(fill="x")

        grid = customtkinter.CTkFrame(body, fg_color="transparent")
        grid.pack(pady=(12, 8))
        for index, color in enumerate(QUICK_COLORS):
            customtkinter.CTkButton(
                grid, text="", width=30, height=30, corner_radius=6, fg_color=color,
                hover_color=swatch_hover(color), border_width=1, border_color=("gray70", "gray35"),
                command=lambda c=color: self._value.set(c),
            ).grid(row=index // 8, column=index % 8, padx=3, pady=3)

        row = customtkinter.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x", pady=(4, 0))
        customtkinter.CTkLabel(row, text="Hex or name").pack(side="left")
        self._value = customtkinter.StringVar(value=initial)
        self.entry = customtkinter.CTkEntry(row, textvariable=self._value, width=130)
        self.entry.pack(side="left", padx=8)
        customtkinter.CTkButton(row, text="More...", width=70, fg_color="transparent",
                                border_width=1, text_color=("gray15", "gray90"),
                                command=self._system_picker).pack(side="left")
        self._default_border = self.entry.cget("border_color")

        buttons = customtkinter.CTkFrame(body, fg_color="transparent")
        buttons.pack(fill="x", pady=(16, 0))
        self.ok_button = customtkinter.CTkButton(buttons, text="OK", width=100, command=self._ok)
        self.ok_button.pack(side="right")
        customtkinter.CTkButton(buttons, text="Cancel", width=100, fg_color="transparent",
                                border_width=1, text_color=("gray15", "gray90"),
                                command=self.destroy).pack(side="right", padx=8)

        self._value.trace_add("write", self._on_change)
        self.bind("<Return>", lambda _e: self._ok())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        # CTkToplevel sets its own icon a moment after opening; ours goes on after it.
        icon = find_asset("assets", "icon.ico")
        if icon and sys.platform == "win32":
            self.after(250, lambda: self.iconbitmap(str(icon)))
        self.after(20, self._grab)

    def _grab(self):
        try:
            self.lift()
            self.focus_force()
            self.grab_set()
            self.entry.focus_set()
        except tkinter.TclError:
            pass  # window already closed

    def _on_change(self, *_):
        color = to_hex(self._value.get())
        if color:
            self.preview.configure(fg_color=color)
            self.entry.configure(border_color=self._default_border)
            self.ok_button.configure(state="normal")
        else:
            self.entry.configure(border_color=ERROR_TEXT)
            self.ok_button.configure(state="disabled")

    def _system_picker(self):
        _, chosen = colorchooser.askcolor(color=to_hex(self._value.get()) or "#ffffff",
                                          parent=self, title=self.title())
        if chosen:
            self._value.set(chosen)

    def _ok(self):
        color = to_hex(self._value.get())
        if color:
            self.result = color
            self.destroy()

    def get(self) -> str | None:
        self.master.wait_window(self)
        return self.result


class _QueueLogHandler(logging.Handler):
    """Forwards warnings raised during a run to the UI thread."""

    def __init__(self, target: queue.Queue):
        super().__init__(level=logging.WARNING)
        self.target = target

    def emit(self, record):
        self.target.put(("note", record.getMessage()))


# --------------------------------------------------------------------- app

_APP_BASES = (customtkinter.CTk, TkinterDnD.DnDWrapper) if TkinterDnD else (customtkinter.CTk,)


class WordcloudApp(*_APP_BASES):
    def __init__(self, open_files=()):
        super().__init__()
        self.base = app_dir()
        self.settings_path = config_dir() / "settings.json"
        self.settings = load_settings(self.settings_path)

        self.title("WordcloudGen")
        self._set_icon()
        self._restore_geometry()
        self.minsize(*MIN_WINDOW)

        self.font_body = customtkinter.CTkFont(size=13)
        self.font_small = customtkinter.CTkFont(size=12)
        self.font_section = customtkinter.CTkFont(size=12, weight="bold")
        self.font_title = customtkinter.CTkFont(size=19, weight="bold")

        # Worker threads must never touch Tk directly, so everything they report
        # comes back through this queue and is handled on the UI thread.
        self._results = queue.Queue()
        self._busy = False
        self._started = 0.0
        self._notes = []
        self._run_language = AUTO_LANGUAGE
        self.last_output = None
        self.last_seed = None
        self.locked_seed = None
        self._preview_source = None
        self._preview_image = None
        self._preview_tip = None
        self._resize_job = None
        self._font_label = DEFAULT_FONT_LABEL
        self._palette_name = "Default"
        self.colors = list(DEFAULT_COLORS)
        self.font_paths = {DEFAULT_FONT_LABEL: None}
        self.palettes = {}
        self.mask_path = None
        self.bg_custom = "#f5efe6"

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._build_header()
        self._build_sidebar()
        self._build_main()
        self._build_statusbar()
        self._apply_settings()
        self._bind_keys()

        self.dnd_enabled = self._enable_drag_and_drop()
        self._show_empty_state()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.report_callback_exception = self._on_unexpected_error

        for path in open_files:
            self.open_path(Path(path))

    # ------------------------------------------------------------ window

    def _set_icon(self):
        try:
            if sys.platform == "win32":
                icon = find_asset("assets", "icon.ico")
                if icon:
                    self.iconbitmap(str(icon))
            else:
                icon = find_asset("assets", "icon.png")
                if icon:
                    self._icon_photo = tkinter.PhotoImage(file=str(icon))
                    self.iconphoto(True, self._icon_photo)
        except tkinter.TclError:
            pass

    def _restore_geometry(self):
        """Reuse last session's window size, but never bigger than the screen.

        CTk sizes are in scaled units, so the screen is converted too: a
        1920x1080 laptop at 150% zoom is only 1280x720 of them, and a window
        taller than that would hide the Generate button.
        """
        scaling = customtkinter.ScalingTracker.get_window_scaling(self)
        screen_w = int(self.winfo_screenwidth() / scaling)
        screen_h = int(self.winfo_screenheight() / scaling)
        width, height = 1240, 800
        match = re.match(r"(\d+)x(\d+)", str(self.settings.get("geometry", "")))
        if match:
            width, height = int(match[1]), int(match[2])
        width = max(MIN_WINDOW[0], min(width, screen_w - 40))
        height = max(MIN_WINDOW[1], min(height, screen_h - 90))  # taskbar and title bar
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 3)
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _enable_drag_and_drop(self) -> bool:
        if TkinterDnD is None:
            return False
        try:
            TkinterDnD._require(self)
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self._on_drop)
            self.dnd_bind("<<DropEnter>>", lambda e: self._drop_highlight(True, e))
            self.dnd_bind("<<DropLeave>>", lambda e: self._drop_highlight(False, e))
        except (RuntimeError, tkinter.TclError) as exc:
            log.warning("Drag and drop is unavailable: %s", exc)
            return False
        return True

    def _bind_keys(self):
        self.bind("<Control-Return>", lambda _e: self.on_generate())
        self.bind("<F5>", lambda _e: self.on_generate())
        self.bind("<Control-o>", lambda _e: self.browse_document())
        self.bind("<Control-s>", lambda _e: self.save_as())
        # In the text box Ctrl+Enter would also type a newline; stop it there.
        self.exclude_box.bind("<Control-Return>", lambda _e: (self.on_generate(), "break")[1])

    # ------------------------------------------------------------ layout

    def _build_header(self):
        header = customtkinter.CTkFrame(self, corner_radius=0, height=58,
                                        fg_color=("gray95", "gray14"))
        header.grid(row=0, column=0, columnspan=2, sticky="ew")
        header.grid_columnconfigure(1, weight=1)

        icon = find_asset("assets", "icon.png")
        if icon:
            with Image.open(icon) as picture:
                logo = picture.copy()
            self._logo = customtkinter.CTkImage(logo, logo, size=(30, 30))
            customtkinter.CTkLabel(header, text="", image=self._logo).grid(
                row=0, column=0, padx=(18, 10), pady=12)

        title = customtkinter.CTkFrame(header, fg_color="transparent")
        title.grid(row=0, column=1, sticky="w")
        customtkinter.CTkLabel(title, text="WordcloudGen", font=self.font_title).pack(side="left")
        customtkinter.CTkLabel(title, text=f"  v{__version__}", font=self.font_small,
                               text_color=MUTED).pack(side="left", pady=(4, 0))

        self.appearance_var = customtkinter.StringVar(value="System")
        customtkinter.CTkSegmentedButton(
            header, values=["Light", "Dark", "System"], variable=self.appearance_var,
            command=customtkinter.set_appearance_mode, font=self.font_small,
        ).grid(row=0, column=2, padx=18)

    def _build_sidebar(self):
        sidebar = customtkinter.CTkFrame(self, corner_radius=0, width=400)
        sidebar.grid(row=1, column=0, sticky="nsw")
        sidebar.grid_propagate(False)
        sidebar.grid_rowconfigure(0, weight=1)
        sidebar.grid_columnconfigure(0, weight=1)

        scroll = customtkinter.CTkScrollableFrame(sidebar, fg_color="transparent")
        scroll.grid(row=0, column=0, sticky="nsew", padx=(6, 0), pady=(6, 0))
        scroll.grid_columnconfigure(0, weight=1)
        self._sections = scroll

        self._build_document_section(self._section("Document"))
        self._build_look_section(self._section("Look"))
        self._build_words_section(self._section("Words"))
        self._build_output_section(self._section("Save to"))

        bottom = customtkinter.CTkFrame(sidebar, fg_color="transparent")
        bottom.grid(row=1, column=0, sticky="ew", padx=16, pady=14)
        bottom.grid_columnconfigure(0, weight=1)
        self.generate_button = customtkinter.CTkButton(
            bottom, text="Generate", height=46,
            font=customtkinter.CTkFont(size=16, weight="bold"), command=self.on_generate)
        self.generate_button.grid(row=0, column=0, sticky="ew")
        customtkinter.CTkLabel(bottom, text="Ctrl+Enter", font=self.font_small,
                               text_color=MUTED).grid(row=1, column=0, pady=(4, 0))

    def _section(self, title: str) -> customtkinter.CTkFrame:
        frame = customtkinter.CTkFrame(self._sections, fg_color="transparent")
        frame.pack(fill="x", padx=10, pady=(10, 4))
        frame.grid_columnconfigure(0, weight=1)
        customtkinter.CTkLabel(frame, text=title.upper(), font=self.font_section,
                               text_color=MUTED, anchor="w").grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 4))
        frame.next_row = 1
        return frame

    def _field(self, section, label: str, hint: str | None = None) -> int:
        """Add a field label to a section and return the grid row for its control."""
        row = section.next_row
        widget = customtkinter.CTkLabel(section, text=label, font=self.font_body, anchor="w")
        widget.grid(row=row, column=0, columnspan=3, sticky="w", pady=(6, 2))
        if hint:
            Tooltip(widget, hint)
        section.next_row = row + 2
        return row + 1

    def _secondary_button(self, parent, text, command, width=90):
        return customtkinter.CTkButton(
            parent, text=text, width=width, font=self.font_body, fg_color="transparent",
            border_width=1, border_color=("gray70", "gray35"),
            hover_color=("gray85", "gray25"), text_color=("gray10", "gray90"), command=command)

    def _build_document_section(self, s):
        row = self._field(s, "File", "A PDF, a Word .docx or a plain text file")
        self.doc_var = customtkinter.StringVar()
        self.doc_entry = customtkinter.CTkEntry(s, textvariable=self.doc_var, font=self.font_body)
        self.doc_entry.grid(row=row, column=0, columnspan=2, sticky="ew")
        self._secondary_button(s, "Browse...", self.browse_document).grid(
            row=row, column=2, padx=(8, 0))
        self.doc_info = customtkinter.CTkLabel(s, text="", font=self.font_small,
                                               text_color=MUTED, anchor="w")
        self.doc_info.grid(row=row + 1, column=0, columnspan=3, sticky="w")
        s.next_row += 1
        self.doc_var.trace_add("write", lambda *_: self._update_doc_info())
        self._keep_end_visible(self.doc_var, self.doc_entry)

        row = self._field(s, "Language", "Used to drop common words like 'the' and 'and'. "
                                         "Detection works well for anything longer than a paragraph.")
        self.lang_var = customtkinter.StringVar(value=AUTO_LABEL)
        customtkinter.CTkOptionMenu(
            s, values=[AUTO_LABEL] + [lang.title() for lang in SUPPORTED_LANGUAGES],
            variable=self.lang_var, font=self.font_body, dynamic_resizing=False,
        ).grid(row=row, column=0, columnspan=3, sticky="ew")

    def _build_look_section(self, s):
        # Font
        row = self._field(s, "Font")
        self.font_var = customtkinter.StringVar(value=DEFAULT_FONT_LABEL)
        fonts_dir = find_asset("fonts")
        if fonts_dir:
            found = sorted(p for p in fonts_dir.iterdir() if p.suffix.lower() in (".ttf", ".otf"))
            for path in found:
                name = font_display_name(path)
                if name in self.font_paths:
                    name = f"{name} ({path.stem})"
                self.font_paths[name] = str(path)
        self.font_menu = customtkinter.CTkOptionMenu(
            s, variable=self.font_var, font=self.font_body, dynamic_resizing=False,
            command=self._on_font_choice)
        self.font_menu.grid(row=row, column=0, columnspan=3, sticky="ew")
        self._refresh_font_menu()
        self.font_preview = customtkinter.CTkLabel(s, text="", height=40)
        self.font_preview.grid(row=row + 1, column=0, columnspan=3, sticky="w", pady=(4, 0))
        s.next_row += 1

        # Palette
        row = self._field(s, "Colors", "Each word gets a random color from this palette")
        self.palette_var = customtkinter.StringVar()
        self.palette_menu = customtkinter.CTkOptionMenu(
            s, variable=self.palette_var, font=self.font_body, dynamic_resizing=False,
            command=self._on_palette_choice)
        self.palette_menu.grid(row=row, column=0, columnspan=2, sticky="ew")
        self._secondary_button(s, "Save...", self.save_palette).grid(row=row, column=2, padx=(8, 0))
        self.swatch_frame = customtkinter.CTkFrame(s, fg_color="transparent")
        self.swatch_frame.grid(row=row + 1, column=0, columnspan=3, sticky="w", pady=(6, 0))
        s.next_row += 1
        self._refresh_palettes()

        # Background
        row = self._field(s, "Background")
        self.bg_var = customtkinter.StringVar(value="White")
        bg_row = customtkinter.CTkFrame(s, fg_color="transparent")
        bg_row.grid(row=row, column=0, columnspan=3, sticky="ew")
        bg_row.grid_columnconfigure(0, weight=1)
        customtkinter.CTkSegmentedButton(
            bg_row, values=[*BACKGROUNDS, CUSTOM_BACKGROUND], variable=self.bg_var,
            font=self.font_small, command=self._on_background_choice,
        ).grid(row=0, column=0, sticky="ew")
        self.bg_swatch = customtkinter.CTkButton(
            bg_row, text="", width=32, height=28, corner_radius=6, border_width=1,
            fg_color="transparent", hover_color=("gray85", "gray25"),
            border_color=("gray65", "gray35"), command=self.pick_background)
        self.bg_swatch.grid(row=0, column=1, padx=(8, 0))
        Tooltip(self.bg_swatch, "Pick a custom background color")

        # Size
        row = self._field(s, "Size", "Output size in pixels")
        self.size_var = customtkinter.StringVar(value=next(iter(SIZE_PRESETS)))
        customtkinter.CTkOptionMenu(
            s, values=[*SIZE_PRESETS, CUSTOM_LABEL], variable=self.size_var,
            font=self.font_body, dynamic_resizing=False, command=self._on_size_choice,
        ).grid(row=row, column=0, columnspan=3, sticky="ew")
        dims = customtkinter.CTkFrame(s, fg_color="transparent")
        dims.grid(row=row + 1, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        dims.grid_columnconfigure((0, 2), weight=1)
        self.width_var = customtkinter.StringVar(value="1920")
        self.height_var = customtkinter.StringVar(value="1080")
        self.width_entry = customtkinter.CTkEntry(dims, textvariable=self.width_var,
                                                  font=self.font_body, justify="center")
        self.width_entry.grid(row=0, column=0, sticky="ew")
        customtkinter.CTkLabel(dims, text="×", font=self.font_body).grid(row=0, column=1, padx=8)
        self.height_entry = customtkinter.CTkEntry(dims, textvariable=self.height_var,
                                                   font=self.font_body, justify="center")
        self.height_entry.grid(row=0, column=2, sticky="ew")
        swap = self._secondary_button(dims, "Rotate", self.swap_size, width=70)
        swap.grid(row=0, column=3, padx=(8, 0))
        Tooltip(swap, "Swap width and height")
        self._entry_border = self.width_entry.cget("border_color")
        for var in (self.width_var, self.height_var):
            var.trace_add("write", lambda *_: self._on_size_typed())
        s.next_row += 1

        # Shape
        row = self._field(s, "Shape (optional)",
                          "Fill a shape instead of a rectangle. Words go where the image is "
                          "dark; white or transparent areas stay empty.")
        shape_row = customtkinter.CTkFrame(s, fg_color="transparent")
        shape_row.grid(row=row, column=0, columnspan=3, sticky="ew")
        shape_row.grid_columnconfigure(1, weight=1)
        self._secondary_button(shape_row, "Choose image...", self.browse_mask, width=130).grid(
            row=0, column=0)
        self.mask_label = customtkinter.CTkLabel(shape_row, text="None", font=self.font_small,
                                                 text_color=MUTED, anchor="w")
        self.mask_label.grid(row=0, column=1, sticky="ew", padx=8)
        self.mask_clear = customtkinter.CTkButton(
            shape_row, text="✕", width=28, height=28, fg_color="transparent",
            hover_color=("gray85", "gray25"), text_color=MUTED, command=lambda: self.set_mask(None))
        Tooltip(self.mask_clear, "Remove the shape")

    def _build_words_section(self, s):
        row = self._field(s, "Leave out", "Words or phrases to drop, separated by commas")
        self.exclude_box = customtkinter.CTkTextbox(s, height=64, font=self.font_body, wrap="word",
                                                    border_width=1)
        self.exclude_box.grid(row=row, column=0, columnspan=3, sticky="ew")
        customtkinter.CTkLabel(s, text="Separate with commas. Phrases like et al work too.",
                               font=self.font_small, text_color=MUTED, anchor="w").grid(
            row=row + 1, column=0, columnspan=3, sticky="w")
        s.next_row += 1

        row = self._field(s, "Number of words")
        count_row = customtkinter.CTkFrame(s, fg_color="transparent")
        count_row.grid(row=row, column=0, columnspan=3, sticky="ew")
        count_row.grid_columnconfigure(0, weight=1)
        self.max_words_var = customtkinter.IntVar(value=200)
        customtkinter.CTkSlider(count_row, from_=20, to=1000, number_of_steps=98,
                                variable=self.max_words_var,
                                command=lambda _v: self._update_word_count()).grid(
            row=0, column=0, sticky="ew")
        self.max_words_label = customtkinter.CTkLabel(count_row, text="200", width=44,
                                                      font=self.font_body)
        self.max_words_label.grid(row=0, column=1, padx=(8, 0))

        options = customtkinter.CTkFrame(s, fg_color="transparent")
        options.grid(row=s.next_row, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        s.next_row += 1
        self.collocations_var = customtkinter.BooleanVar(value=False)
        phrases = customtkinter.CTkCheckBox(options, text="Allow two-word phrases",
                                            variable=self.collocations_var, font=self.font_body)
        phrases.pack(anchor="w")
        Tooltip(phrases, "Keep pairs that often appear together, like 'new york', as one entry")
        self.lock_var = customtkinter.BooleanVar(value=False)
        lock = customtkinter.CTkSwitch(options, text="Keep this layout", variable=self.lock_var,
                                       font=self.font_body, command=self._on_lock_toggle)
        lock.pack(anchor="w", pady=(10, 0))
        Tooltip(lock, "Reuse the arrangement from the last run, so you can try other colors "
                      "without reshuffling the words")

    def _build_output_section(self, s):
        row = self._field(s, "Folder", "Every image is saved here with a timestamped name")
        self.output_var = customtkinter.StringVar(
            value=str(default_output_dir(self.base, getattr(sys, "frozen", False))))
        output_entry = customtkinter.CTkEntry(s, textvariable=self.output_var, font=self.font_body)
        output_entry.grid(row=row, column=0, columnspan=2, sticky="ew")
        self._keep_end_visible(self.output_var, output_entry)
        self._secondary_button(s, "Change...", self.browse_output).grid(
            row=row, column=2, padx=(8, 0))

    def _build_main(self):
        main = customtkinter.CTkFrame(self, fg_color="transparent")
        main.grid(row=1, column=1, sticky="nsew", padx=18, pady=(14, 8))
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(1, weight=1)

        # Error banner: hidden until something goes wrong.
        self.banner = customtkinter.CTkFrame(main, fg_color=ERROR_FILL, corner_radius=8)
        self.banner.grid_columnconfigure(0, weight=1)
        self.banner_text = customtkinter.CTkLabel(self.banner, text="", text_color=ERROR_TEXT,
                                                  font=self.font_body, justify="left",
                                                  anchor="w", wraplength=640)
        self.banner_text.grid(row=0, column=0, sticky="ew", padx=14, pady=10)
        customtkinter.CTkButton(self.banner, text="✕", width=28, height=28,
                                fg_color="transparent", text_color=ERROR_TEXT,
                                hover_color=ERROR_FILL, command=self.hide_error).grid(
            row=0, column=1, padx=6)

        self.preview_box = customtkinter.CTkFrame(main, corner_radius=12, border_width=2,
                                                  fg_color=("gray90", "gray16"),
                                                  border_color=("gray90", "gray16"))
        self.preview_box.grid(row=1, column=0, sticky="nsew")
        self._box_border = ("gray90", "gray16")
        self.preview_label = customtkinter.CTkLabel(
            self.preview_box, text="", font=customtkinter.CTkFont(size=15),
            text_color=MUTED, justify="center")
        self.preview_label.place(relx=0.5, rely=0.5, anchor="center")
        self.preview_box.bind("<Configure>", self._on_preview_resize)
        self.preview_label.bind("<Button-1>", lambda _e: self._on_preview_click())
        self.preview_box.bind("<Button-1>", lambda _e: self._on_preview_click())

        # Most frequent words, each one click away from the exclusion list.
        self.words_row = customtkinter.CTkFrame(main, fg_color="transparent")
        self.words_row.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        customtkinter.CTkLabel(
            self.words_row, text="Most frequent words. Click one to leave it out.",
            font=self.font_small, text_color=MUTED, anchor="w").pack(anchor="w")
        self.chips = customtkinter.CTkFrame(self.words_row, fg_color="transparent", height=32)
        self.chips.pack(anchor="w", fill="x")
        self.chips.bind("<Configure>", self._schedule_chip_layout)
        self._chip_widgets = []
        self._chip_job = None
        self.words_row.grid_remove()  # nothing to show until the first run

        actions = customtkinter.CTkFrame(main, fg_color="transparent")
        actions.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        self.open_button = self._secondary_button(actions, "Open image", self.open_image, 120)
        self.save_button = self._secondary_button(actions, "Save as...", self.save_as, 120)
        self.reveal_button = self._secondary_button(actions, "Show in folder",
                                                    self.reveal_image, 130)
        for button in (self.open_button, self.save_button, self.reveal_button):
            button.pack(side="left", padx=(0, 8))
            button.configure(state="disabled")

    def _build_statusbar(self):
        bar = customtkinter.CTkFrame(self, corner_radius=0, height=30,
                                     fg_color=("gray95", "gray14"))
        bar.grid(row=2, column=0, columnspan=2, sticky="ew")
        bar.grid_columnconfigure(0, weight=1)
        self.status = customtkinter.CTkLabel(bar, text="Ready", font=self.font_small,
                                             text_color=MUTED, anchor="w")
        self.status.grid(row=0, column=0, sticky="ew", padx=16, pady=4)
        self.progress = customtkinter.CTkProgressBar(bar, width=180, mode="indeterminate")
        self.progress.grid(row=0, column=1, padx=16)
        self.progress.grid_remove()

    # ---------------------------------------------------------- settings

    def _apply_settings(self):
        """Restore last session. Every value is checked; stale ones are skipped."""
        s = self.settings

        appearance = s.get("appearance")
        if appearance in ("Light", "Dark", "System"):
            self.appearance_var.set(appearance)
            customtkinter.set_appearance_mode(appearance)

        doc = s.get("document")
        if isinstance(doc, str) and Path(doc).is_file():
            self.doc_var.set(doc)

        lang = s.get("language")
        if lang == AUTO_LANGUAGE:
            self.lang_var.set(AUTO_LABEL)
        elif isinstance(lang, str) and lang in SUPPORTED_LANGUAGES:
            self.lang_var.set(lang.title())

        font = s.get("font")
        if isinstance(font, str) and Path(font).is_file():
            self._select_font_path(font)
        self._update_font_preview()

        colors = clean_palette(s.get("colors")) if isinstance(s.get("colors"), list) else []
        name = s.get("palette")
        if colors:
            self._set_colors(colors, name if name in self.palettes else CUSTOM_LABEL)
        else:
            self._select_palette(next(iter(self.palettes), None))

        bg_custom = s.get("background_color")
        if isinstance(bg_custom, str) and to_hex(bg_custom):
            self.bg_custom = to_hex(bg_custom)
        bg = s.get("background")
        self.bg_var.set(bg if bg in (*BACKGROUNDS, CUSTOM_BACKGROUND) else "White")
        self._update_bg_swatch()

        try:
            width, height = check_size(s.get("width", 1920), s.get("height", 1080))
        except ValueError:
            width, height = 1920, 1080
        self.width_var.set(str(width))
        self.height_var.set(str(height))

        mask = s.get("mask")
        if isinstance(mask, str) and Path(mask).is_file():
            self.set_mask(mask)
        else:
            self.set_mask(None)

        exclude = s.get("exclude")
        if isinstance(exclude, str):
            self.exclude_box.insert("1.0", exclude)

        try:
            self.max_words_var.set(min(1000, max(20, int(s.get("max_words", 200)))))
        except (TypeError, ValueError):
            pass
        self._update_word_count()
        self.collocations_var.set(bool(s.get("collocations", False)))

        output = s.get("output_dir")
        if isinstance(output, str) and output.strip():
            self.output_var.set(output)

    def _collect_settings(self) -> dict:
        return {
            "appearance": self.appearance_var.get(),
            "document": self.doc_var.get().strip(),
            "language": self._language(),
            "font": self.font_paths.get(self.font_var.get()),
            "palette": self.palette_var.get(),
            "colors": list(self.colors),
            "background": self.bg_var.get(),
            "background_color": self.bg_custom,
            "width": self.width_var.get().strip(),
            "height": self.height_var.get().strip(),
            "mask": self.mask_path,
            "exclude": self.exclude_box.get("1.0", "end-1c"),
            "max_words": self.max_words_var.get(),
            "collocations": self.collocations_var.get(),
            "output_dir": self.output_var.get().strip(),
            "geometry": self.geometry(),
        }

    def on_close(self):
        save_settings(self.settings_path, self._collect_settings())
        self.destroy()

    # ------------------------------------------------------------ document

    def browse_document(self):
        current = Path(self.doc_var.get().strip() or ".")
        patterns = " ".join(f"*{ext}" for ext in DOCUMENT_EXTENSIONS)
        path = filedialog.askopenfilename(
            parent=self, title="Choose a document",
            initialdir=str(current.parent) if current.parent.is_dir() else None,
            filetypes=[("Documents", patterns), ("PDF", "*.pdf"), ("Word", "*.docx"),
                       ("Text", "*.txt *.md"), ("All files", "*.*")])
        if path:
            self.doc_var.set(path)
            self._show_end(self.doc_entry)

    def _update_doc_info(self):
        path = Path(self.doc_var.get().strip())
        if not self.doc_var.get().strip():
            text = "Or drop a file anywhere on this window" if getattr(
                self, "dnd_enabled", False) else ""
        elif path.is_file():
            text = f"{path.name}, {self._human_size(path.stat().st_size)}"
        else:
            text = "File not found"
        self.doc_info.configure(text=text)

    @staticmethod
    def _human_size(size: int) -> str:
        for unit in ("bytes", "KB", "MB"):
            if size < 1024 or unit == "MB":
                return f"{size:.0f} {unit}" if unit == "bytes" else f"{size:.1f} {unit}"
            size /= 1024
        return f"{size} bytes"

    @staticmethod
    def _show_end(entry):
        """Scroll a path entry so the file name, not the drive letter, is visible."""
        try:
            entry._entry.xview_moveto(1.0)
        except (AttributeError, tkinter.TclError):
            pass

    def _keep_end_visible(self, variable, entry):
        # The entry may not have its final width yet when the value is set, so
        # scroll a moment later, and again once the window first appears.
        variable.trace_add("write", lambda *_: self.after(50, lambda: self._show_end(entry)))
        entry.bind("<Map>", lambda _e: self.after(50, lambda: self._show_end(entry)), add="+")

    def _language(self) -> str:
        value = self.lang_var.get()
        return AUTO_LANGUAGE if value == AUTO_LABEL else value.lower()

    def open_path(self, path: Path):
        """Route a dropped or command-line file to the setting it belongs to."""
        if path.is_dir():
            self.set_status("That is a folder. Drop a single file instead.", error=True)
            return
        if not path.is_file():
            self.set_status(f"Can't find {path}", error=True)
            return
        suffix = path.suffix.lower()
        if suffix in (".ttf", ".otf"):
            self._select_font_path(str(path))
            self._update_font_preview()
            self.set_status(f"Font set to {font_display_name(path)}")
        elif suffix == ".json":
            self._load_palette_file(path)
        elif suffix in IMAGE_EXTENSIONS:
            self.set_mask(str(path))
            self.set_status(f"Shape set to {path.name}")
        else:
            self.doc_var.set(str(path))
            self._show_end(self.doc_entry)
            self.hide_error()
            self.set_status(f"Ready to read {path.name}. Press Generate.")

    def _on_drop(self, event):
        self._drop_highlight(False)
        for raw in self.tk.splitlist(event.data):
            self.open_path(Path(raw))
        return event.action

    def _drop_highlight(self, on: bool, event=None):
        color = customtkinter.ThemeManager.theme["CTkButton"]["fg_color"] if on else self._box_border
        self.preview_box.configure(border_color=color)
        return event.action if event is not None else None

    # ---------------------------------------------------------------- font

    def _refresh_font_menu(self):
        self.font_menu.configure(values=[*self.font_paths, OTHER_FONT_LABEL])

    def _select_font_path(self, path: str):
        for name, known in self.font_paths.items():
            if known and Path(known) == Path(path):
                self.font_var.set(name)
                return
        name = font_display_name(Path(path))
        if name in self.font_paths:
            name = f"{name} ({Path(path).name})"
        self.font_paths[name] = path
        self._refresh_font_menu()
        self.font_var.set(name)

    def _on_font_choice(self, choice):
        if choice == OTHER_FONT_LABEL:
            # Put the menu back on the current font in case the dialog is cancelled.
            self.font_var.set(self._font_label)
            path = filedialog.askopenfilename(parent=self, title="Choose a font",
                                              filetypes=[("Fonts", "*.ttf *.otf")])
            if not path:
                return
            try:
                ImageFont.truetype(path, 12)
            except OSError:
                self.show_error(f"{Path(path).name} isn't a font this app can read. "
                                "Pick a .ttf or .otf file.")
                return
            self._select_font_path(path)
        self._update_font_preview()

    def _update_font_preview(self):
        self._font_label = self.font_var.get()
        path = self.font_paths.get(self._font_label)
        light, dark = font_sample(path, "#1b1b1b"), font_sample(path, "#ececec")
        if light is None:
            self.font_preview.configure(image=None, text="(preview unavailable)")
            return
        ratio = 26 / light.height
        size = (max(1, int(light.width * ratio)), 26)
        self._font_image = customtkinter.CTkImage(light, dark, size=size)
        self.font_preview.configure(image=self._font_image, text="")

    # ------------------------------------------------------------- palette

    def _refresh_palettes(self):
        """List bundled presets, then any the user saved."""
        self.palettes = {}
        for folder in (find_asset("colors"), user_palette_dir()):
            if not folder or not folder.is_dir():
                continue
            for path in sorted(folder.glob("*.json")):
                if is_autosaved_palette(path):
                    continue
                name = palette_display_name(path)
                if name in self.palettes:
                    continue
                self.palettes[name] = path
        # Default first: it is what a new user expects to see selected.
        if "Default" in self.palettes:
            self.palettes = {"Default": self.palettes.pop("Default"), **self.palettes}
        self.palette_menu.configure(values=[*self.palettes, OPEN_PALETTE_LABEL])

    def _select_palette(self, name):
        path = self.palettes.get(name)
        self._set_colors(load_colors(path) if path else list(DEFAULT_COLORS),
                         name if path else "Default")

    def _on_palette_choice(self, choice):
        if choice == OPEN_PALETTE_LABEL:
            self.palette_var.set(self._palette_name)
            path = filedialog.askopenfilename(parent=self, title="Open a palette",
                                              initialdir=str(find_asset("colors") or "."),
                                              filetypes=[("Palette", "*.json")])
            if path:
                self._load_palette_file(Path(path))
            return
        self._select_palette(choice)

    def _load_palette_file(self, path: Path):
        colors = load_colors(path)
        name = palette_display_name(path)
        if name not in self.palettes:
            self.palettes[name] = path
            self.palette_menu.configure(values=[*self.palettes, OPEN_PALETTE_LABEL])
        self._set_colors(colors, name)
        self.set_status(f"Loaded the {name} palette ({len(colors)} colors)")

    def _set_colors(self, colors, name):
        self.colors = list(colors)[:MAX_PALETTE] or list(DEFAULT_COLORS)
        self._palette_name = name
        self.palette_var.set(name)
        self._render_swatches()

    def _mark_palette_custom(self):
        self._palette_name = CUSTOM_LABEL
        self.palette_var.set(CUSTOM_LABEL)

    def _render_swatches(self):
        for child in self.swatch_frame.winfo_children():
            child.destroy()
        for index, color in enumerate(self.colors):
            swatch = customtkinter.CTkButton(
                self.swatch_frame, text="", width=34, height=30, corner_radius=6,
                fg_color=color, hover_color=swatch_hover(color), border_width=1,
                border_color=("gray65", "gray35"),
                command=lambda i=index: self._swatch_menu(i))
            swatch.grid(row=index // SWATCH_COLUMNS, column=index % SWATCH_COLUMNS, padx=2, pady=2)
            Tooltip(swatch, f"{color}\nClick to change or remove")
        if len(self.colors) < MAX_PALETTE:
            index = len(self.colors)
            add = customtkinter.CTkButton(
                self.swatch_frame, text="+", width=34, height=30, corner_radius=6,
                fg_color="transparent", border_width=1, border_color=("gray65", "gray35"),
                hover_color=("gray85", "gray25"), text_color=("gray20", "gray85"),
                font=self.font_body, command=self.add_color)
            add.grid(row=index // SWATCH_COLUMNS, column=index % SWATCH_COLUMNS, padx=2, pady=2)
            Tooltip(add, "Add a color")

    def _swatch_menu(self, index):
        menu = tkinter.Menu(self, tearoff=False)
        menu.add_command(label="Change color...", command=lambda: self.change_color(index))
        if index > 0:
            menu.add_command(label="Move left", command=lambda: self._move_color(index, -1))
        if index < len(self.colors) - 1:
            menu.add_command(label="Move right", command=lambda: self._move_color(index, 1))
        menu.add_separator()
        menu.add_command(label="Remove", command=lambda: self.remove_color(index),
                         state="normal" if len(self.colors) > 1 else "disabled")
        try:
            menu.tk_popup(self.winfo_pointerx(), self.winfo_pointery())
        finally:
            menu.grab_release()

    def add_color(self):
        color = ColorDialog(self, "Add a color", self.colors[-1] if self.colors else "#1f77b4").get()
        if color:
            self.colors.append(color)
            self._mark_palette_custom()
            self._render_swatches()

    def change_color(self, index):
        color = ColorDialog(self, "Change color", self.colors[index]).get()
        if color:
            self.colors[index] = color
            self._mark_palette_custom()
            self._render_swatches()

    def _move_color(self, index, step):
        other = index + step
        self.colors[index], self.colors[other] = self.colors[other], self.colors[index]
        self._mark_palette_custom()
        self._render_swatches()

    def remove_color(self, index):
        if len(self.colors) <= 1:
            return
        del self.colors[index]
        self._mark_palette_custom()
        self._render_swatches()

    def save_palette(self):
        folder = user_palette_dir()
        folder.mkdir(parents=True, exist_ok=True)
        path = filedialog.asksaveasfilename(
            parent=self, title="Save this palette", initialdir=str(folder),
            initialfile="my_colors.json", defaultextension=".json",
            filetypes=[("Palette", "*.json")])
        if not path:
            return
        try:
            write_palette(self.colors, path)
        except OSError as exc:
            self.show_error(f"Couldn't save the palette: {exc.strerror or exc}")
            return
        self._refresh_palettes()
        name = palette_display_name(Path(path))
        self.palettes.setdefault(name, Path(path))
        self.palette_menu.configure(values=[*self.palettes, OPEN_PALETTE_LABEL])
        self._palette_name = name
        self.palette_var.set(name)
        self.set_status(f"Palette saved as {Path(path).name}")

    # ---------------------------------------------------------- background

    def _on_background_choice(self, choice):
        if choice == CUSTOM_BACKGROUND:
            self.pick_background()
        self._update_bg_swatch()

    def pick_background(self):
        color = ColorDialog(self, "Background color", self.bg_custom).get()
        if color:
            self.bg_custom = color
            self.bg_var.set(CUSTOM_BACKGROUND)
        elif self.bg_var.get() == CUSTOM_BACKGROUND and not self.bg_custom:
            self.bg_var.set("White")
        self._update_bg_swatch()

    def _update_bg_swatch(self):
        """Show the background that will actually be used, checkerboard for none."""
        choice = self.bg_var.get()
        if choice == "Transparent":
            picture = checkerboard((24, 24), cell=6).convert("RGB")
        else:
            color = self.bg_custom if choice == CUSTOM_BACKGROUND else BACKGROUNDS.get(choice)
            picture = Image.new("RGB", (24, 24), to_hex(color or "white") or "#ffffff")
        self._bg_image = customtkinter.CTkImage(picture, picture, size=(20, 20))
        self.bg_swatch.configure(image=self._bg_image)

    def _background(self) -> str:
        choice = self.bg_var.get()
        return self.bg_custom if choice == CUSTOM_BACKGROUND else BACKGROUNDS.get(choice, "white")

    # ---------------------------------------------------------------- size

    def _on_size_choice(self, choice):
        if choice in SIZE_PRESETS:
            width, height = SIZE_PRESETS[choice]
            self._setting_size = True
            self.width_var.set(str(width))
            self.height_var.set(str(height))
            self._setting_size = False
            self._on_size_typed()

    def _on_size_typed(self):
        if getattr(self, "_setting_size", False):
            return
        try:
            size = check_size(self.width_var.get(), self.height_var.get())
        except ValueError:
            size = None
        valid = size is not None
        for entry in (self.width_entry, self.height_entry):
            entry.configure(border_color=self._entry_border if valid else ERROR_TEXT)
        match = next((name for name, preset in SIZE_PRESETS.items() if preset == size), CUSTOM_LABEL)
        self.size_var.set(match)

    def swap_size(self):
        width, height = self.width_var.get(), self.height_var.get()
        self._setting_size = True
        self.width_var.set(height)
        self._setting_size = False
        self.height_var.set(width)

    # --------------------------------------------------------------- shape

    def browse_mask(self):
        patterns = " ".join(f"*{ext}" for ext in IMAGE_EXTENSIONS)
        path = filedialog.askopenfilename(parent=self, title="Choose a shape image",
                                          filetypes=[("Images", patterns), ("All files", "*.*")])
        if path:
            self.set_mask(path)

    def set_mask(self, path):
        self.mask_path = path
        if path:
            self.mask_label.configure(text=Path(path).name, text_color=("gray10", "gray90"))
            self.mask_clear.grid(row=0, column=2)
        else:
            self.mask_label.configure(text="None", text_color=MUTED)
            self.mask_clear.grid_remove()

    # --------------------------------------------------------------- words

    def _update_word_count(self):
        self.max_words_label.configure(text=str(self.max_words_var.get()))

    def _on_lock_toggle(self):
        self.locked_seed = self.last_seed if self.lock_var.get() else None
        if self.lock_var.get() and self.last_seed is None:
            self.set_status("The next layout you generate will be kept.")

    def exclude_word(self, word, chip):
        current = normalize_exclusions(self.exclude_box.get("1.0", "end-1c"))
        if word not in current:
            text = self.exclude_box.get("1.0", "end-1c").rstrip().rstrip(",")
            self.exclude_box.delete("1.0", "end")
            self.exclude_box.insert("1.0", f"{text}, {word}" if text else word)
        chip.configure(state="disabled", text=word)
        self.set_status(f"'{word}' will be left out next time. Press Generate to update.")

    def _show_top_words(self, words):
        for chip in self._chip_widgets:
            chip.destroy()
        self._chip_widgets = []
        if not words:
            self.words_row.grid_remove()
            return
        self.words_row.grid()
        for word in words[:TOP_WORDS]:
            chip = customtkinter.CTkButton(
                self.chips, text=f"{word}  ✕", height=26, corner_radius=13, width=10,
                font=self.font_small, fg_color=("gray86", "gray24"),
                hover_color=("gray78", "gray30"), text_color=("gray10", "gray90"),
                text_color_disabled=("gray60", "gray45"))
            chip.configure(command=lambda w=word, c=chip: self.exclude_word(w, c))
            Tooltip(chip, f"Leave '{word}' out next time")
            self._chip_widgets.append(chip)
        self._schedule_chip_layout()

    def _schedule_chip_layout(self, _event=None):
        if self._chip_job:
            self.after_cancel(self._chip_job)
        self._chip_job = self.after(40, self._layout_chips)

    def _layout_chips(self):
        """Show as many chips as fit on one line; a clipped chip looks broken."""
        self._chip_job = None
        room = self.chips.winfo_width()
        gap = int(6 * customtkinter.ScalingTracker.get_widget_scaling(self.chips))
        used, fits = 0, True
        for chip in self._chip_widgets:
            need = chip.winfo_reqwidth() + gap
            fits = fits and used + need <= room
            if fits:
                if not chip.winfo_manager():
                    chip.pack(side="left", padx=(0, 6), pady=(4, 0))
                used += need
            else:
                chip.pack_forget()

    # -------------------------------------------------------------- output

    def browse_output(self):
        path = filedialog.askdirectory(parent=self, title="Choose where images are saved",
                                       initialdir=self.output_var.get() or None)
        if path:
            self.output_var.set(path)

    def open_image(self):
        if self.last_output and Path(self.last_output).is_file():
            open_in_system(Path(self.last_output))
        else:
            self.set_status("The image has been moved or deleted.", error=True)

    def reveal_image(self):
        if self.last_output and Path(self.last_output).is_file():
            reveal_in_folder(Path(self.last_output))
        else:
            folder = Path(self.output_var.get() or ".")
            if folder.is_dir():
                open_in_system(folder)

    def save_as(self):
        if not self.last_output or not Path(self.last_output).is_file():
            self.set_status("Generate a word cloud first, then save it.", error=True)
            return
        source = Path(self.last_output)
        path = filedialog.asksaveasfilename(
            parent=self, title="Save the word cloud as", initialfile=source.name,
            initialdir=str(source.parent), defaultextension=".png",
            filetypes=[("PNG image", "*.png"), ("JPEG image", "*.jpg"), ("WebP image", "*.webp")])
        if not path:
            return
        try:
            saved = export_image(source, path)
        except (WordcloudError, OSError) as exc:
            self.show_error(str(exc))
            return
        note = ""
        if Path(path).suffix.lower() in (".jpg", ".jpeg") and self._background() == "transparent":
            note = " JPEG can't be transparent, so the background is white."
        self.set_status(f"Saved a copy to {saved}.{note}", ok=True)

    # ---------------------------------------------------------- generating

    def on_generate(self):
        if self._busy:
            return
        self.hide_error()

        document = self.doc_var.get().strip().strip('"')
        if not document:
            self.show_error("Choose a document first: press Browse, or drop a file on the window.")
            return
        if not Path(document).is_file():
            self.show_error(f"Can't find the document:\n{document}")
            return
        try:
            width, height = check_size(self.width_var.get(), self.height_var.get())
        except WordcloudError as exc:
            self.show_error(str(exc))
            return

        output_dir = self.output_var.get().strip() or str(
            default_output_dir(self.base, getattr(sys, "frozen", False)))
        self.output_var.set(output_dir)

        if self.lock_var.get() and self.locked_seed is not None:
            seed = self.locked_seed
        else:
            seed = random.randrange(2**31)
        self.last_seed = seed
        if self.lock_var.get() and self.locked_seed is None:
            self.locked_seed = seed

        settings = {
            "input_path": document,
            "lang": self._language(),
            "width": width,
            "height": height,
            "background": self._background(),
            "font": self.font_paths.get(self.font_var.get()),
            "exclude_words": self.exclude_box.get("1.0", "end-1c"),
            "output_dir": output_dir,
            "colors": list(self.colors),
            "max_words": self.max_words_var.get(),
            "collocations": self.collocations_var.get(),
            "mask": self.mask_path,
            "seed": seed,
        }
        self._run_language = settings["lang"]
        self._set_busy(True)
        self._notes = []
        self._started = time.perf_counter()
        threading.Thread(target=self._worker, args=(settings,), daemon=True).start()
        self.after(80, self._poll_results)

    def _worker(self, settings):
        """Runs off the UI thread, so it only ever talks to the result queue."""
        handler = _QueueLogHandler(self._results)
        log.addHandler(handler)
        try:
            result = generate_word_cloud(
                progress=lambda message: self._results.put(("progress", message)), **settings)
            preview = make_preview(result.path)
        except WordcloudError as exc:
            self._results.put(("error", str(exc)))
        except FileNotFoundError as exc:
            self._results.put(("error", str(exc)))
        except MemoryError:
            self._results.put(("error", "Ran out of memory. Try a smaller size or fewer words."))
        except OSError as exc:
            self._results.put(("error", f"Couldn't read or write a file: {exc}"))
        except Exception as exc:  # a bug: log it, then tell the user where
            log.exception("Generation failed")
            self._results.put(("crash", exc))
        else:
            self._results.put(("ok", (result, preview)))
        finally:
            log.removeHandler(handler)

    def _poll_results(self):
        """Handle everything the worker has reported so far, on the UI thread."""
        while True:
            try:
                kind, payload = self._results.get_nowait()
            except queue.Empty:
                break
            if kind == "progress":
                self.set_status(f"{payload}...")
            elif kind == "note":
                self._notes.append(payload)
            elif kind == "ok":
                self._on_success(*payload)
                return
            elif kind == "error":
                self._set_busy(False)
                self.show_error(payload)
                return
            elif kind == "crash":
                self._set_busy(False)
                self._report_crash(payload)
                return
        self.after(80, self._poll_results)

    def _set_busy(self, busy: bool):
        self._busy = busy
        self.generate_button.configure(state="disabled" if busy else "normal",
                                       text="Generating..." if busy else "Generate")
        if busy:
            self.progress.grid()
            self.progress.start()
        else:
            self.progress.stop()
            self.progress.grid_remove()

    def _on_success(self, result, preview):
        self._set_busy(False)
        self.last_output = result.path
        self._preview_source = preview
        self._render_preview()
        self._show_top_words(result.words)
        for button in (self.open_button, self.save_button, self.reveal_button):
            button.configure(state="normal")

        elapsed = time.perf_counter() - self._started
        message = f"Saved {Path(result.path).name} in {elapsed:.1f} s"
        if self._run_language == AUTO_LANGUAGE:
            message += f". Language: {result.language.title()}"
        if self._notes:
            message += f". Note: {self._notes[-1]}"
        self.set_status(message, ok=True)
        save_settings(self.settings_path, self._collect_settings())

    # ------------------------------------------------------------- preview

    def _show_empty_state(self):
        if self.dnd_enabled:
            text = "Drop a PDF, Word or text file here\nor press Browse to choose one"
        else:
            text = "Choose a PDF, Word or text file on the left,\nthen press Generate"
        self._update_doc_info()
        self.preview_label.configure(text=text, image=None)

    def _on_preview_click(self):
        if self._preview_source is None:
            self.browse_document()
        else:
            self.open_image()

    def _on_preview_resize(self, _event=None):
        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(60, self._render_preview)

    def _render_preview(self):
        self._resize_job = None
        if self._preview_source is None:
            return
        scaling = customtkinter.ScalingTracker.get_widget_scaling(self.preview_box)
        room_w = self.preview_box.winfo_width() / scaling - 32
        room_h = self.preview_box.winfo_height() / scaling - 32
        if room_w < 20 or room_h < 20:
            return
        image = self._preview_source
        ratio = min(room_w / image.width, room_h / image.height)
        size = (max(1, int(image.width * ratio)), max(1, int(image.height * ratio)))
        if self._preview_image is None:
            self._preview_image = customtkinter.CTkImage(image, image, size=size)
        else:
            self._preview_image.configure(light_image=image, dark_image=image, size=size)
        self.preview_label.configure(image=self._preview_image, text="")
        if not self._preview_tip:
            self._preview_tip = Tooltip(self.preview_label, "Click to open the full-size image")

    # -------------------------------------------------------------- status

    def set_status(self, text: str, error: bool = False, ok: bool = False):
        color = ERROR_TEXT if error else OK_TEXT if ok else MUTED
        self.status.configure(text=text, text_color=color)

    def show_error(self, message: str):
        self.banner_text.configure(text=message)
        self.banner.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self.set_status("Couldn't generate the word cloud. See the message above.", error=True)

    def hide_error(self):
        self.banner.grid_remove()

    def _report_crash(self, exc):
        log_file = config_dir() / "wordcloudgen.log"
        self.show_error("Something went wrong inside the app. Sorry about that.")
        messagebox.showerror(
            "WordcloudGen hit a problem",
            f"{exc.__class__.__name__}: {exc}\n\nThe details were saved to:\n{log_file}\n\n"
            "If it keeps happening, please open an issue on GitHub and attach that file.",
            parent=self)

    def _on_unexpected_error(self, exc_type, exc, tb):
        """Tk calls this for exceptions in callbacks, which would otherwise vanish."""
        log.error("Unhandled error in the UI:\n%s", "".join(traceback.format_exception(exc_type, exc, tb)))
        self._report_crash(exc)


# --------------------------------------------------------------- entry points

def configure_logging() -> None:
    """Log to a file the user can attach to a bug report, and to stderr if there is one."""
    log.setLevel(logging.INFO)
    log.propagate = False
    try:
        folder = config_dir()
        folder.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            folder / "wordcloudgen.log", maxBytes=512_000, backupCount=1, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(handler)
    except OSError:
        pass
    if sys.stderr is not None:  # a windowed .exe has no console at all
        log.addHandler(logging.StreamHandler())


def close_splash() -> None:
    """Dismiss the loading image the one-file .exe shows while it unpacks."""
    try:
        import pyi_splash

        pyi_splash.close()
    except Exception:
        pass


def selftest() -> int:
    """Render a word cloud without opening a window.

    Used by CI to prove a packaged build actually works: launching the GUI
    only proves that importing it succeeded.
    """
    import tempfile

    sample = find_asset("input", "demo.txt")
    if sample is None:
        print("selftest: bundled input/demo.txt is missing")
        return 1

    try:
        with tempfile.TemporaryDirectory() as tmp:
            result = generate_word_cloud(input_path=sample, lang=AUTO_LANGUAGE,
                                         width=400, height=300, output_dir=tmp, seed=1)
            ok = Path(result.path).stat().st_size > 0 and result.language == "english"
    except Exception as exc:
        print(f"selftest: FAILED - {exc.__class__.__name__}: {exc}")
        return 1

    print("selftest: OK" if ok else "selftest: produced an empty image")
    return 0 if ok else 1


def main():
    if "--selftest" in sys.argv:
        close_splash()
        raise SystemExit(selftest())

    configure_logging()
    if sys.platform == "win32":
        try:  # group the taskbar button under our icon, not python.exe's
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("biagio11.WordcloudGen")
        except (AttributeError, OSError):
            pass

    files = [arg for arg in sys.argv[1:] if not arg.startswith("-")]
    app = WordcloudApp(open_files=files)
    app.after(0, close_splash)
    app.mainloop()


if __name__ == "__main__":
    main()
