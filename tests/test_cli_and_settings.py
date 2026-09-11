"""Tests for the command line front end and the app's settings file."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import wordcloud_gen  # noqa: E402
from wordcloudgen.settings import default_output_dir, load_settings, save_settings  # noqa: E402

DEMO = ROOT / "input" / "demo.txt"


# ----------------------------------------------------------------------- CLI

def run_cli(tmp_path, *args):
    return wordcloud_gen.main([*map(str, args), "--no-show", "--output-dir", str(tmp_path),
                               "--width", "300", "--height", "200", "--seed", "1"])


def test_cli_takes_the_document_as_a_plain_argument(tmp_path, capsys):
    assert run_cli(tmp_path, DEMO) == 0
    out = capsys.readouterr().out
    assert "saved as" in out and "english" in out
    assert list(tmp_path.glob("wordcloud_*.png"))


def test_cli_still_accepts_txt_flag(tmp_path):
    assert run_cli(tmp_path, "--txt", DEMO) == 0


def test_cli_language_is_case_insensitive(tmp_path):
    assert run_cli(tmp_path, DEMO, "--lang", "English") == 0


def test_cli_writes_an_exact_output_file(tmp_path):
    target = tmp_path / "mine.jpg"
    assert run_cli(tmp_path, DEMO, "--output", target) == 0
    assert target.is_file()


def test_cli_reports_a_missing_file(tmp_path, capsys):
    assert run_cli(tmp_path, tmp_path / "missing.txt") == 1
    assert "not found" in capsys.readouterr().err


def test_cli_reports_a_bad_color(tmp_path, capsys):
    assert run_cli(tmp_path, DEMO, "--background", "blurple") == 1
    assert "isn't a color" in capsys.readouterr().err


def test_cli_needs_a_document(capsys):
    with pytest.raises(SystemExit) as exit_info:
        wordcloud_gen.main(["--no-show"])
    assert exit_info.value.code == 2
    assert "which document" in capsys.readouterr().err


def test_cli_rejects_two_documents(capsys):
    with pytest.raises(SystemExit):
        wordcloud_gen.main([str(DEMO), "--txt", str(DEMO)])


# ------------------------------------------------------------------ settings

def test_load_settings_missing_file(tmp_path):
    assert load_settings(tmp_path / "none.json") == {}


def test_load_settings_corrupt_file(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{half a file", encoding="utf-8")
    assert load_settings(path) == {}


def test_load_settings_wrong_shape(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    assert load_settings(path) == {}


def test_settings_round_trip(tmp_path):
    path = tmp_path / "nested" / "settings.json"
    assert save_settings(path, {"width": 800, "document": "città.pdf"})
    assert load_settings(path) == {"width": 800, "document": "città.pdf"}
    assert not list(path.parent.glob("*.tmp"))  # the temp file was moved into place


def test_save_settings_reports_failure_instead_of_raising(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    assert save_settings(blocker / "settings.json", {"a": 1}) is False


def test_default_output_dir():
    app = Path("/some/app")
    assert default_output_dir(app, frozen=False) == app / "output"
    assert default_output_dir(app, frozen=True).name == "WordcloudGen"
