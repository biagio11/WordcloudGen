"""Shared word cloud logic used by both the CLI and the GUI.

Keeping text extraction, preprocessing and rendering in one place means the two
front ends cannot drift apart: fix a bug here and both get the fix.
"""

from __future__ import annotations

import json
import logging
import os
import re
import socket
import sys
import zipfile
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree

import numpy as np
from PIL import Image, ImageColor, ImageFont
from wordcloud import STOPWORDS, WordCloud

log = logging.getLogger("wordcloudgen")

# Colors used when no palette file is supplied (matplotlib's "tab10").
DEFAULT_COLORS = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
]

# Every language here has an NLTK stopword list. Right-to-left and CJK scripts
# are left out on purpose: the renderer can't lay them out correctly.
SUPPORTED_LANGUAGES = [
    "danish", "dutch", "english", "finnish", "french", "german", "greek",
    "hungarian", "indonesian", "italian", "norwegian", "portuguese", "romanian",
    "russian", "slovene", "spanish", "swedish", "turkish",
]
AUTO_LANGUAGE = "auto"

# File types extract_text() understands. Anything else is tried as plain text.
DOCUMENT_EXTENSIONS = (".pdf", ".docx", ".txt", ".md")
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff")
OUTPUT_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")

# Canvas limits. Past MAX_PIXELS the layout takes minutes and gigabytes of RAM,
# which looks exactly like a hang from the user's side.
MIN_SIDE = 50
MAX_SIDE = 8000
MAX_PIXELS = 40_000_000
MAX_WORDS_LIMIT = 2000

# Corpora the pipeline needs. 'punkt_tab' is required by NLTK >= 3.8.2.
# Open Multilingual WordNet is deliberately absent: it is 26 MB and is only
# consulted for non-English synset lookups, which this pipeline never performs.
NLTK_PACKAGES = ["punkt", "punkt_tab", "stopwords", "wordnet"]

_nltk_ready = False


class WordcloudError(ValueError):
    """A problem the user can fix: a bad setting, an unreadable file, and so on.

    The message is written to be shown to the user as is. It subclasses
    ValueError so code that already catches ValueError keeps working.
    """


@dataclass
class Result:
    """What generate_word_cloud() produced.

    Unpacks as ``cloud, path = result`` for code written against 1.0.
    """

    cloud: WordCloud
    path: str
    language: str
    words: list[str] = field(default_factory=list)  # most frequent first

    def __iter__(self):
        return iter((self.cloud, self.path))


# ------------------------------------------------------------------ NLTK data

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
    and only downloads what is genuinely missing. If the download fails the
    pipeline still runs, on simpler fallbacks (see tokenize() and friends).
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
    # bundle's own folder, so a packaged app would rewrite its own contents.
    download_dir = Path.home() / "nltk_data"
    if str(download_dir) not in nltk.data.path:
        nltk.data.path.append(str(download_dir))

    # urllib waits forever by default. On a captive portal or a dead proxy that
    # would freeze the first run with no explanation, so cap it.
    previous_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(20)
    try:
        for package in NLTK_PACKAGES:
            try:
                nltk.download(package, download_dir=str(download_dir), quiet=quiet)
            except Exception as exc:  # network down, proxy, SSL: keep going
                log.warning("Could not download the NLTK package '%s': %s", package, exc)
    finally:
        socket.setdefaulttimeout(previous_timeout)
    _nltk_ready = True


# ------------------------------------------------------------- reading files

def extract_text_from_pdf(pdf_path: str | os.PathLike) -> str:
    """Return the text of every page in a PDF."""
    import pymupdf

    name = Path(pdf_path).name
    try:
        document = pymupdf.open(pdf_path)
    except Exception as exc:  # PyMuPDF raises its own FileDataError/RuntimeError
        raise WordcloudError(
            f"Couldn't open {name} as a PDF. The file may be damaged."
        ) from exc

    with document:
        if document.needs_pass and not document.authenticate(""):
            raise WordcloudError(
                f"{name} is password-protected. Remove the password and try again."
            )
        text = "\n".join(page.get_text() for page in document)

    if not text.strip():
        raise WordcloudError(
            f"{name} has no selectable text. It is probably a scan: run it "
            "through OCR first, then try again."
        )
    return text


