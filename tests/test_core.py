"""Tests for the shared word cloud pipeline."""

import json
import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wordcloudgen.core import (  # noqa: E402
    DEFAULT_COLORS,
    build_color_func,
    extract_text,
    generate_word_cloud,
    load_colors,
    preprocess_text,
    save_colors,
)

SAMPLE = (
    "The wise man rejects pleasure to secure greater pleasures, "
    "and endures pains to avoid worse pains. New York is a great city."
)


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
    assert "pleasure" in extract_text(path)


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


def test_preprocess_excludes_multi_word_phrases():
    tokens = preprocess_text(SAMPLE, exclude_words=["new york"]).split()
    assert "york" not in tokens
    assert "new" not in tokens
    assert "city" in tokens  # the surrounding text survives


def test_preprocess_ignores_blank_exclusions():
    """An empty GUI textbox yields [''], which must not blank the whole cloud."""
    assert preprocess_text(SAMPLE, exclude_words=["", "  "]).split()


def test_preprocess_falls_back_for_an_unknown_language():
    assert preprocess_text(SAMPLE, lang="klingon").split()


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


def test_save_and_reload_round_trips(tmp_path):
    saved = save_colors(["#123456", "#abcdef"], tmp_path)
    assert saved is not None
    assert load_colors(saved) == ["#123456", "#abcdef"]


def test_save_colors_returns_none_for_an_empty_palette(tmp_path):
    assert save_colors([], tmp_path) is None


def test_color_func_only_returns_palette_colors():
    palette = ["#111111", "#222222"]
    color_func = build_color_func(colors=palette, seed=1)
    assert {color_func() for _ in range(50)} <= set(palette)


def test_color_func_is_reproducible_with_a_seed():
    first = [build_color_func(colors=DEFAULT_COLORS, seed=99)() for _ in range(10)]
    second = [build_color_func(colors=DEFAULT_COLORS, seed=99)() for _ in range(10)]
    assert first == second


# ---------------------------------------------------------------- rendering

def test_generate_writes_an_image_of_the_requested_size(tmp_path):
    source = tmp_path / "doc.txt"
    source.write_text(SAMPLE, encoding="utf-8")

    _, filename = generate_word_cloud(
        input_path=source, width=400, height=200,
        output_dir=tmp_path / "out", seed=3)

    with Image.open(filename) as image:
        assert image.size == (400, 200)
        assert image.mode == "RGB"


def test_generate_creates_a_missing_output_folder(tmp_path):
    source = tmp_path / "doc.txt"
    source.write_text(SAMPLE, encoding="utf-8")
    target = tmp_path / "deeply" / "nested"

    _, filename = generate_word_cloud(
        input_path=source, width=200, height=100, output_dir=target, seed=3)

    assert Path(filename).parent == target


def test_generate_honours_a_transparent_background(tmp_path):
    source = tmp_path / "doc.txt"
    source.write_text(SAMPLE, encoding="utf-8")

    _, filename = generate_word_cloud(
        input_path=source, width=200, height=100, background="transparent",
        output_dir=tmp_path / "out", seed=3)

    with Image.open(filename) as image:
        assert image.mode == "RGBA"
        assert image.getpixel((0, 0))[3] == 0  # corner is fully transparent


def test_generate_rejects_a_document_with_nothing_left(tmp_path):
    source = tmp_path / "doc.txt"
    source.write_text("the and of to a", encoding="utf-8")  # all stopwords

    with pytest.raises(ValueError, match="No words left"):
        generate_word_cloud(input_path=source, output_dir=tmp_path / "out")
