"""WordcloudGen - generate word clouds from PDF or plain-text documents."""

__version__ = "1.0.0"

from .core import (
    DEFAULT_COLORS,
    SUPPORTED_LANGUAGES,
    build_color_func,
    ensure_nltk_data,
    extract_text,
    extract_text_from_pdf,
    generate_word_cloud,
    have_nltk_data,
    load_colors,
    preprocess_text,
)

__all__ = [
    "DEFAULT_COLORS",
    "SUPPORTED_LANGUAGES",
    "build_color_func",
    "ensure_nltk_data",
    "extract_text",
    "extract_text_from_pdf",
    "generate_word_cloud",
    "have_nltk_data",
    "load_colors",
    "preprocess_text",
    "__version__",
]
