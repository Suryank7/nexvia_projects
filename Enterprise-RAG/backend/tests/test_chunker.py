"""Unit tests for ingestion chunking strategies (no external services required)."""

from app.ingestion.chunker import chunk_text, chunk_text_paragraph_aware


def test_chunk_text_basic():
    text = "word " * 100  # 100 words
    chunks = chunk_text(text, chunk_size=30, overlap=5)
    assert len(chunks) > 1
    # Chunk indices are sequential
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    # Each chunk text is non-empty
    assert all(c.text.strip() for c in chunks)


def test_chunk_text_small():
    text = "hello world"
    chunks = chunk_text(text, chunk_size=50, overlap=5)
    assert len(chunks) == 1
    assert chunks[0].text == "hello world"
    assert chunks[0].chunk_index == 0


def test_chunk_text_empty():
    chunks = chunk_text("", chunk_size=50, overlap=5)
    assert chunks == []


def test_chunk_text_paragraph_aware_basic():
    text = "Para one sentence.\n\nPara two sentence.\n\n" + "x " * 700
    chunks = chunk_text_paragraph_aware(text, chunk_size=50, overlap=5)
    assert len(chunks) > 1
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    assert all(c.text.strip() for c in chunks)


def test_chunk_text_paragraph_aware_keeps_small_paragraphs_together():
    text = "Short para one.\n\nShort para two.\n\nShort para three."
    chunks = chunk_text_paragraph_aware(text, chunk_size=100, overlap=5)
    # All three short paragraphs should fit in one chunk
    assert len(chunks) == 1
    assert "Short para one." in chunks[0].text
    assert "Short para two." in chunks[0].text
    assert "Short para three." in chunks[0].text


def test_chunk_text_paragraph_aware_large_paragraph_split():
    text = "x " * 700  # one large paragraph
    chunks = chunk_text_paragraph_aware(text, chunk_size=50, overlap=5)
    assert len(chunks) > 1


def test_chunk_text_paragraph_aware_empty():
    chunks = chunk_text_paragraph_aware("", chunk_size=50, overlap=5)
    assert chunks == []

    chunks = chunk_text_paragraph_aware("\n\n\n", chunk_size=50, overlap=5)
    assert chunks == []
