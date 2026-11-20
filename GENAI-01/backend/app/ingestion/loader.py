from pathlib import Path
from typing import Optional


def load_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_pdf_file(path: Path) -> str:
    import pdfplumber

    pages = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
    return "\n\n".join(pages)


def load_docx_file(path: Path) -> str:
    """Extract text from a .docx file using python-docx.

    Paragraphs are joined with double newlines so downstream chunking
    can respect document structure.
    """
    from docx import Document as DocxDocument

    doc = DocxDocument(str(path))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n\n".join(paragraphs)


def _extract_text_from_html(html: str) -> str:
    """Convert HTML to plain text, preserving paragraph boundaries."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    # Remove script/style elements
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    # Get text with newlines between block elements
    text = soup.get_text(separator="\n")
    # Collapse excessive blank lines
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)


def fetch_url_text(url: str, timeout: int = 20) -> str:
    """Fetch a webpage and return its extracted plain-text content.

    Raises ValueError on fetch/parse failure so callers can handle it.
    """
    import requests

    try:
        response = requests.get(url, timeout=timeout, headers={"User-Agent": "Enterprise-RAG/1.0"})
        response.raise_for_status()
    except requests.RequestException as exc:
        raise ValueError(f"Failed to fetch URL {url}: {exc}") from exc

    content_type = response.headers.get("content-type", "")
    if "text/html" not in content_type and "application/xhtml" not in content_type:
        # Treat as plain text
        return response.text

    return _extract_text_from_html(response.text)


def load_document(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return load_pdf_file(path)
    if suffix == ".docx":
        return load_docx_file(path)
    if suffix in (".txt", ".md"):
        return load_text_file(path)
    raise ValueError(f"Unsupported file type: {suffix} ({path})")


def load_document_from_url(url: str) -> tuple[str, Optional[str]]:
    """Load a document from a URL.

    Returns (text, source_title) where source_title is the page title or URL.
    """
    text = fetch_url_text(url)
    if not text or not text.strip():
        raise ValueError(f"No extractable text found at URL: {url}")
    return text, url
