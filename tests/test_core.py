"""Tests for the shared word cloud pipeline."""

import codecs
import json
import sys
import zipfile
from pathlib import Path

import pymupdf
import pytest
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from wordcloudgen import core  # noqa: E402
from wordcloudgen.core import (  # noqa: E402
    DEFAULT_COLORS,
    SUPPORTED_LANGUAGES,
    WordcloudError,
    build_color_func,
    check_font,
    check_size,
    clean_palette,
    detect_language,
    export_image,
    extract_text,
    generate_word_cloud,
    load_colors,
    load_mask,
    normalize_exclusions,
    parse_background,
    preprocess_text,
    save_colors,
    write_palette,
)

SAMPLE = (
    "The wise man rejects pleasure to secure greater pleasures, "
    "and endures pains to avoid worse pains. New York is a great city."
)

ITALIAN = (
    "Nel mezzo del cammin di nostra vita mi ritrovai per una selva oscura, "
    "che la diritta via era smarrita. Ahi quanto a dir qual era è cosa dura "
    "esta selva selvaggia e aspra e forte che nel pensier rinova la paura!"
)

GERMAN = (
    "Die Würde des Menschen ist unantastbar. Sie zu achten und zu schützen ist "
    "Verpflichtung aller staatlichen Gewalt. Das Deutsche Volk bekennt sich darum "
    "zu unverletzlichen und unveräußerlichen Menschenrechten."
)


@pytest.fixture
def doc(tmp_path):
    path = tmp_path / "doc.txt"
    path.write_text(SAMPLE, encoding="utf-8")
    return path


def make_docx(path, paragraphs):
    body = "".join(paragraphs)
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", xml)
    return path


def make_pdf(path, text=None, password=None):
    document = pymupdf.open()
    page = document.new_page()
    if text:
        page.insert_text((72, 72), text)
    options = {}
    if password:
        options = {"encryption": pymupdf.PDF_ENCRYPT_AES_256,
                   "user_pw": password, "owner_pw": password + "-owner"}
    document.save(path, **options)
    document.close()
    return path


# ------------------------------------------------------------------ text I/O

def test_extract_text_reads_a_text_file(tmp_path):
    path = tmp_path / "doc.txt"
    path.write_text("hello world", encoding="utf-8")
    assert extract_text(path) == "hello world"


def test_extract_text_rejects_a_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        extract_text(tmp_path / "nope.txt")


def test_extract_text_survives_undecodable_bytes(tmp_path):
    path = tmp_path / "doc.txt"
    path.write_bytes(b"caf\xe9 pleasure")  # latin-1 in a utf-8 world
    assert extract_text(path) == "café pleasure"


def test_extract_text_strips_a_utf8_bom(tmp_path):
    path = tmp_path / "doc.txt"
    path.write_bytes(codecs.BOM_UTF8 + b"pleasure")
    assert extract_text(path) == "pleasure"


def test_extract_text_reads_utf16_from_notepad(tmp_path):
    path = tmp_path / "doc.txt"
    path.write_text("città pleasure", encoding="utf-16")
    assert extract_text(path) == "città pleasure"


def test_extract_text_rejects_binary_files(tmp_path):
    path = tmp_path / "doc.txt"
    path.write_bytes(b"\x00\x01\x02\x03binary")
    with pytest.raises(WordcloudError, match="doesn't look like a text file"):
        extract_text(path)


def test_extract_text_explains_old_word_files(tmp_path):
    path = tmp_path / "old.doc"
    path.write_bytes(b"\xd0\xcf\x11\xe0")
    with pytest.raises(WordcloudError, match="docx"):
        extract_text(path)


def test_extract_text_rejects_an_image(tmp_path):
    path = tmp_path / "picture.png"
    Image.new("RGB", (4, 4)).save(path)
    with pytest.raises(WordcloudError, match="image"):
        extract_text(path)


