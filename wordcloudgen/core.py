"""Shared word cloud logic used by both the CLI and the GUI.

Keeping text extraction, preprocessing and rendering in one place means the two
front ends cannot drift apart: fix a bug here and both get the fix.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
from wordcloud import WordCloud

# Colors used when no palette file is supplied (matplotlib's "tab10").
DEFAULT_COLORS = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
]

# NLTK ships stopword lists for these; keep the GUI dropdown and the CLI in sync.
SUPPORTED_LANGUAGES = [
    "english", "italian", "german", "spanish", "french",
    "portuguese", "dutch", "russian", "slovene",
]

# Corpora the pipeline needs. 'punkt_tab' is required by NLTK >= 3.8.2.
# Open Multilingual WordNet is deliberately absent: it is 26 MB and is only
# consulted for non-English synset lookups, which this pipeline never performs.
NLTK_PACKAGES = ["punkt", "punkt_tab", "stopwords", "wordnet"]

_nltk_ready = False


def _bundled_nltk_dir() -> Path | None:
    """Locate the nltk_data folder shipped inside a PyInstaller bundle."""
    root = getattr(sys, "_MEIPASS", None)
    if not root:
        return None
    candidate = Path(root) / "nltk_data"
    return candidate if candidate.is_dir() else None


def have_nltk_data(nltk) -> bool:
    """True when every corpus we need is already on disk."""
    lookups = {
        "punkt": "tokenizers/punkt",
        "punkt_tab": "tokenizers/punkt_tab",
        "stopwords": "corpora/stopwords",
        "wordnet": "corpora/wordnet",
    }
    for package in NLTK_PACKAGES:
        resource = lookups.get(package)
        if resource is None:
            return False
        # A corpus may be shipped extracted or still zipped; NLTK's own loaders
        # read either, but data.find() only resolves the zip when asked for the
        # path inside it.
        folder, _, name = resource.partition("/")
        for candidate in (resource, f"{folder}/{name}.zip/{name}/"):
            try:
                nltk.data.find(candidate)
                break
            except LookupError:
                continue
        else:
            return False
    return True


def ensure_nltk_data(quiet: bool = True) -> None:
    """Make sure the NLTK corpora we depend on are available, once per process.

    Prefers data bundled with a frozen build, then anything already installed,
    and only downloads what is genuinely missing.
    """
    global _nltk_ready
    if _nltk_ready:
        return

    import nltk

    bundled = _bundled_nltk_dir()
    if bundled and str(bundled) not in nltk.data.path:
        nltk.data.path.insert(0, str(bundled))

    if have_nltk_data(nltk):
        _nltk_ready = True
        return

    # Download somewhere the user can write. Left to itself NLTK picks the first
    # writable entry in nltk.data.path, which inside a frozen build is the
    # bundle's own folder - so a packaged app would rewrite its own contents.
    download_dir = Path.home() / "nltk_data"
    if str(download_dir) not in nltk.data.path:
        nltk.data.path.append(str(download_dir))

    for package in NLTK_PACKAGES:
        try:
            nltk.download(package, download_dir=str(download_dir), quiet=quiet)
        except Exception as exc:  # network down, proxy, SSL - keep going
            print(f"Warning: could not download NLTK package '{package}': {exc}")
    _nltk_ready = True


def extract_text_from_pdf(pdf_path: str | os.PathLike) -> str:
    """Return the concatenated text of every page in a PDF."""
    import pymupdf

    with pymupdf.open(pdf_path) as document:
        return "".join(page.get_text() for page in document)


def extract_text(path: str | os.PathLike) -> str:
    """Read a document, dispatching on file extension (.pdf vs. plain text)."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Input file not found: {path}")

    if path.suffix.lower() == ".pdf":
        return extract_text_from_pdf(path)
    return path.read_text(encoding="utf-8", errors="replace")