_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def extract_text_from_docx(docx_path: str | os.PathLike) -> str:
    """Pull the text out of a Word .docx, no Word or python-docx needed.

    A .docx is a zip archive. The body lives in word/document.xml, with one
    <w:p> per paragraph and the text itself in <w:t> runs.
    """
    name = Path(docx_path).name
    try:
        with zipfile.ZipFile(docx_path) as archive:
            root = ElementTree.fromstring(archive.read("word/document.xml"))
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError) as exc:
        raise WordcloudError(
            f"Couldn't read {name} as a Word document. The file may be damaged."
        ) from exc

    breaks = {f"{_W}tab", f"{_W}br", f"{_W}cr"}
    paragraphs = []
    for paragraph in root.iter(f"{_W}p"):
        parts = []
        for node in paragraph.iter():
            if node.tag == f"{_W}t":
                parts.append(node.text or "")
            elif node.tag in breaks:
                parts.append(" ")  # otherwise "word<tab>word" fuses into one
        paragraphs.append("".join(parts))
    return "\n".join(paragraphs)


def read_text_file(path: str | os.PathLike) -> str:
    """Read a plain-text file whatever its encoding.

    Tries UTF-8 (with or without a BOM), UTF-16 (what Notepad calls "Unicode"),
    then Windows-1252, and finally Latin-1, which never fails.
    """
    path = Path(path)
    data = path.read_bytes()

    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16", errors="replace")
    if b"\x00" in data[:4096]:
        raise WordcloudError(
            f"{path.name} doesn't look like a text file. Use a PDF, a Word "
            ".docx or a plain .txt file."
        )

    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def extract_text(path: str | os.PathLike) -> str:
    """Read a document: PDF, Word .docx, or anything that is plain text."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Input file not found: {path}")

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_text_from_pdf(path)
    if suffix == ".docx":
        return extract_text_from_docx(path)
    if suffix == ".doc":
        raise WordcloudError(
            f"{path.name} is an old-style Word file. Open it in Word, save it "
            "as .docx or PDF, and try again."
        )
    if suffix in IMAGE_EXTENSIONS:
        raise WordcloudError(
            f"{path.name} is an image, not a document. To shape the cloud "
            "with it, use it as the mask instead."
        )
    return read_text_file(path)


# ------------------------------------------------------------ text pipeline

_WORD = re.compile(r"[^\W\d_]+")


_stopword_cache: dict[str, frozenset[str]] = {}


def _nltk_stopwords(lang: str) -> frozenset[str] | None:
    # Only successes are cached: a lookup that failed because the corpus was
    # still downloading must be allowed to succeed on the next call.
    if lang not in _stopword_cache:
        try:
            from nltk.corpus import stopwords

            _stopword_cache[lang] = frozenset(stopwords.words(lang))
        except (LookupError, OSError):  # corpus missing, or no list for lang
            return None
    return _stopword_cache[lang]


def load_stopwords(lang: str) -> frozenset[str]:
    """Stopwords for `lang`, falling back to English when there is no list.

    If NLTK has no data at all, the English list that ships inside the
    wordcloud package is used, so a missing corpus never stops a run.
    """
    ensure_nltk_data()
    words = _nltk_stopwords(lang)
    if words is not None:
        return words

    english = _nltk_stopwords("english")
    if english is None:
        log.warning("The NLTK stopword lists are missing; using a built-in English list.")
        return frozenset(STOPWORDS)
    log.warning("No stopword list for '%s'; using English instead.", lang)
    return english


def detect_language(text: str) -> str:
    """Guess which supported language a text is written in.

    Stopwords are the most frequent words in any language, so the language
    whose list covers the largest share of the text wins. Only each list's own
    words are counted once, which keeps big lists (Slovene has ~1,800 entries)
    from winning just by being big.
    """
    words = _WORD.findall(text[:200_000].lower())  # plenty to decide on
    if not words:
        return "english"
    ensure_nltk_data()

    counts = Counter(words)
    frequent = {word for word, _ in counts.most_common(300)}

    best, best_score = "english", 0.0
    for lang in SUPPORTED_LANGUAGES:
        stops = _nltk_stopwords(lang)
        if not stops:
            continue
        hits = frequent & stops
        # Coverage of the whole text, lightly penalised by list size.
        score = sum(counts[w] for w in hits) / len(words) - len(stops) / 100_000
        if score > best_score:
            best, best_score = lang, score
    return best


def tokenize(text: str) -> list[str]:
    """Split text into words with NLTK, or a plain regex if punkt is missing."""
    try:
        import nltk

        return nltk.word_tokenize(text)
    except LookupError:
        log.warning("NLTK tokenizer data is missing; using a simpler word splitter.")
        return _WORD.findall(text)


def _english_lemmatizer() -> Callable[[str], str]:
    """WordNet's lemmatizer, or a no-op when WordNet isn't installed."""
    try:
        from nltk.stem import WordNetLemmatizer

        lemmatizer = WordNetLemmatizer()
        lemmatizer.lemmatize("tests")  # WordNet loads lazily; fail here, not mid-loop
        return lemmatizer.lemmatize
    except LookupError:
        log.warning("WordNet is missing; plurals will not be merged.")
        return lambda word: word


def normalize_exclusions(exclude_words: Iterable[str] | str | None) -> list[str]:
    """Clean up a user's exclusion list.

    Accepts a list or one comma/newline separated string. Lowercases, drops
    blanks and stray quotes, and collapses runs of spaces inside phrases.
    """
    if not exclude_words:
        return []
    if isinstance(exclude_words, str):
        exclude_words = re.split(r"[,\n;]", exclude_words)

    cleaned = []
    for word in exclude_words:
        word = " ".join(str(word).strip().strip("\"'").lower().split())
        if word and word not in cleaned:
            cleaned.append(word)
    return cleaned


def preprocess_text(text: str, lang: str = "english", exclude_words=None) -> str:
    """Lowercase, tokenize, lemmatize and filter a document.

    Removes stopwords for `lang`, anything in `exclude_words` (multi-word
    phrases included) and every token that is not purely alphabetic.
    Pass lang="auto" to detect the language first.
    """
    ensure_nltk_data()
    if lang == AUTO_LANGUAGE:
        lang = detect_language(text)

    exclude = normalize_exclusions(exclude_words)
    text = text.lower()

    # Strip multi-word phrases before tokenizing: once split into tokens there
    # is no way to tell "new york" apart from an unrelated "new" and "york".
    # \s+ between the words also catches a phrase broken across two lines.
    for phrase in (p for p in exclude if " " in p):
        pattern = r"\s+".join(re.escape(part) for part in phrase.split())
        text = re.sub(rf"\b{pattern}\b", " ", text)

    stop_words = load_stopwords(lang)
    # WordNet is English. On other languages it would "fix" words it happens to
    # recognise, e.g. turn a Spanish plural into an unrelated English noun.
    lemmatize = _english_lemmatizer() if lang == "english" else (lambda word: word)

    # Excluding "mice" should also drop "mouse", so exclude the lemmas too.
    exclude_set = set(exclude) | {lemmatize(w) for w in exclude if " " not in w}

    tokens = [
        lemmatize(token)
        for token in tokenize(text)
        if token.isalpha() and len(token) > 1
        and token not in stop_words and token not in exclude_set
    ]
    # Excluded words can also surface *after* lemmatization ("pains" -> "pain").
    tokens = [t for t in tokens if t not in stop_words and t not in exclude_set]

    return " ".join(tokens)


# ------------------------------------------------------------------ palettes

def clean_palette(colors: Iterable[str] | None) -> list[str]:
    """Keep only the entries the renderer can actually draw."""
    valid = []
    for color in colors or []:
        color = str(color).strip()
        if not color:
            continue
        try:
            ImageColor.getrgb(color)
        except ValueError:
            log.warning("Skipping '%s': not a color.", color)
            continue
        valid.append(color)
    return valid


def load_colors(color_file: str | os.PathLike | None = None) -> list[str]:
    """Load a palette from a JSON file shaped like {"colors": ["#rrggbb", ...]}.

    A bare JSON list of colors works too. Falls back to DEFAULT_COLORS when the
    file is missing, unreadable, or holds no usable colors.
    """
    if not color_file:
        return list(DEFAULT_COLORS)

    path = Path(color_file)
    if not path.is_file():
        log.warning("%s not found; using the default palette.", path)
        return list(DEFAULT_COLORS)

    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        log.warning("Could not read %s (%s); using the default palette.", path, exc)
        return list(DEFAULT_COLORS)

    colors = data.get("colors", []) if isinstance(data, dict) else data
    if not isinstance(colors, list):
        colors = []
    return clean_palette(colors) or list(DEFAULT_COLORS)


def write_palette(colors, path: str | os.PathLike) -> str:
    """Write a palette to `path` in the format load_colors() reads."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"colors": clean_palette(colors)}, indent=4) + "\n",
                    encoding="utf-8")
    return str(path)


