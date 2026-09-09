"""Download the NLTK corpora WordcloudGen needs.

    python setup_nltk.py

Both front ends also call this automatically on first use; run it by hand when
you want to prime the cache ahead of time or verify network access.
"""

import ssl
import sys

from wordcloudgen.core import NLTK_PACKAGES, ensure_nltk_data, have_nltk_data


def relax_ssl_if_needed() -> None:
    """Work around corporate proxies with unverifiable certificates."""
    try:
        ssl._create_default_https_context = ssl._create_unverified_context
    except AttributeError:
        pass


def main() -> int:
    relax_ssl_if_needed()
    print("Downloading NLTK data: " + ", ".join(NLTK_PACKAGES))
    ensure_nltk_data(quiet=False)

    import nltk

    # Reuse the engine's own check, so this script and the app can never
    # disagree about whether the data is usable.
    if not have_nltk_data(nltk):
        print("\nSome corpora are still missing.", file=sys.stderr)
        print("Check your internet connection and try again.", file=sys.stderr)
        return 1

    print("\nAll set. You can now run wordcloud_gen.py or wordcloud_gen_GUI.py.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
