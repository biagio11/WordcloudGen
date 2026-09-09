<div align="center">

# WordcloudGen

**Turn any PDF or text file into a word cloud — from a desktop app or the command line.**

[![CI](https://github.com/biagio11/WordcloudGen/actions/workflows/ci.yml/badge.svg)](https://github.com/biagio11/WordcloudGen/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/biagio11/WordcloudGen?label=download)](https://github.com/biagio11/WordcloudGen/releases/latest)
[![Python](https://img.shields.io/badge/python-3.10%20%E2%80%93%203.12-blue)](https://www.python.org/)
[![License: CC BY-NC-SA 4.0](https://img.shields.io/badge/license-CC%20BY--NC--SA%204.0-lightgrey)](LICENSE)

<img src="docs/gallery/script-southland.png" alt="A word cloud rendered in a flowing script font" width="720">

</div>

---

## What it does

Point WordcloudGen at a document and it will:

1. **Extract** the text — from a PDF (via PyMuPDF) or a plain `.txt` file.
2. **Clean** it — lowercase, tokenize, lemmatize, and strip stopwords in your document's language.
3. **Render** a word cloud in the size, palette, font and background you choose.
4. **Save** it as a timestamped PNG, with real alpha if you pick a transparent background.

Two front ends share one engine, so both behave identically: a **desktop app** with a live preview, and a **CLI** for scripting and batch work.

---

## Gallery

Every image below comes from the same paragraph of sample text in [`input/demo.txt`](input/demo.txt) — only the font, palette and background changed.

| | |
|:-:|:-:|
| <img src="docs/gallery/classic.png" alt="Default palette on white" width="400"> | <img src="docs/gallery/vibrant-dark.png" alt="Vibrant palette on a dark background" width="400"> |
| `default_colors.json` · white | `vibrant_colors.json` · `#101820` |
| <img src="docs/gallery/earthy-timeless.png" alt="Earthy palette in a serif font" width="400"> | <img src="docs/gallery/pastel-night.png" alt="Pastel palette on a midnight background" width="400"> |
| `earthy_colors.json` · Timeless | `pastel_colors.json` · Quicksand |

---

## Get it

### Option 1 — Download the app (Windows, no Python needed)

Grab the latest `WordcloudGen-vX.Y.Z-windows-x64.zip` from the
**[Releases page](https://github.com/biagio11/WordcloudGen/releases/latest)**, unzip it
anywhere, and run **`WordcloudGen.exe`**.

> Windows SmartScreen may warn about an unsigned app the first time.
> Choose **More info → Run anyway**.

Generated images land in an `output/` folder next to the executable.

### Option 2 — Run from source

```bash
git clone https://github.com/biagio11/WordcloudGen.git
cd WordcloudGen
```

<details open>
<summary><b>With pip (any OS)</b></summary>

```bash
python -m venv .venv
# Windows:        .venv\Scripts\activate
# macOS / Linux:  source .venv/bin/activate

pip install -r requirements.txt
python setup_nltk.py
```

</details>

<details>
<summary><b>With conda</b></summary>

```bash
conda env create -f environment.yml
conda activate wordcloud-env
python setup_nltk.py
```

After the first time, `conda activate wordcloud-env` is all you need.

</details>

`setup_nltk.py` downloads the NLTK corpora (tokenizers, stopwords, WordNet). It runs
automatically on first use too — this just gets it out of the way up front.

---

## Use it

### The desktop app

```bash
python wordcloud_gen_GUI.py
```

<div align="center">
<img src="docs/screenshot-gui.png" alt="The WordcloudGen desktop app, showing the settings panel and a rendered preview" width="860">
</div>

Pick a document, adjust anything you like, and press **Generate Word Cloud**. The result
appears in the preview panel and is saved to your output folder. Rendering happens on a
background thread, so the window stays responsive on long PDFs.

### The command line

```bash
python wordcloud_gen.py --txt input/demo.txt
```

A fuller example:

```bash
python wordcloud_gen.py \
  --pdf paper.pdf \
  --lang english \
  --width 2560 --height 1440 \
  --background transparent \
  --font "fonts/Quicksand_Light.otf" \
  --color_file colors/vibrant_colors.json \
  --exclude-words figure table "et al" \
  --seed 42
```

| Option | Default | What it does |
|---|---|---|
| `--pdf` / `--txt` | *required* | The source document (exactly one of the two). |
| `--lang` | `english` | Language used for the stopword list. |
| `--width` / `--height` | `1920` / `1080` | Output size in pixels. |
| `--background` | `white` | Color name, hex value, or `transparent` for real alpha. |
| `--font` | library default | Path to a `.ttf` or `.otf`. See [`fonts/`](fonts). |
| `--color_file` | built-in palette | JSON palette. See [`colors/`](colors). |
| `--exclude-words` | *none* | Words to drop. Quote multi-word phrases: `"et al"`. |
| `--max-words` | `200` | How many words to draw. |
| `--collocations` | off | Allow two-word phrases in the cloud. |
| `--seed` | random | Fix the layout and colors so a run is reproducible. |
| `--output-dir` | `output` | Where the PNG is written (created if missing). |
| `--no-show` | off | Save without opening a preview window — useful in scripts. |

Run `python wordcloud_gen.py --help` for the full list.

### Custom palettes

A palette is a JSON file listing hex colors; words are drawn from it at random.

```json
{
  "colors": ["#ebbf0d", "#2f9d00", "#cb6ce6", "#ff5757", "#008ada"]
}
```

Drop your own into [`colors/`](colors) and pass it with `--color_file`, or build one
visually in the app with **Add** / **Remove** and reuse the file it saves.

---

## Project layout

```
WordcloudGen/
├── wordcloudgen/          # the shared engine (text → cloud)
│   └── core.py
├── wordcloud_gen.py       # CLI front end
├── wordcloud_gen_GUI.py   # desktop front end
├── build_exe.py           # builds the standalone Windows app
├── setup_nltk.py          # downloads the NLTK corpora
├── tests/                 # pytest suite
├── colors/                # palette presets (JSON)
├── fonts/                 # bundled fonts
├── input/                 # sample documents
└── output/                # generated images land here
```

Both front ends are thin wrappers around `wordcloudgen/core.py`, so a fix in the engine
reaches the CLI and the app at once.

---

## Build the executable yourself

```bash
pip install -r requirements-dev.txt
python build_exe.py
```

This downloads the NLTK corpora, trims the ones the app can't reach, runs PyInstaller
against [`wordcloud_gen_GUI.spec`](wordcloud_gen_GUI.spec), and then self-tests the
result by rendering a cloud without opening a window. The app appears in
`dist/WordcloudGen/`.

The spec resolves every package path at build time, so there is nothing machine-specific
to edit. If a frozen build misbehaves, rebuild with a console attached to see the
traceback:

```bash
WORDCLOUDGEN_CONSOLE=1 python build_exe.py
```

Pushing a tag builds and publishes a release automatically:

```bash
git tag v1.0.0
git push origin v1.0.0
```

---

## Development

```bash
pip install -r requirements-dev.txt
pytest          # run the test suite
ruff check .    # lint
```

CI runs the tests on Windows and Linux across Python 3.10–3.12.

---

## Troubleshooting

<details>
<summary><b><code>ModuleNotFoundError: No module named 'frontend'</code> from PyMuPDF</b></summary>

A stale or conflicting install. Reinstall it cleanly:

```bash
pip uninstall -y fitz pymupdf
pip install --upgrade --force-reinstall pymupdf
```

The old `fitz` package on PyPI is unrelated to PyMuPDF and shadows it.

</details>

<details>
<summary><b><code>LookupError: Resource punkt not found</code></b></summary>

The NLTK corpora were not downloaded. Run `python setup_nltk.py`. Behind a proxy with a
self-signed certificate, that script relaxes SSL verification for you.

</details>

<details>
<summary><b>The cloud comes out empty</b></summary>

Every word was filtered out. Check that `--lang` matches the document's actual language,
and that your exclusion list isn't too broad. Scanned PDFs hold images rather than text —
run OCR first.

</details>

<details>
<summary><b>The transparent background looks white</b></summary>

The PNG does have an alpha channel; most image viewers just paint white behind it. Open
it in an editor, or place it over a colored background, to confirm.

</details>

---

## Contributing

Contributions are welcome. Open an
[issue](https://github.com/biagio11/WordcloudGen/issues) or a
[pull request](https://github.com/biagio11/WordcloudGen/pulls) — for larger changes,
please start with an issue so we can discuss the direction. See
[CONTRIBUTING.md](CONTRIBUTING.md) for the details.

If this project is useful to you, a ⭐ is appreciated.

## License

[![CC BY-NC-SA 4.0](https://mirrors.creativecommons.org/presskit/icons/cc.svg?ref=chooser-v1)](LICENSE) [![CC BY-NC-SA 4.0](https://mirrors.creativecommons.org/presskit/icons/by.svg?ref=chooser-v1)](LICENSE) [![CC BY-NC-SA 4.0](https://mirrors.creativecommons.org/presskit/icons/nc.svg?ref=chooser-v1)](LICENSE) [![CC BY-NC-SA 4.0](https://mirrors.creativecommons.org/presskit/icons/sa.svg?ref=chooser-v1)](LICENSE)

WordcloudGen by **biagio11** is licensed under
[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/?ref=chooser-v1).

The fonts in [`fonts/`](fonts) are covered by their own licenses, not by this project's.

## Contributors

- [biagio11](https://github.com/biagio11)