def save_colors(colors, directory: str | os.PathLike = "colors") -> str | None:
    """Write a palette to a timestamped JSON file and return its path."""
    colors = clean_palette(colors)
    if not colors:
        return None
    path = _unique_path(Path(directory), f"colors_{datetime.now():%Y-%m-%d_%H-%M-%S}", ".json")
    return write_palette(colors, path)


def build_color_func(color_file=None, colors=None, seed: int | None = None):
    """Return a wordcloud `color_func` that picks randomly from a palette."""
    palette = clean_palette(colors) if colors else load_colors(color_file)
    palette = palette or list(DEFAULT_COLORS)
    rng = np.random.default_rng(seed)
    return lambda *args, **kwargs: str(rng.choice(palette))


# ------------------------------------------------------------ settings checks

def parse_background(background: str | None) -> str | None:
    """Return a color the renderer accepts, or None for a transparent canvas."""
    value = str(background or "").strip()
    if not value:
        return "white"
    if value.lower() in ("transparent", "none"):
        return None
    try:
        ImageColor.getrgb(value)
    except ValueError:
        raise WordcloudError(
            f"'{value}' isn't a color I recognise. Use a name like white or "
            "black, a hex value like #101820, or transparent."
        ) from None
    return value


def check_size(width, height) -> tuple[int, int]:
    """Validate the canvas size and return it as two ints."""
    try:
        width, height = int(width), int(height)
    except (TypeError, ValueError):
        raise WordcloudError("Width and height must be whole numbers.") from None

    if not (MIN_SIDE <= width <= MAX_SIDE and MIN_SIDE <= height <= MAX_SIDE):
        raise WordcloudError(
            f"Width and height must each be between {MIN_SIDE} and {MAX_SIDE} pixels."
        )
    if width * height > MAX_PIXELS:
        raise WordcloudError(
            f"{width} x {height} is too large to render in a reasonable time. "
            f"Keep it under {MAX_PIXELS // 1_000_000} megapixels."
        )
    return width, height


