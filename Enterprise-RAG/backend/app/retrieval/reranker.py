from sentence_transformers import CrossEncoder

from app.config import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

_model: CrossEncoder | None = None
_cohere_client = None

_settings = get_settings()


def load_reranker() -> None:
    global _model
    _model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2", device="cpu")


def get_reranker() -> CrossEncoder:
    if _model is None:
        raise RuntimeError("Reranker not loaded. Call load_reranker() at startup.")
    return _model


def _load_cohere() -> object:
    global _cohere_client
    if _cohere_client is not None:
        return _cohere_client
    if not _settings.cohere_api_key:
        raise RuntimeError("Cohere API key not configured")
    import cohere

    _cohere_client = cohere.Client(_settings.cohere_api_key)
    return _cohere_client


def cohere_rerank(query: str, hits: list[dict], top_k: int = 5) -> list[dict]:
    """Rerank using Cohere's rerank API. Falls back to cross-encoder on error."""
    if not hits:
        return []
    try:
        client = _load_cohere()
        documents = [hit["text"] for hit in hits]
        response = client.rerank(
            model=_settings.cohere_rerank_model,
            query=query,
            documents=documents,
            top_n=top_k,
        )
        results = []
        for result in response.results:
            entry = dict(hits[result.index])
            entry["rerank_score"] = float(result.relevance_score)
            entry["reranker"] = "cohere"
            results.append(entry)
        logger.info("Cohere reranker selected %d results from %d candidates", len(results), len(hits))
        return results
    except Exception as exc:
        logger.warning("Cohere rerank failed (%s), falling back to cross-encoder", exc)
        return rerank(query, hits, top_k=top_k)


def rerank(query: str, hits: list[dict], top_k: int = 5) -> list[dict]:
    """Rerank hits using the configured provider (cross_encoder default, cohere optional)."""
    if not hits:
        return []

    if _settings.reranker_provider == "cohere":
        return cohere_rerank(query, hits, top_k=top_k)

    pairs = [[query, hit["text"]] for hit in hits]
    scores = get_reranker().predict(pairs, show_progress_bar=False)

    ranked = sorted(zip(scores, hits), key=lambda x: x[0], reverse=True)
    results = []
    for score, hit in ranked[:top_k]:
        entry = dict(hit)
        entry["rerank_score"] = float(score)
        entry["reranker"] = "cross_encoder"
        results.append(entry)

    logger.info("Reranker selected %d results from %d candidates", len(results), len(hits))
    return results
