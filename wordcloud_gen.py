"""Command-line entry point for WordcloudGen.

Examples:
    python wordcloud_gen.py input/demo.txt
    python wordcloud_gen.py report.pdf --color_file colors/vibrant_colors.json --no-show
"""

import argparse
import logging
import sys

from wordcloudgen import __version__
from wordcloudgen.core import (
    AUTO_LANGUAGE,
    SUPPORTED_LANGUAGES,
    WordcloudError,
    generate_word_cloud,
    show_word_cloud,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wordcloud_gen",
        description="Generate a word cloud from a PDF, Word .docx or text file.",
    )
    parser.add_argument("--version", action="version", version=f"WordcloudGen {__version__}")

    parser.add_argument("document", nargs="?",
                        help="The PDF, .docx or text file to read.")
    # --pdf and --txt predate the positional argument and still work.
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--pdf", type=str, help=argparse.SUPPRESS)
    source.add_argument("--txt", type=str, help=argparse.SUPPRESS)

    parser.add_argument("--lang", type=str.lower, default=AUTO_LANGUAGE,
                        choices=[AUTO_LANGUAGE, *SUPPORTED_LANGUAGES], metavar="LANG",
                        help="Language of the document, used to drop common words. "
                             "Default: detect it. One of: " + ", ".join(SUPPORTED_LANGUAGES))
    parser.add_argument("--width", type=int, default=1920,
                        help="Width of the image in pixels (default 1920).")
    parser.add_argument("--height", type=int, default=1080,
                        help="Height of the image in pixels (default 1080).")
    parser.add_argument("--background", type=str, default="white",
                        help='Background color, e.g. "white", "#101820" or "transparent".')
    parser.add_argument("--font", type=str,
                        help="Path to a .ttf or .otf font file.")
    parser.add_argument("--exclude-words", "--exclude", dest="exclude_words",
                        type=str, nargs="*", default=[],
                        help="Words or quoted phrases to leave out of the cloud.")
    parser.add_argument("--color_file", "--colors", dest="color_file", type=str,
                        help="JSON palette file shaped like {\"colors\": [\"#rrggbb\", ...]}.")
    parser.add_argument("--mask", type=str,
                        help="Image whose dark (or opaque) parts the words should fill.")
    parser.add_argument("--output", type=str,
                        help="Exact file to write (.png, .jpg or .webp). "
                             "Default: a timestamped PNG in --output-dir.")
    parser.add_argument("--output-dir", type=str, default="output",
                        help="Folder the image is written to (created if missing).")
    parser.add_argument("--max-words", type=int, default=200,
                        help="Maximum number of words to draw (default 200).")
    parser.add_argument("--collocations", action="store_true",
                        help="Allow two-word phrases in the cloud.")
    parser.add_argument("--seed", type=int,
                        help="Random seed, for reproducible layouts and colors.")
    parser.add_argument("--no-show", action="store_true",
                        help="Save the image without opening a preview window.")
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    given = [p for p in (args.document, args.pdf, args.txt) if p]
    if not given:
        parser.error("tell me which document to read, e.g.  wordcloud_gen.py report.pdf")
    if len(given) > 1:
        parser.error("give the document once, either as a plain argument or with --pdf/--txt")

    logging.basicConfig(format="Warning: %(message)s", level=logging.WARNING)

    try:
        result = generate_word_cloud(
            input_path=given[0],
            lang=args.lang,
            width=args.width,
            height=args.height,
            background=args.background,
            font=args.font,
            exclude_words=args.exclude_words,
            output_dir=args.output_dir,
            output_path=args.output,
            color_file=args.color_file,
            mask=args.mask,
            collocations=args.collocations,
            seed=args.seed,
            max_words=args.max_words,
        )
    except (FileNotFoundError, WordcloudError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Error: couldn't read or write a file: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130

    detected = f" (detected language: {result.language})" if args.lang == AUTO_LANGUAGE else ""
    print(f"Word cloud saved as {result.path}{detected}")

    if not args.no_show:
        show_word_cloud(result.cloud, args.width, args.height)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
