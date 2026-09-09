"""Command-line entry point for WordcloudGen.

Example:
    python wordcloud_gen.py --txt input/demo.txt --color_file colors/vibrant_colors.json
"""

import argparse
import sys

from wordcloudgen import __version__
from wordcloudgen.core import (
    SUPPORTED_LANGUAGES,
    generate_word_cloud,
    show_word_cloud,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wordcloud_gen",
        description="Generate a word cloud from a PDF or text file.",
    )
    parser.add_argument("--version", action="version", version=f"WordcloudGen {__version__}")

    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--pdf", type=str, help="Path to the PDF file.")
    source.add_argument("--txt", type=str, help="Path to the text file.")

    parser.add_argument("--lang", type=str, default="english",
                        choices=SUPPORTED_LANGUAGES,
                        help="Language of the document, used for stopwords.")
    parser.add_argument("--width", type=int, default=1920,
                        help="Width of the word cloud image in pixels.")
    parser.add_argument("--height", type=int, default=1080,
                        help="Height of the word cloud image in pixels.")
    parser.add_argument("--background", type=str, default="white",
                        help='Background color, e.g. "white", "#101820" or "transparent".')
    parser.add_argument("--font", type=str,
                        help="Path to a .ttf or .otf font file.")
    parser.add_argument("--exclude-words", "--exclude", dest="exclude_words",
                        type=str, nargs="*", default=[],
                        help="Words or quoted phrases to leave out of the cloud.")
    parser.add_argument("--color_file", "--colors", dest="color_file", type=str,
                        help="JSON palette file shaped like {\"colors\": [\"#rrggbb\", ...]}.")
    parser.add_argument("--output-dir", type=str, default="output",
                        help="Folder the PNG is written to (created if missing).")
    parser.add_argument("--max-words", type=int, default=200,
                        help="Maximum number of words to draw.")
    parser.add_argument("--collocations", action="store_true",
                        help="Allow two-word phrases in the cloud.")
    parser.add_argument("--seed", type=int,
                        help="Random seed, for reproducible layouts and colors.")
    parser.add_argument("--no-show", action="store_true",
                        help="Save the image without opening a preview window.")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    try:
        cloud, filename = generate_word_cloud(
            input_path=args.pdf or args.txt,
            lang=args.lang,
            width=args.width,
            height=args.height,
            background=args.background,
            font=args.font,
            exclude_words=args.exclude_words,
            output_dir=args.output_dir,
            color_file=args.color_file,
            collocations=args.collocations,
            seed=args.seed,
            max_words=args.max_words,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Word cloud saved as {filename}")

    if not args.no_show:
        show_word_cloud(cloud, args.width, args.height)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