def check_font(font: str | os.PathLike | None) -> str | None:
    """Make sure a font file exists and really is a font."""
    if not font:
        return None
    path = Path(font)
    if not path.is_file():
        raise WordcloudError(f"Font file not found: {path}")
    try:
        ImageFont.truetype(str(path), 12)
    except OSError:
        raise WordcloudError(
            f"Couldn't load {path.name} as a font. Pick a .ttf or .otf file."
        ) from None
    return str(path)


def load_mask(path: str | os.PathLike, width: int, height: int) -> np.ndarray:
    """Turn a picture into a mask that shapes the cloud.

    Words go where the picture is dark. White areas stay empty, and so do
    transparent ones, so a logo with a transparent background just works.
    The picture is scaled to fit the canvas and centred, so the output keeps
    the size the user asked for.
    """
    path = Path(path)
    if not path.is_file():
        raise WordcloudError(f"Shape image not found: {path}")
    try:
        with Image.open(path) as picture:
            picture.load()
            if picture.mode in ("RGBA", "LA", "PA") or "transparency" in picture.info:
                inside = np.array(picture.convert("RGBA").getchannel("A")) >= 128
            else:
                inside = np.array(picture.convert("L")) < 240
    except (OSError, Image.DecompressionBombError) as exc:
        raise WordcloudError(f"Couldn't open {path.name} as an image.") from exc

    shape = Image.fromarray(np.where(inside, 255, 0).astype(np.uint8))
    scale = min(width / shape.width, height / shape.height)
    size = (max(1, round(shape.width * scale)), max(1, round(shape.height * scale)))
    shape = shape.resize(size, Image.Resampling.BILINEAR)

    canvas = Image.new("L", (width, height), 0)
    canvas.paste(shape, ((width - size[0]) // 2, (height - size[1]) // 2))
    inside = np.array(canvas) >= 128
    if not inside.any():
        raise WordcloudError(
            f"{path.name} has no dark or opaque areas, so there is nowhere to "
            "put the words. Use a dark shape on a white or transparent background."
        )
    return np.where(inside, 0, 255).astype(np.uint8)  # wordcloud: 255 = keep out


# ----------------------------------------------------------------- rendering

def _unique_path(folder: Path, stem: str, suffix: str) -> Path:
    """`folder/stem.suffix`, numbered if that name is already taken."""
    candidate = folder / f"{stem}{suffix}"
    number = 2
    while candidate.exists():
        candidate = folder / f"{stem}_{number}{suffix}"
        number += 1
    return candidate


def save_image(image: Image.Image, path: str | os.PathLike) -> str:
    """Save an image, picking the format from the extension.

    JPEG has no alpha channel, so a transparent image is flattened onto white
    rather than failing.
    """
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix not in OUTPUT_EXTENSIONS:
        raise WordcloudError(
            f"Can't save as '{suffix or path.name}'. Use .png, .jpg or .webp."
        )
    if suffix in (".jpg", ".jpeg") and image.mode in ("RGBA", "LA"):
        flat = Image.new("RGB", image.size, "white")
        flat.paste(image, mask=image.getchannel("A"))
        image = flat

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path)
    except OSError as exc:
        raise WordcloudError(
            f"Couldn't save the image to {path.parent}: {exc.strerror or exc}. "
            "Pick a folder you can write to."
        ) from exc
    return str(path)


def export_image(source: str | os.PathLike, destination: str | os.PathLike) -> str:
    """Copy a generated image to a new place, converting its format if needed."""
    with Image.open(source) as image:
        image.load()
        return save_image(image, destination)


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
    mask: str | os.PathLike | None = None,
    output_path: str | os.PathLike | None = None,
    progress: Callable[[str], None] | None = None,
) -> Result:
    """Build a word cloud from a document and save it as an image.

    Every setting is checked before the (slow) document is read, so a typo
    fails in milliseconds. Problems the user can fix raise WordcloudError.

    The image goes to `output_path` if given, otherwise to a timestamped PNG in
    `output_dir`. `progress`, if given, is called with a short description of
    each stage. Returns a Result, which also unpacks as ``cloud, path``.
    """
    def step(message: str) -> None:
        if progress:
            progress(message)

    width, height = check_size(width, height)
    if output_path and Path(output_path).suffix.lower() not in OUTPUT_EXTENSIONS:
        raise WordcloudError(
            f"Can't save as '{Path(output_path).name}'. Use .png, .jpg or .webp."
        )
    background_color = parse_background(background)
    font_path = check_font(font)
    try:
        max_words = int(max_words)
    except (TypeError, ValueError):
        raise WordcloudError("The number of words must be a whole number.") from None
    if max_words < 1:
        raise WordcloudError("The number of words must be at least 1.")
    max_words = min(max_words, MAX_WORDS_LIMIT)
    mask_array = load_mask(mask, width, height) if mask else None
    color_func = build_color_func(color_file, colors, seed)

    if input_path is None or not str(input_path).strip():
        raise WordcloudError("Choose a document to read.")
    step(f"Reading {Path(input_path).name}")
    text = extract_text(input_path)
    if not text.strip():
        raise WordcloudError(f"{Path(input_path).name} is empty.")

    step("Cleaning up the text")
    language = detect_language(text) if lang == AUTO_LANGUAGE else lang
    processed = preprocess_text(text, language, exclude_words)
    if not processed.strip():
        raise WordcloudError(
            "No words left after removing common words and your exclusions. "
            "Check the document language and your exclusion list."
        )

    step("Arranging the words")
    cloud = WordCloud(
        width=width,
        height=height,
        background_color=background_color,
        mode="RGBA" if background_color is None else "RGB",
        font_path=font_path,
        color_func=color_func,
        collocations=collocations,
        max_words=max_words,
        mask=mask_array,
        random_state=seed,
    ).generate(processed)

    step("Saving the image")
    if output_path:
        target = Path(output_path)
    else:
        folder = Path(output_dir or "output")
        target = _unique_path(folder, f"wordcloud_{datetime.now():%Y-%m-%d_%H-%M-%S}", ".png")
    path = save_image(cloud.to_image(), target)

    return Result(cloud=cloud, path=path, language=language, words=list(cloud.words_))


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
