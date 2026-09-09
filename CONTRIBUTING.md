# Contributing to WordcloudGen

Thanks for taking the time to help out. Bug reports, ideas and pull requests are all
welcome.

## Getting set up

```bash
git clone https://github.com/biagio11/WordcloudGen.git
cd WordcloudGen

python -m venv .venv
# Windows:        .venv\Scripts\activate
# macOS / Linux:  source .venv/bin/activate

pip install -r requirements-dev.txt
python setup_nltk.py
```

Check that everything works before you change anything:

```bash
pytest
python wordcloud_gen.py --txt input/demo.txt --no-show
python wordcloud_gen_GUI.py
```

## Where code goes

The rendering pipeline lives in `wordcloudgen/core.py`. Both `wordcloud_gen.py` (CLI) and
`wordcloud_gen_GUI.py` (desktop app) are thin wrappers around it.

**Put shared behaviour in `core.py`.** The two front ends used to hold their own copies of
the text pipeline and drifted apart; keeping the logic in one place is what stops that
happening again. A front end should only handle argument parsing, widgets and presentation.

## Before opening a pull request

```bash
pytest          # the suite should be green
ruff check .    # and the linter quiet
```

If you change the pipeline, add a test for it in `tests/test_core.py`. If you change the
GUI, say in the PR how you exercised it — the tests do not cover the widgets.

CI runs the same checks on Windows and Linux across Python 3.10–3.12.

## Reporting a bug

Please include:

- what you ran (the full command, or the steps in the app),
- what you expected and what happened instead,
- the complete traceback if there is one,
- your OS and `python --version`,
- whether you used the source install or the packaged `.exe`.

A sample document that reproduces the problem helps enormously, when you can share one.

## Releases

Releases are built by GitHub Actions from a tag:

```bash
git tag v1.2.0
git push origin v1.2.0
```

That runs `build_exe.py` on a Windows runner, self-tests the result, and attaches the zip
to a draft release. Update `CHANGELOG.md` and the version in `pyproject.toml` and
`wordcloudgen/__init__.py` in the same commit as the tag.

## Code style

Nothing exotic — follow what is already there. Four-space indents, `snake_case`, a short
docstring on anything non-obvious, and comments that explain *why* rather than restating
the code. `ruff` settings live in `pyproject.toml`.
