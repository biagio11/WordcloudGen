# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project uses [semantic versioning](https://semver.org/).

## [1.0.0] - 2026-09-09

The first packaged release. The command line tool is fixed, the desktop app has been
rebuilt around a live preview, and there is now a downloadable Windows executable.

### Added

- **Standalone Windows app.** `build_exe.py` plus `wordcloud_gen_GUI.spec` produce a
  self-contained build with the NLTK corpora included, so it works offline and needs no
  Python install. Tagging a release builds and publishes it automatically.
- **Live preview in the app.** Generated clouds appear in the window instead of opening a
  separate matplotlib pop-up.
- **Rendering off the UI thread**, with a progress bar, so the window no longer freezes on
  long PDFs.
- **A shared engine**, `wordcloudgen/core.py`, used by both front ends.
- **A test suite** (`pytest`) and CI on Windows and Linux across Python 3.10–3.12.
- New CLI options: `--seed` for reproducible output, `--output-dir`, `--max-words`,
  `--collocations`, `--no-show`, and `--version`.
- `--selftest` on the packaged app, so a build can be verified without a display.
- Light/dark theme switch, an *Open output folder* button, and a *Reset* button for the
  palette.
- `requirements.txt` / `requirements-dev.txt` for installing without conda.
- `CONTRIBUTING.md`, this changelog, and a rewritten README with a gallery.

### Fixed

- **The CLI crashed on every run.** `main()` referenced an undefined `color_file` instead
  of `args.color_file`, raising `NameError` before anything was rendered.
- **`--exclude-words` did not match the documented flag.** The README showed `--exclude`;
  both spellings now work.
- **The app ignored colors you picked.** Palettes were only saved when a palette file had
  already been loaded from disk, so a freshly built one was silently dropped and the
  defaults were used instead.
- **Excluded words came back after lemmatization.** Excluding `pain` left `pains` in the
  cloud, because filtering happened before the words were lemmatized.
- **Multi-word exclusions removed unrelated text.** Phrases are now matched on word
  boundaries.
- **Transparent backgrounds** are produced through the wordcloud library's own alpha
  handling rather than an `rgba(...)` string.
- **A non-numeric width or height** raised an unhandled `ValueError` from the app; it is
  now reported in the interface.
- **The output folder is created when missing** instead of failing at save time.
- A document that reduces to nothing now reports why, rather than raising an opaque error
  from the rendering library.
- An unknown `--lang` falls back to English with a warning instead of crashing.
- Removed a stray `print(preprocess_text)` debug line that printed a function object on
  every run, an unused `import fitz`, and a duplicated `WordCloud` import.
- The CLI no longer sorts tokens alphabetically before rendering, which had been
  scrambling any two-word phrases.

### Changed

- The GUI defaults its output folder to `output/` next to the app instead of refusing to
  run until one is chosen.
- Word clouds are single words by default; pass `--collocations` for two-word phrases.
- `setup_nltk.py` reports what is missing and exits non-zero on failure, instead of
  swallowing errors.
- Sample images moved from `output/` to `docs/gallery/`; `output/` is now for your own
  results and is git-ignored.
- `.gitignore` covers build artifacts, virtual environments and generated files — it was
  previously a single ineffective `*.` pattern.

[1.0.0]: https://github.com/biagio11/WordcloudGen/releases/tag/v1.0.0