def preprocess_text(text: str, lang: str = "english", exclude_words=None) -> str:
    """Lowercase, tokenize, lemmatize and filter a document.

    Removes stopwords for `lang`, anything in `exclude_words` (multi-word
    phrases included) and every token that is not purely alphabetic.
    """
    ensure_nltk_data()

    import nltk
    from nltk.corpus import stopwords
    from nltk.stem import WordNetLemmatizer

    exclude = [w.strip().lower() for w in (exclude_words or []) if w and w.strip()]
    text = text.lower()

    # Strip multi-word phrases before tokenizing - once split into tokens there
    # is no way to tell "new york" apart from an unrelated "new" and "york".
    for phrase in (p for p in exclude if " " in p):
        text = re.sub(rf"\b{re.escape(phrase)}\b", " ", text)

    try:
        stop_words = set(stopwords.words(lang))
    except OSError:
        print(f"Warning: no stopword list for '{lang}'; falling back to english.")
        stop_words = set(stopwords.words("english"))

    exclude_set = set(exclude)
    lemmatizer = WordNetLemmatizer()

    tokens = [
        lemmatizer.lemmatize(token)
        for token in nltk.word_tokenize(text)
        if token.isalpha() and token not in stop_words and token not in exclude_set
    ]
    # Excluded words can also surface *after* lemmatization ("mice" -> "mouse").
    tokens = [t for t in tokens if t not in stop_words and t not in exclude_set]

    return " ".join(tokens)


def load_colors(color_file: str | os.PathLike | None = None) -> list[str]:
    """Load a palette from a JSON file shaped like {"colors": ["#rrggbb", ...]}.

    Falls back to DEFAULT_COLORS when the file is missing, unreadable or empty.
    """
    if not color_file:
        return list(DEFAULT_COLORS)

    path = Path(color_file)
    if not path.is_file():
        print(f"Warning: {path} not found; using the default palette.")
        return list(DEFAULT_COLORS)

    try:
        colors = json.loads(path.read_text(encoding="utf-8")).get("colors", [])
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Warning: could not read {path} ({exc}); using the default palette.")
        return list(DEFAULT_COLORS)

    return [str(c) for c in colors] or list(DEFAULT_COLORS)


def save_colors(colors, directory: str | os.PathLike = "colors") -> str | None:
    """Write a palette to a timestamped JSON file and return its path."""
    colors = [c for c in colors if c]
    if not colors:
        return None

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"colors_{datetime.now():%Y-%m-%d_%H-%M-%S}.json"
    path.write_text(json.dumps({"colors": list(colors)}, indent=4), encoding="utf-8")
    return str(path)


def build_color_func(color_file=None, colors=None, seed: int | None = None):
    """Return a wordcloud `color_func` that picks randomly from a palette."""
    palette = list(colors) if colors else load_colors(color_file)
    rng = np.random.default_rng(seed)
    return lambda *args, **kwargs: str(rng.choice(palette))


def generate_word_cloud(
    input_path=None,
    lang: str = "english",
    width: int = 1920,
    height: int = 1080,
    background: str = "white",
    font: str | None = None,
    exclude_words=None,
    output_dir: str | os.PathLike = "output",
    color_file=None,
    colors=None,
    collocations: bool = False,
    seed: int | None = None,
    max_words: int = 200,
) -> tuple[WordCloud, str]:
    """Build a word cloud from a document and save it as a timestamped PNG.

    Returns the WordCloud object and the path of the saved image.
    """
    text = extract_text(input_path)
    processed = preprocess_text(text, lang, exclude_words)
    if not processed.strip():
        raise ValueError(
            "No words left after preprocessing. Check the document language "
            "and your exclusion list."
        )

    transparent = str(background).strip().lower() == "transparent"
    cloud = WordCloud(
        width=int(width),
        height=int(height),
        background_color=None if transparent else background,
        mode="RGBA" if transparent else "RGB",
        font_path=str(font) if font else None,
        color_func=build_color_func(color_file, colors, seed),
        collocations=collocations,
        max_words=max_words,
        random_state=seed,
    ).generate(processed)

    output_dir = Path(output_dir or "output")
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"wordcloud_{datetime.now():%Y-%m-%d_%H-%M-%S}.png"
    cloud.to_file(str(out_path))

    return cloud, str(out_path)


def show_word_cloud(cloud: WordCloud, width: int, height: int) -> None:
    """Open the generated cloud in a matplotlib window."""
    import matplotlib.pyplot as plt

    plt.figure(figsize=(width / 100, height / 100))
    plt.imshow(cloud, interpolation="bilinear")
    plt.axis("off")
    plt.tight_layout(pad=0)
    try:
        plt.gcf().canvas.manager.set_window_title("Generated Wordcloud")
    except AttributeError:
        pass  # some matplotlib backends have no window manager
    plt.show()