def test_extract_text_reads_a_docx(tmp_path):
    path = make_docx(tmp_path / "doc.docx", [
        "<w:p><w:r><w:t>Hello</w:t></w:r><w:r><w:tab/><w:t>world</w:t></w:r></w:p>",
        "<w:p><w:r><w:t>Second paragraph</w:t></w:r></w:p>",
    ])
    text = extract_text(path)
    assert "Hello world" in text
    assert "Second paragraph" in text


def test_extract_text_rejects_a_broken_docx(tmp_path):
    path = tmp_path / "doc.docx"
    path.write_bytes(b"this is not a zip file")
    with pytest.raises(WordcloudError, match="Word document"):
        extract_text(path)


def test_extract_text_reads_a_pdf(tmp_path):
    path = make_pdf(tmp_path / "doc.pdf", "pleasure and pain")
    assert "pleasure and pain" in extract_text(path)


def test_extract_text_explains_a_scanned_pdf(tmp_path):
    path = make_pdf(tmp_path / "scan.pdf")
    with pytest.raises(WordcloudError, match="OCR"):
        extract_text(path)


def test_extract_text_explains_a_locked_pdf(tmp_path):
    path = make_pdf(tmp_path / "locked.pdf", "secret words", password="hunter2")
    with pytest.raises(WordcloudError, match="password"):
        extract_text(path)


def test_extract_text_explains_a_damaged_pdf(tmp_path):
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"%PDF-1.7 garbage garbage")
    with pytest.raises(WordcloudError):
        extract_text(path)


# --------------------------------------------------------------- preprocess

def test_preprocess_removes_stopwords_and_punctuation():
    tokens = preprocess_text(SAMPLE).split()
    assert "the" not in tokens and "and" not in tokens
    assert "," not in tokens
    assert "wise" in tokens


def test_preprocess_lemmatizes_plurals():
    tokens = preprocess_text(SAMPLE).split()
    assert "pain" in tokens  # "pains" was lemmatized
    assert "pains" not in tokens


def test_preprocess_excludes_single_words():
    tokens = preprocess_text(SAMPLE, exclude_words=["pleasure", "wise"]).split()
    assert "pleasure" not in tokens
    assert "wise" not in tokens


def test_preprocess_excludes_words_after_lemmatization():
    """'pains' lemmatizes to 'pain', so excluding 'pain' must drop it too."""
    assert "pain" not in preprocess_text(SAMPLE, exclude_words=["pain"]).split()


def test_preprocess_excluding_a_plural_drops_the_singular_too():
    assert "pain" not in preprocess_text(SAMPLE, exclude_words=["pains"]).split()


def test_preprocess_excludes_multi_word_phrases():
    tokens = preprocess_text(SAMPLE, exclude_words=["new york"]).split()
    assert "york" not in tokens
    assert "new" not in tokens
    assert "city" in tokens  # the surrounding text survives


def test_preprocess_excludes_phrases_split_across_lines():
    tokens = preprocess_text("I love New\nYork and its city lights",
                             exclude_words=["new york"]).split()
    assert "york" not in tokens


def test_preprocess_accepts_a_comma_separated_string():
    tokens = preprocess_text(SAMPLE, exclude_words="pleasure, wise").split()
    assert "pleasure" not in tokens and "wise" not in tokens


def test_preprocess_ignores_blank_exclusions():
    """An empty GUI textbox yields [''], which must not blank the whole cloud."""
    assert preprocess_text(SAMPLE, exclude_words=["", "  "]).split()


def test_preprocess_falls_back_for_an_unknown_language():
    assert preprocess_text(SAMPLE, lang="klingon").split()


def test_preprocess_only_lemmatizes_english():
    """WordNet is English; it must not rewrite words in other languages."""
    assert "pains" in preprocess_text("pains pains", lang="italian").split()


def test_preprocess_drops_single_letters():
    assert "x" not in preprocess_text("x marks the spot").split()


