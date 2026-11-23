"""TextExtractor: pypdf for text PDFs, plain decode for TXT. Photos/scans -> 'coming soon' (Phase C OCR)."""

from __future__ import annotations

import io

MAX_BYTES = 10 * 1024 * 1024
MAX_PAGES = 10
MAX_PASTE_CHARS = 20_000


class UnsupportedDocument(Exception):
    pass


class PypdfTextExtractor:
    def extract(self, data: bytes, filename: str) -> tuple[str, int]:
        if len(data) > MAX_BYTES:
            raise UnsupportedDocument("File is larger than 10 MB.")
        name = filename.lower()
        if name.endswith(".txt") or not data.startswith(b"%PDF"):
            if name.endswith((".png", ".jpg", ".jpeg", ".heic", ".tif", ".tiff")):
                raise UnsupportedDocument("Photos and scans are coming soon. For now, paste the text or upload a text PDF.")
            try:
                return data.decode("utf-8"), 1
            except UnicodeDecodeError:
                return data.decode("latin-1"), 1
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        if len(reader.pages) > MAX_PAGES:
            raise UnsupportedDocument("PDFs can have at most 10 pages.")
        text = "\n".join((p.extract_text() or "") for p in reader.pages)
        if len(text.strip()) < 40:
            raise UnsupportedDocument("This looks like a scanned PDF. Scans are coming soon; please paste the text.")
        return text, len(reader.pages)
