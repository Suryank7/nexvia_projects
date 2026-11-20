from dataclasses import dataclass
from typing import Optional


_CHUNK_SIZE = 512
_CHUNK_OVERLAP = 64


@dataclass
class Chunk:
    text: str
    chunk_index: int


def chunk_text(text: str, chunk_size: int = _CHUNK_SIZE, overlap: int = _CHUNK_OVERLAP) -> list[Chunk]:
    words = text.split()
    chunks = []
    start = 0
    index = 0

    while start < len(words):
        end = start + chunk_size
        chunk_words = words[start:end]
        chunks.append(Chunk(text=" ".join(chunk_words), chunk_index=index))
        start += chunk_size - overlap
        index += 1

    return chunks


def chunk_text_paragraph_aware(
    text: str,
    chunk_size: int = _CHUNK_SIZE,
    overlap: int = _CHUNK_OVERLAP,
) -> list[Chunk]:
    """Split text into chunks while respecting paragraph boundaries.

    Paragraphs (split on blank lines) are kept whole when they fit within
    chunk_size. Larger paragraphs are split with the fixed-word strategy.
    Adjacent small paragraphs are merged until approaching chunk_size.
    This produces more structure-aware chunks than pure word splitting.
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return []

    chunks: list[Chunk] = []
    index = 0
    buffer: list[str] = []
    buffer_len = 0

    def flush_buffer() -> None:
        nonlocal buffer, buffer_len, index
        if buffer:
            joined = "\n\n".join(buffer)
            new_chunks = chunk_text(joined, chunk_size=chunk_size, overlap=overlap)
            for c in new_chunks:
                c.chunk_index = index
                index += 1
            chunks.extend(new_chunks)
            buffer = []
            buffer_len = 0

    for para in paragraphs:
        para_len = len(para.split())
        # If a single paragraph exceeds chunk_size, flush buffer then split it
        if para_len > chunk_size:
            flush_buffer()
            new_chunks = chunk_text(para, chunk_size=chunk_size, overlap=overlap)
            for c in new_chunks:
                c.chunk_index = index
                index += 1
            chunks.extend(new_chunks)
            continue
        # If adding this paragraph would exceed chunk_size, flush first
        if buffer_len + para_len > chunk_size and buffer:
            flush_buffer()
        buffer.append(para)
        buffer_len += para_len

    flush_buffer()
    return chunks