def test_preprocess_auto_detects_the_language():
    tokens = preprocess_text(ITALIAN, lang="auto").split()
    assert "selva" in tokens
    assert "che" not in tokens  # an Italian stopword


def test_preprocess_works_without_nltk_data(monkeypatch):
    """Offline with no corpora, the pipeline still has to produce something."""
    import nltk

    def missing(*_args, **_kwargs):
        raise LookupError("no punkt")

    monkeypatch.setattr(nltk, "word_tokenize", missing)
    monkeypatch.setattr(core, "_nltk_stopwords", lambda lang: None)
    tokens = preprocess_text(SAMPLE).split()
    assert "pleasure" in tokens
    assert "the" not in tokens  # wordcloud's own English list kicked in


def test_normalize_exclusions_cleans_up_user_input():
    assert normalize_exclusions(' "Et  Al", Pain,,\n  ') == ["et al", "pain"]
    assert normalize_exclusions(None) == []


# ------------------------------------------------------ language detection

@pytest.mark.parametrize(("text", "expected"), [
    (SAMPLE * 3, "english"),
    (ITALIAN, "italian"),
    (GERMAN, "german"),
])
def test_detect_language(text, expected):
    assert detect_language(text) == expected


def test_detect_language_defaults_to_english_for_no_words():
    assert detect_language("1234 5678 !!!") == "english"


def test_every_supported_language_has_a_stopword_list():
    from nltk.corpus import stopwords

    available = set(stopwords.fileids())
    assert set(SUPPORTED_LANGUAGES) <= available


# ------------------------------------------------------------------ palettes

def test_load_colors_defaults_when_no_file_given():
    assert load_colors(None) == DEFAULT_COLORS


def test_load_colors_defaults_when_the_file_is_missing(tmp_path):
    assert load_colors(tmp_path / "absent.json") == DEFAULT_COLORS


