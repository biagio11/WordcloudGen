"""Graphical front end for WordcloudGen (customtkinter)."""

import os
import queue
import subprocess
import sys
import threading
import tkinter
from pathlib import Path

import customtkinter
from CTkColorPicker import AskColor
from CTkListbox import CTkListbox
from CTkMessagebox import CTkMessagebox
from CTkToolTip import CTkToolTip
from customtkinter import filedialog

# Make the app importable no matter where it is launched from, including from
# inside a PyInstaller bundle.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from wordcloudgen import __version__  # noqa: E402
from wordcloudgen.core import (  # noqa: E402
    DEFAULT_COLORS,
    SUPPORTED_LANGUAGES,
    generate_word_cloud,
    load_colors,
    save_colors,
)

customtkinter.set_appearance_mode("System")
customtkinter.set_default_color_theme("green")

PREVIEW_W, PREVIEW_H = 420, 260


def app_dir() -> Path:
    """Writable folder for output and saved palettes.

    When frozen by PyInstaller this is the folder holding the .exe, so results
    land next to the app instead of inside a temporary extraction directory.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def resource_dir() -> Path:
    """Read-only folder holding the bundled colors/ and fonts/ samples.

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


class WordcloudApp(customtkinter.CTk):
    def __init__(self):
        super().__init__()
        self.title(f"WordcloudGen {__version__}")
        self.geometry("1080x760")
        self.minsize(940, 680)

        self.base = app_dir()
        self.colors_file_path = None
        self.last_output = None
        self._preview_image = None  # keep a reference or Tk drops the image
        # Worker threads must never touch Tk directly, so results come back
        # through this queue and are drained by _poll_results on the UI thread.
        self._results = queue.Queue()

        self.font_normal = customtkinter.CTkFont(size=14)
        self.font_title = customtkinter.CTkFont(size=22, weight="bold")

        self.grid_columnconfigure(0, weight=3, minsize=520)
        self.grid_columnconfigure(1, weight=2, minsize=380)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()
        self._build_settings_panel()
        self._build_preview_panel()
        self._load_default_palette()

    # ---------------------------------------------------------------- layout

    def _build_header(self):
        header = customtkinter.CTkFrame(self, corner_radius=0, height=64)
        header.grid(row=0, column=0, columnspan=2, sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        customtkinter.CTkLabel(
            header, text="WordcloudGen", font=self.font_title
        ).grid(row=0, column=0, padx=24, pady=(14, 0), sticky="w")
        customtkinter.CTkLabel(
            header,
            text="Turn a PDF or text file into a word cloud.",
            font=self.font_normal,
            text_color=("gray40", "gray65"),
        ).grid(row=1, column=0, padx=24, pady=(0, 14), sticky="w")

        self.appearance_menu = customtkinter.CTkOptionMenu(
            header, values=["System", "Light", "Dark"], width=110,
            font=self.font_normal, command=customtkinter.set_appearance_mode,
        )
        self.appearance_menu.grid(row=0, column=1, rowspan=2, padx=24, pady=12)
        CTkToolTip(self.appearance_menu, "Switch between light and dark theme")

    def _build_settings_panel(self):
        panel = customtkinter.CTkScrollableFrame(self, label_text="Settings",
                                                 label_font=self.font_normal)
        panel.grid(row=1, column=0, padx=(16, 8), pady=16, sticky="nsew")
        panel.grid_columnconfigure(1, weight=1)
        row = 0

        # --- source file
        self.source_var = customtkinter.StringVar(value="")
        self._label(panel, row, "Document:", "Pick the PDF or .txt file to read")
        self.source_entry = customtkinter.CTkEntry(
            panel, textvariable=self.source_var, font=self.font_normal,
            placeholder_text="Select a .pdf or .txt file")
        self.source_entry.grid(row=row, column=1, padx=8, pady=8, sticky="ew")
        customtkinter.CTkButton(panel, text="Browse", width=90, font=self.font_normal,
                                command=self.select_source).grid(
            row=row, column=2, padx=(0, 8), pady=8)
        row += 1

        # --- language
        self._label(panel, row, "Language:", "Language of the document, used for stopwords")
        self.language_var = customtkinter.StringVar(value="english")
        customtkinter.CTkOptionMenu(panel, values=SUPPORTED_LANGUAGES, font=self.font_normal,
                                    variable=self.language_var).grid(
            row=row, column=1, columnspan=2, padx=8, pady=8, sticky="ew")
        row += 1

        # --- size
        self._label(panel, row, "Width x Height:", "Output image size in pixels")
        size_frame = customtkinter.CTkFrame(panel, fg_color="transparent")
        size_frame.grid(row=row, column=1, columnspan=2, padx=8, pady=8, sticky="ew")
        size_frame.grid_columnconfigure((0, 2), weight=1)
        self.width_entry = customtkinter.CTkEntry(size_frame, font=self.font_normal)
        self.width_entry.insert(0, "1920")
        self.width_entry.grid(row=0, column=0, sticky="ew")
        customtkinter.CTkLabel(size_frame, text="x", font=self.font_normal).grid(
            row=0, column=1, padx=10)
        self.height_entry = customtkinter.CTkEntry(size_frame, font=self.font_normal)
        self.height_entry.insert(0, "1080")
        self.height_entry.grid(row=0, column=2, sticky="ew")
        row += 1

        # --- background
        self._label(panel, row, "Background:", "A color name, a hex value, or 'transparent'")
        self.background_entry = customtkinter.CTkEntry(panel, font=self.font_normal)
        self.background_entry.insert(0, "transparent")
        self.background_entry.grid(row=row, column=1, padx=8, pady=8, sticky="ew")
        customtkinter.CTkButton(panel, text="Pick", width=90, font=self.font_normal,
                                command=self.select_background_color).grid(
            row=row, column=2, padx=(0, 8), pady=8)
        row += 1

        # --- font
        self.font_var = customtkinter.StringVar(value="")
        self._label(panel, row, "Font:", "Optional .ttf or .otf font file")
        customtkinter.CTkEntry(panel, textvariable=self.font_var, font=self.font_normal,
                               placeholder_text="Default font").grid(
            row=row, column=1, padx=8, pady=8, sticky="ew")
        customtkinter.CTkButton(panel, text="Browse", width=90, font=self.font_normal,
                                command=self.select_font).grid(
            row=row, column=2, padx=(0, 8), pady=8)
        row += 1

        # --- excluded words
        self._label(panel, row, "Exclude:", "Words or phrases to leave out, separated by commas")
        self.exclude_textbox = customtkinter.CTkTextbox(panel, height=70,
                                                        font=self.font_normal, wrap="word")
        self.exclude_textbox.grid(row=row, column=1, columnspan=2, padx=8, pady=8, sticky="ew")
        row += 1

        # --- palette
        self._label(panel, row, "Colors:", "Palette the words are drawn from")
        self.color_list = CTkListbox(panel, font=self.font_normal, height=150)
        self.color_list.grid(row=row, column=1, padx=8, pady=8, sticky="ew")
        buttons = customtkinter.CTkFrame(panel, fg_color="transparent")
        buttons.grid(row=row, column=2, padx=(0, 8), pady=8, sticky="new")
        for text, command in (("Add", self.add_color),
                              ("Remove", self.remove_color),
                              ("Load", self.load_colors_from_file),
                              ("Reset", self._load_default_palette)):
            customtkinter.CTkButton(buttons, text=text, width=90, font=self.font_normal,
                                    command=command).pack(fill="x", pady=(0, 6))
        row += 1

        # --- output folder
        self.output_var = customtkinter.StringVar(value=str(self.base / "output"))
        self._label(panel, row, "Output folder:", "Where the PNG is saved")
        customtkinter.CTkEntry(panel, textvariable=self.output_var,
                               font=self.font_normal).grid(
            row=row, column=1, padx=8, pady=8, sticky="ew")
        customtkinter.CTkButton(panel, text="Browse", width=90, font=self.font_normal,
                                command=self.select_output_folder).grid(
            row=row, column=2, padx=(0, 8), pady=8)

    def _build_preview_panel(self):
        panel = customtkinter.CTkFrame(self)
        panel.grid(row=1, column=1, padx=(8, 16), pady=16, sticky="nsew")
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(1, weight=1)

        customtkinter.CTkLabel(panel, text="Preview", font=self.font_normal).grid(
            row=0, column=0, padx=16, pady=(14, 6), sticky="w")

        self.preview_label = customtkinter.CTkLabel(
            panel, text="Your word cloud will appear here.", font=self.font_normal,
            text_color=("gray45", "gray60"), fg_color=("gray92", "gray20"),
            corner_radius=8, width=PREVIEW_W, height=PREVIEW_H)
        self.preview_label.grid(row=1, column=0, padx=16, pady=6, sticky="nsew")

        self.status_label = customtkinter.CTkLabel(panel, text="Ready",
                                                   font=self.font_normal,
                                                   text_color=("gray45", "gray60"),
                                                   wraplength=PREVIEW_W)
        self.status_label.grid(row=2, column=0, padx=16, pady=6, sticky="ew")

        self.progress = customtkinter.CTkProgressBar(panel)
        self.progress.set(0)
        self.progress.grid(row=3, column=0, padx=16, pady=(0, 10), sticky="ew")

        self.generate_button = customtkinter.CTkButton(
            panel, text="Generate Word Cloud", height=46,
            font=customtkinter.CTkFont(size=17, weight="bold"),
            command=self.on_generate)
        self.generate_button.grid(row=4, column=0, padx=16, pady=(0, 8), sticky="ew")

        self.open_button = customtkinter.CTkButton(
            panel, text="Open output folder", height=36, font=self.font_normal,
            fg_color="transparent", border_width=1,
            text_color=("gray20", "gray85"), command=self.open_output_folder)
        self.open_button.grid(row=5, column=0, padx=16, pady=(0, 16), sticky="ew")

    def _label(self, parent, row, text, tooltip):
        label = customtkinter.CTkLabel(parent, text=text, font=self.font_normal, anchor="w")
        label.grid(row=row, column=0, padx=(14, 6), pady=8, sticky="w")
        CTkToolTip(label, tooltip)
        return label

    # --------------------------------------------------------------- actions

    def select_source(self):
        path = filedialog.askopenfilename(
            title="Select a document",
            filetypes=[("Documents", "*.pdf *.txt"), ("PDF files", "*.pdf"),
                       ("Text files", "*.txt"), ("All files", "*.*")])
        if path:
            self.source_var.set(path)

    def select_font(self):
        fonts = find_asset("fonts")
        path = filedialog.askopenfilename(
            title="Select a font", filetypes=[("Font files", "*.ttf *.otf")],
            initialdir=str(fonts) if fonts else None)
        if path:
            self.font_var.set(path)

    def select_output_folder(self):
        path = filedialog.askdirectory(title="Select the output folder")
        if path:
            self.output_var.set(path)

    def select_background_color(self):
        color = AskColor(title="Choose background color").get()
        if color:
            self.background_entry.delete(0, tkinter.END)
            self.background_entry.insert(0, color)

    def add_color(self):
        color = AskColor(title="Choose color").get()
        if color:
            self.color_list.insert(tkinter.END, color)

    def remove_color(self):
        selected = self.color_list.curselection()
        if selected is None:
            return
        indices = (selected,) if isinstance(selected, int) else selected
        for index in sorted(indices, reverse=True):
            self.color_list.delete(index)

    def _set_palette(self, colors):
        self.color_list.delete("all")
        for color in colors:
            self.color_list.insert(tkinter.END, color)

    def _load_default_palette(self):
        default_file = find_asset("colors", "default_colors.json")
        self._set_palette(load_colors(default_file))
        self.colors_file_path = str(default_file) if default_file else None

    def load_colors_from_file(self):
        palettes = find_asset("colors")
        path = filedialog.askopenfilename(
            title="Select a palette", filetypes=[("JSON files", "*.json")],
            initialdir=str(palettes) if palettes else None)
        if not path:
            return
        self._set_palette(load_colors(path))
        self.colors_file_path = path

    def open_output_folder(self):
        folder = Path(self.output_var.get() or self.base / "output")
        folder.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(folder)
        elif sys.platform == "darwin":
            subprocess.run(["open", str(folder)], check=False)
        else:
            subprocess.run(["xdg-open", str(folder)], check=False)

    # ------------------------------------------------------------ generation

    def _current_colors(self):
        colors = self.color_list.get("all") or []
        return [c for c in colors if c] or list(DEFAULT_COLORS)

    def _error(self, message):
        self.status_label.configure(text=message)
        CTkMessagebox(title="Error", message=message, icon="warning",
                      font=customtkinter.CTkFont(size=15))

    def on_generate(self):
        source = self.source_var.get().strip()
        if not source:
            self._error("Please select a PDF or text file first.")
            return
        if not Path(source).is_file():
            self._error(f"File not found:\n{source}")
            return

        try:
            width, height = int(self.width_entry.get()), int(self.height_entry.get())
            if width <= 0 or height <= 0:
                raise ValueError
        except ValueError:
            self._error("Width and height must be positive whole numbers.")
            return

        output_dir = self.output_var.get().strip() or str(self.base / "output")
        exclude = [w.strip() for w in
                   self.exclude_textbox.get("1.0", "end-1c").split(",") if w.strip()]
        colors = self._current_colors()

        # Persist the palette so the same run can be reproduced from the CLI.
        try:
            saved = save_colors(colors, self.base / "colors")
            if saved:
                self.colors_file_path = saved
        except OSError as exc:
            print(f"Could not save the palette: {exc}")

        self.generate_button.configure(state="disabled", text="Generating...")
        self.status_label.configure(text="Reading and processing the document...")
        self.progress.configure(mode="indeterminate")
        self.progress.start()

        settings = {
            "input_path": source,
            "lang": self.language_var.get(),
            "width": width,
            "height": height,
            "background": self.background_entry.get().strip() or "white",
            "font": self.font_var.get().strip() or None,
            "exclude_words": exclude,
            "output_dir": output_dir,
            "colors": colors,
        }
        threading.Thread(target=self._worker, args=(settings,), daemon=True).start()
        self.after(100, self._poll_results)

    def _worker(self, settings):
        """Runs off the UI thread, so it only touches the result queue."""
        try:
            _, filename = generate_word_cloud(**settings)
        except Exception as exc:  # surfaced to the user in _on_failure
            self._results.put(("error", exc))
        else:
            self._results.put(("ok", filename))

    def _poll_results(self):
        """Drain the worker queue on the UI thread."""
        try:
            status, payload = self._results.get_nowait()
        except queue.Empty:
            self.after(100, self._poll_results)
            return

        if status == "ok":
            self._on_success(payload)
        else:
            self._on_failure(payload)

    def _finish(self):
        self.progress.stop()
        self.progress.configure(mode="determinate")
        self.progress.set(0)
        self.generate_button.configure(state="normal", text="Generate Word Cloud")

    def _on_success(self, filename):
        self._finish()
        self.last_output = filename
        self.status_label.configure(text=f"Saved to {filename}")
        self._show_preview(filename)
        CTkMessagebox(title="Done", message=f"Word cloud saved as\n{filename}",
                      icon="check", font=customtkinter.CTkFont(size=15))

    def _on_failure(self, exc):
        self._finish()
        self._error(str(exc) or exc.__class__.__name__)

    def _show_preview(self, filename):
        try:
            from PIL import Image
        except ImportError:
            return

        with Image.open(filename) as opened:
            image = opened.copy()
        # Flatten transparency onto white so the preview stays readable.
        if image.mode == "RGBA":
            background = Image.new("RGBA", image.size, (255, 255, 255, 255))
            image = Image.alpha_composite(background, image).convert("RGB")

        ratio = min(PREVIEW_W / image.width, PREVIEW_H / image.height)
        size = (max(1, int(image.width * ratio)), max(1, int(image.height * ratio)))
        self._preview_image = customtkinter.CTkImage(light_image=image, dark_image=image,
                                                     size=size)
        self.preview_label.configure(image=self._preview_image, text="")


def selftest() -> int:
    """Render a word cloud without opening a window.

    Used by CI to prove a packaged build actually works - launching the GUI
    only proves that importing it succeeded.
    """
    import tempfile

    sample = find_asset("input", "demo.txt")
    if sample is None:
        print("selftest: bundled input/demo.txt is missing")
        return 1

    try:
        with tempfile.TemporaryDirectory() as tmp:
            _, filename = generate_word_cloud(
                input_path=sample, width=400, height=300, output_dir=tmp, seed=1)
            ok = Path(filename).stat().st_size > 0
    except Exception as exc:
        print(f"selftest: FAILED - {exc.__class__.__name__}: {exc}")
        return 1

    print("selftest: OK" if ok else "selftest: produced an empty image")
    return 0 if ok else 1


def main():
    if "--selftest" in sys.argv:
        raise SystemExit(selftest())
    WordcloudApp().mainloop()


if __name__ == "__main__":
    main()
