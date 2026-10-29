from pathlib import Path

from ..config import get_settings
from .cleaning import clean_document
from .documents import parse_csv, parse_docx, parse_pdf, parse_pptx, parse_text
from .excel import parse_excel
from .models import Element, ParsedDocument

PARSERS = {
    ".xlsx": parse_excel,
    ".xlsm": parse_excel,
    ".csv": parse_csv,
    ".pdf": parse_pdf,
    ".docx": parse_docx,
    ".pptx": parse_pptx,
    ".txt": parse_text,
    ".md": parse_text,
}
SUPPORTED_EXTENSIONS = sorted(PARSERS)


def parse_file(path: str | Path, options: dict | None = None) -> ParsedDocument:
    """options = user parse corrections (currently used by the Excel parser)."""
    path = Path(path)
    parser = PARSERS.get(path.suffix.lower())
    if parser is None:
        raise ValueError(f"Unsupported file type '{path.suffix}'. Supported: {', '.join(SUPPORTED_EXTENSIONS)}")
    if parser is parse_excel:
        return parse_excel(path, options)
    doc = parser(path)
    return clean_document(doc) if get_settings().clean_noise else doc


__all__ = ["Element", "ParsedDocument", "parse_file", "SUPPORTED_EXTENSIONS"]