def test_load_colors_defaults_on_malformed_json(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    assert load_colors(path) == DEFAULT_COLORS


def test_load_colors_reads_a_palette(tmp_path):
    path = tmp_path / "palette.json"
    path.write_text(json.dumps({"colors": ["#000000", "#ffffff"]}), encoding="utf-8")
    assert load_colors(path) == ["#000000", "#ffffff"]


def test_load_colors_accepts_a_bare_list(tmp_path):
    path = tmp_path / "palette.json"
    path.write_text(json.dumps(["red", "#00ff00"]), encoding="utf-8")
    assert load_colors(path) == ["red", "#00ff00"]


def test_load_colors_skips_entries_that_are_not_colors(tmp_path):
    path = tmp_path / "palette.json"
    path.write_text(json.dumps({"colors": ["#000000", "not-a-color", 42]}), encoding="utf-8")
    assert load_colors(path) == ["#000000"]


def test_load_colors_defaults_when_nothing_usable(tmp_path):
    path = tmp_path / "palette.json"
    path.write_text(json.dumps({"colors": "oops"}), encoding="utf-8")
    assert load_colors(path) == DEFAULT_COLORS


def test_clean_palette():
    assert clean_palette(["#fff", "nope", "", "  red "]) == ["#fff", "red"]


def test_save_and_reload_round_trips(tmp_path):
    saved = save_colors(["#123456", "#abcdef"], tmp_path)
    assert saved is not None
    assert load_colors(saved) == ["#123456", "#abcdef"]


def test_save_colors_never_overwrites(tmp_path):
    first = save_colors(["#123456"], tmp_path)
    second = save_colors(["#abcdef"], tmp_path)
    assert first != second
    assert load_colors(first) == ["#123456"]


def test_save_colors_returns_none_for_an_empty_palette(tmp_path):
    assert save_colors([], tmp_path) is None


def test_write_palette(tmp_path):
    path = write_palette(["#010203"], tmp_path / "sub" / "mine.json")
    assert load_colors(path) == ["#010203"]


def test_color_func_only_returns_palette_colors():
    palette = ["#111111", "#222222"]
    color_func = build_color_func(colors=palette, seed=1)
    assert {color_func() for _ in range(50)} <= set(palette)


def test_color_func_is_reproducible_with_a_seed():
    first = [build_color_func(colors=DEFAULT_COLORS, seed=99)() for _ in range(10)]
    second = [build_color_func(colors=DEFAULT_COLORS, seed=99)() for _ in range(10)]
    assert first == second


# ----------------------------------------------------------- settings checks

@pytest.mark.parametrize(("value", "expected"), [
    ("transparent", None), ("None", None), ("", "white"), (None, "white"),
    ("#101820", "#101820"), ("navy", "navy"),
])
def test_parse_background_accepts(value, expected):
    assert parse_background(value) == expected


def test_parse_background_rejects_nonsense():
    with pytest.raises(WordcloudError, match="isn't a color"):
        parse_background("blurple")


@pytest.mark.parametrize(("width", "height"), [
    ("abc", 100), (10, 100), (100, 8001), (8000, 8000), (None, 100),
])
def test_check_size_rejects(width, height):
    with pytest.raises(WordcloudError):
        check_size(width, height)


def test_check_size_accepts_strings():
    assert check_size("1920", "1080") == (1920, 1080)


def test_check_font_accepts_a_bundled_font():
    assert check_font(ROOT / "fonts" / "Roboto-Regular.ttf")


def test_check_font_rejects_a_missing_file(tmp_path):
    with pytest.raises(WordcloudError, match="not found"):
        check_font(tmp_path / "nope.ttf")


def test_check_font_rejects_a_file_that_is_not_a_font(tmp_path):
    fake = tmp_path / "fake.ttf"
    fake.write_text("definitely not a font", encoding="utf-8")
    with pytest.raises(WordcloudError, match="as a font"):
        check_font(fake)


# --------------------------------------------------------------------- masks

def _circle(path, mode="RGB"):
    background = (0, 0, 0, 0) if mode == "RGBA" else "white"
    image = Image.new(mode, (200, 100), background)
    ImageDraw.Draw(image).ellipse((50, 0, 150, 100), fill="black")
    image.save(path)
    return path


def test_load_mask_fits_the_requested_size(tmp_path):
    mask = load_mask(_circle(tmp_path / "circle.png"), 400, 400)
    assert mask.shape == (400, 400)
    assert mask[200, 200] == 0  # centre: inside the circle, words allowed
    assert mask[5, 5] == 255  # corner: outside


def test_load_mask_uses_transparency(tmp_path):
    mask = load_mask(_circle(tmp_path / "circle.png", mode="RGBA"), 200, 100)
    assert mask[50, 100] == 0
    assert mask[2, 2] == 255


def test_load_mask_rejects_a_blank_image(tmp_path):
    path = tmp_path / "blank.png"
    Image.new("RGB", (50, 50), "white").save(path)
    with pytest.raises(WordcloudError, match="nowhere to put the words"):
        load_mask(path, 100, 100)


def test_load_mask_rejects_a_non_image(tmp_path):
    path = tmp_path / "fake.png"
    path.write_text("nope", encoding="utf-8")
    with pytest.raises(WordcloudError, match="as an image"):
        load_mask(path, 100, 100)


# ---------------------------------------------------------------- rendering

def test_generate_writes_an_image_of_the_requested_size(doc, tmp_path):
    _, filename = generate_word_cloud(
        input_path=doc, width=400, height=200, output_dir=tmp_path / "out", seed=3)

    with Image.open(filename) as image:
        assert image.size == (400, 200)
        assert image.mode == "RGB"


def test_generate_returns_a_result(doc, tmp_path):
    stages = []
    result = generate_word_cloud(input_path=doc, lang="auto", width=300, height=200,
                                 output_dir=tmp_path, seed=3, progress=stages.append)
    assert result.language == "english"
    assert result.words[0] in ("pleasure", "pain")
    assert Path(result.path).is_file()
    assert any("Reading" in s for s in stages) and any("Saving" in s for s in stages)


def test_generate_creates_a_missing_output_folder(doc, tmp_path):
    target = tmp_path / "deeply" / "nested"
    _, filename = generate_word_cloud(
        input_path=doc, width=200, height=100, output_dir=target, seed=3)
    assert Path(filename).parent == target


def test_generate_never_overwrites_an_earlier_image(doc, tmp_path):
    first = generate_word_cloud(input_path=doc, width=200, height=100, output_dir=tmp_path).path
    second = generate_word_cloud(input_path=doc, width=200, height=100, output_dir=tmp_path).path
    assert first != second
    assert Path(first).is_file() and Path(second).is_file()


def test_generate_honours_a_transparent_background(doc, tmp_path):
    _, filename = generate_word_cloud(
        input_path=doc, width=200, height=100, background="transparent",
        output_dir=tmp_path / "out", seed=3)

    with Image.open(filename) as image:
        assert image.mode == "RGBA"
        assert image.getpixel((0, 0))[3] == 0  # corner is fully transparent


def test_generate_with_a_mask_keeps_the_requested_size(doc, tmp_path):
    result = generate_word_cloud(input_path=doc, width=300, height=300, seed=3,
                                 mask=_circle(tmp_path / "circle.png"), output_dir=tmp_path)
    with Image.open(result.path) as image:
        assert image.size == (300, 300)
        assert image.getpixel((2, 2)) == (255, 255, 255)  # outside the shape stays empty


def test_generate_to_an_exact_jpeg_flattens_transparency(doc, tmp_path):
    target = tmp_path / "cloud.jpg"
    result = generate_word_cloud(input_path=doc, width=200, height=100,
                                 background="transparent", output_path=target, seed=3)
    assert result.path == str(target)
    with Image.open(target) as image:
        assert image.mode == "RGB"


def test_generate_rejects_an_unknown_output_type_before_working(doc, tmp_path):
    with pytest.raises(WordcloudError, match=r"\.png"):
        generate_word_cloud(input_path=doc, output_path=tmp_path / "cloud.gif")


def test_generate_checks_settings_before_reading(tmp_path):
    """A bad setting must fail fast, even when the document is missing too."""
    with pytest.raises(WordcloudError, match="isn't a color"):
        generate_word_cloud(input_path=tmp_path / "missing.pdf", background="blurple")


def test_generate_rejects_zero_words(doc, tmp_path):
    with pytest.raises(WordcloudError, match="at least 1"):
        generate_word_cloud(input_path=doc, output_dir=tmp_path, max_words=0)


def test_generate_requires_a_document(tmp_path):
    with pytest.raises(WordcloudError, match="Choose a document"):
        generate_word_cloud(input_path="  ", output_dir=tmp_path)


def test_generate_rejects_a_document_with_nothing_left(tmp_path):
    source = tmp_path / "doc.txt"
    source.write_text("the and of to a", encoding="utf-8")  # all stopwords

    with pytest.raises(ValueError, match="No words left"):
        generate_word_cloud(input_path=source, output_dir=tmp_path / "out")


def test_generate_reports_an_empty_file(tmp_path):
    source = tmp_path / "empty.txt"
    source.write_text("   \n", encoding="utf-8")
    with pytest.raises(WordcloudError, match="empty"):
        generate_word_cloud(input_path=source, output_dir=tmp_path)


def test_export_image_converts_formats(doc, tmp_path):
    result = generate_word_cloud(input_path=doc, width=200, height=100,
                                 background="transparent", output_dir=tmp_path, seed=1)
    copy = export_image(result.path, tmp_path / "copy.webp")
    with Image.open(copy) as image:
        assert image.format == "WEBP"
