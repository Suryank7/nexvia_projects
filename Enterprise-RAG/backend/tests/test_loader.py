"""Unit tests for ingestion loaders (DOCX; no Qdrant/OpenAI required)."""

import os
import tempfile
from pathlib import Path

from app.ingestion.loader import load_docx_file, load_document


def test_load_docx_file():
    from docx import Document as DocxDocument

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "test.docx"
        doc = DocxDocument()
        doc.add_paragraph("Hello world")
        doc.add_paragraph("Second paragraph")
        doc.save(str(path))

        text = load_docx_file(path)
        assert "Hello world" in text
        assert "Second paragraph" in text


def test_load_document_docx_suffix():
    from docx import Document as DocxDocument

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "test.docx"
        doc = DocxDocument()
        doc.add_paragraph("DOCX content here")
        doc.save(str(path))

        text = load_document(path)
        assert "DOCX content here" in text


def test_load_document_unsupported_suffix():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "test.xyz"
        path.write_text("not supported")
        try:
            load_document(path)
            assert False, "Expected ValueError"
        except ValueError:
            pass


def test_fetch_url_text_requires_network(monkeypatch):
    """fetch_url_text should raise ValueError on network failure (no external service)."""
    import requests as real_requests
    from app.ingestion.loader import fetch_url_text

    class _FakeRequests:
        RequestException = real_requests.RequestException

        @staticmethod
        def get(url, timeout=None, headers=None):
            raise real_requests.RequestException("network down")

    # Patch the real requests module's get method since fetch_url_text imports requests
    monkeypatch.setattr(real_requests, "get", _FakeRequests.get)
    try:
        fetch_url_text("http://example.com")
        assert False, "Expected ValueError"
    except ValueError:
        pass
