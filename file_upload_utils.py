"""Utilities for file upload routing, text extraction, and PDF rendering in HUBERT."""
import os
import tempfile
from pathlib import Path

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}

# File types we can extract text from for LLM context
_TEXT_EXTS  = {".txt", ".md", ".csv", ".json", ".py", ".js", ".ts", ".html",
               ".xml", ".yaml", ".yml", ".toml", ".ini", ".log"}
_PDF_EXTS   = {".pdf"}
_DOCX_EXTS  = {".docx", ".doc"}


def classify_file(file_path: str) -> str:
    """Return 'image' for raster image types routed to vision, else 'file'."""
    ext = Path(file_path).suffix.lower()
    return "image" if ext in _IMAGE_EXTS else "file"


def extract_text(file_path: str, max_chars: int = 15_000) -> str | None:
    """
    Extract readable text from a document file.
    Returns text content (truncated to max_chars) or None if unsupported/failed.
    Pure-Python extraction — works with Gemma4 (no LLM required).
    """
    path = Path(file_path)
    ext  = path.suffix.lower()

    try:
        if ext in _TEXT_EXTS:
            return path.read_text(encoding="utf-8", errors="replace")[:max_chars]

        if ext in _PDF_EXTS:
            import pdfplumber
            pages = []
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    t = page.extract_text()
                    if t:
                        pages.append(t)
                    if sum(len(p) for p in pages) >= max_chars:
                        break
            return "\n\n".join(pages)[:max_chars] if pages else None

        if ext in _DOCX_EXTS:
            from docx import Document
            doc = Document(file_path)
            paras = [p.text for p in doc.paragraphs if p.text.strip()]
            return "\n".join(paras)[:max_chars] if paras else None

    except Exception:
        return None

    return None


def render_pdf_page(pdf_path: str, page_num: int = 0, resolution: int = 150) -> str | None:
    """
    Render a single PDF page to a temporary PNG file.
    Returns the temp PNG path, or None on failure.
    Used to give Claude (vision) a pixel-accurate view of the document.
    Falls back gracefully — callers should check for None.
    """
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            if page_num >= len(pdf.pages):
                page_num = 0
            img = pdf.pages[page_num].to_image(resolution=resolution)
            fd, tmp = tempfile.mkstemp(suffix=".png")
            os.close(fd)
            img.save(tmp)
            return tmp
    except Exception:
        return None


def get_file_info(file_path: str) -> dict:
    """
    Return a metadata dict for a file:
    {name, ext, type, size_kb, page_count (PDFs), char_count}
    """
    path = Path(file_path)
    ext  = path.suffix.lower().lstrip(".")
    size_kb = round(path.stat().st_size / 1024, 1) if path.exists() else 0

    page_count = None
    if ext == "pdf":
        try:
            import pdfplumber
            with pdfplumber.open(file_path) as pdf:
                page_count = len(pdf.pages)
        except Exception:
            pass

    text = extract_text(file_path)
    return {
        "name":       path.name,
        "ext":        ext,
        "size_kb":    size_kb,
        "page_count": page_count,
        "char_count": len(text) if text else 0,
        "text":       text,
    }


def build_attachment_note(file_path: str) -> str:
    """Compact attachment note for legacy single-file path."""
    return f"\n[File attached: {Path(file_path).name}]"


def build_context_block(file_path: str) -> str:
    """
    Full context block injected into the LLM message (not shown in chat UI).
    Includes extracted text so any LLM (Claude or Gemma4) can reason over the document.
    """
    name = Path(file_path).name
    text = extract_text(file_path)
    if text:
        return (
            f"\n\n--- Document: {name} ---\n"
            f"{text.strip()}\n"
            f"--- End of {name} ---"
        )
    return f"\n[File attached: {name} — could not extract text]"
