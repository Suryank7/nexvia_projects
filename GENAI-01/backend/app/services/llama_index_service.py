"""Optional LlamaIndex integration.

This is additive: it does not replace the existing hybrid retrieval pipeline.
It exposes a LlamaIndex-based query path over the same Qdrant collection so the
platform can be compared/evaluated with LlamaIndex retrieval when desired.
"""

from typing import Optional

from app.config import get_settings
from app.retrieval.embedder import embed
from app.utils.logger import get_logger

logger = get_logger(__name__)
_s = get_settings()


class LlamaIndexRetriever:
    """Thin wrapper around LlamaIndex over the existing Qdrant collection.

    Uses the same BGE embeddings already loaded by the platform. If LlamaIndex
    or its Qdrant vector-store integration is unavailable, methods degrade
    gracefully and return an empty list with a logged warning.
    """

    def __init__(self) -> None:
        self._available = False
        self._index = None
        try:
            from llama_index.core import VectorStoreIndex, Settings
            from llama_index.core.schema import Document as LIDocument

            Settings.embed_model = _LlamaIndexEmbedder()
            self._VectorStoreIndex = VectorStoreIndex
            self._LIDocument = LIDocument
            self._available = True
            logger.info("LlamaIndex retriever initialised")
        except Exception as exc:
            logger.warning("LlamaIndex not available (%s); integration disabled", exc)

    def query(self, query_text: str, top_k: int = 5) -> list[dict]:
        if not self._available:
            logger.warning("LlamaIndex retriever not available")
            return []
        try:
            # Build an in-memory index from the existing Qdrant payloads.
            # This is a read-only comparison path; it does not modify Qdrant.
            from app.retrieval.dense import get_client as get_qdrant_client

            client = get_qdrant_client()
            points = client.scroll(
                collection_name=_s.qdrant_collection,
                limit=1000,
                with_payload=True,
                with_vectors=False,
            )[0]

            documents = []
            for point in points:
                payload = point.payload or {}
                text = payload.get("text", "")
                if text:
                    documents.append(
                        self._LIDocument(
                            text=text,
                            metadata={
                                "doc_id": payload.get("doc_id"),
                                "source": payload.get("source"),
                                "role_access": payload.get("role_access"),
                            },
                        )
                    )

            if not documents:
                return []

            index = self._VectorStoreIndex.from_documents(documents)
            retriever = index.as_retriever(similarity_top_k=top_k)
            nodes = retriever.retrieve(query_text)

            results = []
            for node in nodes:
                results.append(
                    {
                        "id": getattr(node.node, "id_", None) or str(node.score),
                        "text": node.node.get_content(),
                        "metadata": node.node.metadata or {},
                        "score": float(node.score) if node.score is not None else 0.0,
                    }
                )
            logger.info("LlamaIndex query returned %d results", len(results))
            return results
        except Exception as exc:
            logger.exception("LlamaIndex query failed: %s", exc)
            return []


class _LlamaIndexEmbedder:
    """Adapter exposing the platform's BGE embedder to LlamaIndex."""

    def __init__(self) -> None:
        from app.retrieval.embedder import get_embedder

        self._embedder = get_embedder()

    async def _aget_query_embedding(self, query: str) -> list[float]:
        return self._embedder([query])[0]

    async def _aget_text_embedding(self, text: str) -> list[float]:
        return self._embedder([text])[0]

    def _get_query_embedding(self, query: str) -> list[float]:
        return self._embedder([query])[0]

    def _get_text_embedding(self, text: str) -> list[float]:
        return self._embedder([text])[0]

    # Property expected by older LlamaIndex versions
    @property
    def embed_mode(self) -> str:
        return "default"


def get_llama_index_retriever() -> LlamaIndexRetriever:
    return LlamaIndexRetriever()
