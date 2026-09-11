# Contributing to WordcloudGen

Thanks for wanting to help. Bug reports, ideas and pull requests are all welcome.

## Setting up

```bash
git clone https://github.com/biagio11/WordcloudGen.git
cd WordcloudGen

python -m venv .venv
# Windows:        .venv\Scripts\activate
# macOS / Linux:  source .venv/bin/activate

pip install -r requirements-dev.txt
python setup_nltk.py
```

Check that everything works before changing anything:

```bash
pytest
python wordcloud_gen.py input/demo.txt --no-show
python wordcloud_gen_GUI.py
```

## Where things go

The pipeline (reading documents, cleaning the text, rendering) is in `wordcloudgen/core.py`. `wordcloud_gen.py` is the command line and `wordcloud_gen_GUI.py` is the desktop app. Both are thin layers over the core.

Put shared behaviour in `core.py`. The two front ends used to carry their own copies of the pipeline and drifted apart, and keeping it in one place is what stops that from happening again. A front end should only deal with arguments, widgets and presentation.

When something can go wrong because of what the user did (a bad color, a scanned PDF, a folder they can't write to), raise `WordcloudError` with a message written for them. Both front ends show that message as it is, so make it say what happened and what to do about it.

## Before opening a pull request

```bash
pytest
ruff check .
```

If you change the pipeline, add a test in `tests/test_core.py`. If you change the app, say in the PR what you clicked through to check it, since the tests don't cover the widgets. A screenshot helps.

CI runs the same checks on Windows and Linux with Python 3.10, 3.11 and 3.12.

## Reporting a bug

Please include:

- what you ran (the full command, or the steps in the app),
- what you expected and what happened instead,
- the full error message or traceback,
- your OS and whether you used the `.exe` or ran from source.

If the app crashed, attach `%APPDATA%\WordcloudGen\wordcloudgen.log`. A sample document that shows the problem is the most useful thing of all, when you can share one.

## Releases

Releases are built by GitHub Actions from a tag:

```bash
git tag v1.2.0
git push origin v1.2.0
```

That runs `build_exe.py` on Windows, self-tests both builds, and attaches them to a draft release. Update `CHANGELOG.md` and the version in `pyproject.toml` and `wordcloudgen/__init__.py` in the commit you tag.

## Code style

Follow what's already there: four-space indents, `snake_case`, a short docstring on anything that isn't obvious, and comments that explain why rather than repeat the code. Ruff's settings are in `pyproject.toml`.
