"""WordcloudGen: generate word clouds from PDF, Word or plain-text documents."""

__version__ = "1.1.0"

from .core import (
    AUTO_LANGUAGE,
    DEFAULT_COLORS,
    SUPPORTED_LANGUAGES,
    Result,
    WordcloudError,
    build_color_func,
    detect_language,
    ensure_nltk_data,
    export_image,
    extract_text,
    extract_text_from_docx,
    extract_text_from_pdf,
    generate_word_cloud,
    have_nltk_data,
    load_colors,
    preprocess_text,
)

__all__ = [
    "AUTO_LANGUAGE",
    "DEFAULT_COLORS",
    "SUPPORTED_LANGUAGES",
    "Result",
    "WordcloudError",
    "build_color_func",
    "detect_language",
    "ensure_nltk_data",
    "export_image",
    "extract_text",
    "extract_text_from_docx",
    "extract_text_from_pdf",
    "generate_word_cloud",
    "have_nltk_data",
    "load_colors",
    "preprocess_text",
    "__version__",
]
