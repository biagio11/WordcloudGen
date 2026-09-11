# Changelog

All notable changes to this project are listed here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
project uses [semantic versioning](https://semver.org/).

## [1.1.0] - 2026-09-11

A redesigned desktop app, a single-file Windows download, and a lot of work on what
happens when things go wrong.

### Added

- **Single-file Windows app.** Releases now include a portable `.exe` next to the zip,
  plus a `SHA256SUMS.txt`. The executables carry an icon and proper version details.
- **Drag and drop.** Drop a document on the window to open it. Fonts, palettes and shape
  images can be dropped too and go to the right setting.
- **Word documents.** `.docx` files are read directly, without Word installed.
- **Language detection**, on by default in both the app and the command line. Eighteen
  languages are supported, up from nine.
- **Shapes.** Fill an image instead of a rectangle (`--mask` on the command line).
- **Most frequent words** under the preview. Click one to leave it out of the next run.
- **Keep this layout**, to try other colors without the words moving.
- Presets for fonts (listed by their real names, with a preview), palettes, backgrounds
  and common image sizes.
- **Save as** PNG, JPEG or WebP, plus *Open image* and *Show in folder*.
- The app remembers its settings between sessions.
- A color picker that accepts hex codes and color names.
- Keyboard shortcuts: Ctrl+O, Ctrl+Enter or F5, Ctrl+S.
- A log file at `%APPDATA%\WordcloudGen\wordcloudgen.log`, and a clear message pointing to
  it if the app ever hits an unexpected error.
- Command line: the document can be given as a plain argument
  (`wordcloud_gen.py report.pdf`), `--lang` accepts any capitalisation, and `--output`
  writes to an exact file.

### Changed

- The desktop app has a new layout: settings in a sidebar, and a large preview that
  resizes with the window and shows transparency as a checkerboard.
- The packaged app saves to `Pictures\WordcloudGen` by default instead of next to the
  `.exe`, which may be a read-only or temporary folder.
- Palettes are only saved when you ask. The app used to write a new
  `colors_<timestamp>.json` on every run.
- Errors appear inside the window instead of in a pop-up, and the confirmation pop-up after
  every successful run is gone.
- Lemmatization only runs on English text. WordNet is English-only and could turn words in
  other languages into unrelated English ones.
- Single letters are no longer drawn.
- The GUI depends only on `customtkinter` and `tkinterdnd2`. `CTkColorPicker`,
  `CTkMessagebox`, `CTkToolTip` and `CTkListbox` are no longer needed.
- `colors/colors.json` is now `colors/bright_colors.json`, and the auto-saved duplicate of
  the pastel palette is gone.

### Fixed

- Every setting is checked before the document is read, and problems come back as plain
  explanations: an unknown color, a size that would take minutes to render, a file that
  isn't a font, a folder that can't be written to.
- Scanned PDFs, password-protected PDFs and damaged files are reported as such instead of
  failing with an internal error.
- Text files saved as UTF-16 (Notepad's "Unicode") or with a UTF-8 BOM are read correctly,
  and binary files are refused instead of producing garbage.
- Two runs in the same second no longer overwrite each other's image.
- Palette files with invalid colors, or holding a bare list, no longer crash the app.
- With the NLTK data missing and no internet, the pipeline falls back to simpler word
  splitting and a built-in stopword list instead of failing. Downloads also time out
  instead of hanging.
- Excluding a plural now removes the singular as well, and phrases are still excluded
  when they are split across two lines.
- Words at the end of one PDF page no longer merge with the first word of the next.

## [1.0.0] - 2026-09-09

The first packaged release. The command line tool works again, the desktop app was
rebuilt around a live preview, and there is a downloadable Windows executable.

### Added

- **Standalone Windows app.** `build_exe.py` and `wordcloud_gen_GUI.spec` produce a
  self-contained build with the NLTK data included, so it works offline without Python.
  Pushing a tag builds it on GitHub.
- **Live preview in the app**, instead of a separate matplotlib window.
- **Rendering off the UI thread**, with a progress bar, so the window no longer freezes on
  long PDFs.
- **A shared engine**, `wordcloudgen/core.py`, used by both front ends.
- **A test suite** (`pytest`) and CI on Windows and Linux with Python 3.10, 3.11 and 3.12.
- New command line options: `--seed`, `--output-dir`, `--max-words`, `--collocations`,
  `--no-show` and `--version`.
- `--selftest` on the packaged app, so a build can be checked without a display.
- A light/dark theme switch, an *Open output folder* button, and a *Reset* button for the
  palette.
- `requirements.txt` and `requirements-dev.txt` for installing without conda.
- `CONTRIBUTING.md`, this changelog, and a README with a gallery.

### Fixed

- **The command line crashed on every run.** `main()` used an undefined `color_file`
  instead of `args.color_file`.
- **`--exclude-words` didn't match the README**, which said `--exclude`. Both work now.
- **The app ignored the colors you picked** unless a palette file had been loaded first.
- **Excluded words came back after lemmatization.** Excluding `pain` left `pains` in.
- **Multi-word exclusions removed unrelated text.** Phrases are now matched on word
  boundaries.
- **Transparent backgrounds** now use the wordcloud library's own alpha support.
- **A non-numeric width or height** crashed the app; it is now reported.
- **The output folder is created when missing** instead of failing at save time.
- A document that ends up with no words left says so, instead of raising an obscure error.
- An unknown `--lang` falls back to English with a warning instead of crashing.
- Removed a stray debug `print`, an unused `import fitz` and a duplicated import.
- The command line no longer sorts words alphabetically before rendering, which had been
  scrambling two-word phrases.

### Changed

- The app saves to `output/` next to itself by default, instead of refusing to run until a
  folder was chosen.
- Word clouds use single words by default; `--collocations` turns phrases back on.
- `setup_nltk.py` reports what is missing and exits with an error code on failure.
- Sample images moved from `output/` to `docs/gallery/`, and `output/` is git-ignored.
- `.gitignore` now covers build artifacts, virtual environments and generated files. It
  used to be a single `*.` pattern that matched nothing useful.

[1.1.0]: https://github.com/biagio11/WordcloudGen/releases/tag/v1.1.0
[1.0.0]: https://github.com/biagio11/WordcloudGen/releases/tag/v1.0.0
