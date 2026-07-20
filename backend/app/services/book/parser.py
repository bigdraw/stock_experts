"""Book parser for PDF/EPUB/TXT files."""

import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class BookContent:
    """Parsed book content."""

    title: str
    text: str
    format: str  # pdf / epub / txt


class BookParser:
    """Parse book files into text."""

    def parse(self, file_path: str) -> BookContent:
        path = Path(file_path)
        ext = path.suffix.lower()
        if ext == ".pdf":
            return self._parse_pdf(path)
        elif ext == ".epub":
            return self._parse_epub(path)
        elif ext == ".txt":
            return self._parse_txt(path)
        else:
            raise ValueError(f"Unsupported format: {ext}")

    def _parse_pdf(self, path: Path) -> BookContent:
        import fitz  # PyMuPDF

        doc = fitz.open(str(path))
        text_parts = []
        for page in doc:
            text_parts.append(page.get_text())
        doc.close()
        return BookContent(
            title=path.stem,
            text="\n".join(text_parts),
            format="pdf",
        )

    def _parse_epub(self, path: Path) -> BookContent:
        import ebooklib
        from bs4 import BeautifulSoup
        from ebooklib import epub

        book = epub.read_epub(str(path))
        text_parts = []
        for item in book.get_items():
            if item.get_type() == ebooklib.ITEM_DOCUMENT:
                soup = BeautifulSoup(item.get_content(), "html.parser")
                text_parts.append(soup.get_text())
        return BookContent(
            title=path.stem,
            text="\n".join(text_parts),
            format="epub",
        )

    def _parse_txt(self, path: Path) -> BookContent:
        text = path.read_text(encoding="utf-8")
        return BookContent(
            title=path.stem,
            text=text,
            format="txt",
        )
