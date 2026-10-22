"""Model providers.

Chat        : Azure OpenAI (API key or Entra ID) when configured, otherwise None -> offline mode.
Embeddings  : Azure OpenAI when an embedding deployment is configured, otherwise local fastembed.
Sparse      : local BM25 (always).
Reranker    : local cross-encoder (always, unless disabled).
"""
from __future__ import annotations

import logging
import math
import threading
import time
from functools import lru_cache
from typing import Protocol

from .config import get_settings

log = logging.getLogger(__name__)

_COGNITIVE_SCOPE = "https://cognitiveservices.azure.com/.default"


class Embedder(Protocol):
    dim: int
    name: str

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


def _azure_auth_kwargs() -> dict:
    """API key or keyless Entra ID token provider (az login / managed identity / service principal env vars)."""
    s = get_settings()
    if s.azure_openai_auth == "entra":
        from azure.identity import DefaultAzureCredential, get_bearer_token_provider

        return {"azure_ad_token_provider": get_bearer_token_provider(DefaultAzureCredential(), _COGNITIVE_SCOPE)}
    return {"api_key": s.azure_openai_api_key}


def _azure_common() -> dict:
    s = get_settings()
    return {
        "azure_endpoint": s.azure_openai_endpoint.rstrip("/"),
        "api_version": s.azure_openai_api_version,
        "timeout": s.llm_timeout_s,
        "max_retries": s.llm_max_retries,
        **_azure_auth_kwargs(),
    }


class LocalEmbedder:
    def __init__(self, model_name: str):
        from fastembed import TextEmbedding

        self.name = f"fastembed:{model_name}"
        self._model = TextEmbedding(model_name=model_name)
        self.dim = len(next(iter(self._model.embed(["dimension probe"]))))

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return [v.tolist() for v in self._model.embed(texts)]

    def embed_query(self, text: str) -> list[float]:
        return next(iter(self._model.query_embed(text))).tolist()


class AzureEmbedder:
    def __init__(self):
        from langchain_openai import AzureOpenAIEmbeddings

        s = get_settings()
        kwargs = {"azure_deployment": s.azure_openai_embedding_deployment, "chunk_size": 512, **_azure_common()}
        if s.azure_openai_embedding_dimensions:
            kwargs["dimensions"] = s.azure_openai_embedding_dimensions
        self.name = f"azure:{s.azure_openai_embedding_deployment}"
        self._model = AzureOpenAIEmbeddings(**kwargs)
        self.dim = len(self._model.embed_query("dimension probe"))

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._model.embed_documents(texts) if texts else []

    def embed_query(self, text: str) -> list[float]:
        return self._model.embed_query(text)


@lru_cache
def get_embedder() -> Embedder:
    s = get_settings()
    if s.azure_embeddings_enabled:
        log.info("Embeddings: Azure OpenAI deployment '%s'", s.azure_openai_embedding_deployment)
        return AzureEmbedder()
    log.info("Embeddings: local fastembed '%s'", s.local_embedding_model)
    return LocalEmbedder(s.local_embedding_model)


class SparseEmbedder:
    """BM25 sparse vectors (local, no key) for exact keyword / code matching."""

    def __init__(self, model_name: str):
        from fastembed import SparseTextEmbedding

        self.name = f"fastembed:{model_name}"
        path = get_settings().sparse_embedding_path
        self._model = SparseTextEmbedding(model_name=model_name, **({"specific_model_path": path} if path else {}))

    @staticmethod
    def _pair(e) -> tuple[list[int], list[float]]:
        return e.indices.tolist(), e.values.tolist()

    def embed_documents(self, texts: list[str]) -> list[tuple[list[int], list[float]]]:
        return [self._pair(e) for e in self._model.embed(texts)] if texts else []

    def embed_query(self, text: str) -> tuple[list[int], list[float]]:
        return self._pair(next(iter(self._model.query_embed(text))))


@lru_cache
def get_sparse_embedder() -> SparseEmbedder:
    return SparseEmbedder(get_settings().sparse_embedding_model)


class Reranker:
    """Cross-encoder: scores (query, passage) pairs jointly. Returns probabilities in 0..1."""

    def __init__(self, model_name: str):
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        self.name = f"fastembed:{model_name}"
        path = get_settings().reranker_path
        self._model = TextCrossEncoder(model_name=model_name, **({"specific_model_path": path} if path else {}))

    def score(self, query: str, passages: list[str]) -> list[float]:
        if not passages:
            return []
        return [1 / (1 + math.exp(-s)) for s in self._model.rerank(query, passages)]


@lru_cache
def get_reranker() -> Reranker | None:
    s = get_settings()
    return Reranker(s.reranker_model) if s.rerank_enabled else None


@lru_cache
def get_chat_model(fast: bool = False):
    """AzureChatOpenAI instance, or None in offline mode.

    fast=True: same deployment with the lowest reasoning effort, for short structured tasks
    (query planning, rewrites, domain suggestions) where latency matters more than depth.
    """
    s = get_settings()
    if not s.llm_enabled:
        if not fast:
            log.warning("Azure OpenAI chat not configured -> offline mode (extractive answers)")
        return None
    from langchain_openai import AzureChatOpenAI

    deployment = s.azure_openai_chat_deployment
    reasoning = s.llm_reasoning_model
    if fast and s.azure_openai_fast_deployment:
        deployment = s.azure_openai_fast_deployment
        reasoning = s.llm_reasoning_model if s.llm_fast_reasoning_model is None else s.llm_fast_reasoning_model
    # stream_usage: Azure sends token counts at the end of streamed answers (per-user usage accounting)
    kwargs = {"azure_deployment": deployment, "max_tokens": s.llm_max_tokens, "stream_usage": True, **_azure_common()}
    if reasoning:  # reasoning models reject temperature
        kwargs["reasoning_effort"] = s.llm_fast_reasoning_effort if fast else s.llm_reasoning_effort
    else:
        kwargs["temperature"] = s.llm_temperature
    log.info("Chat model%s: Azure OpenAI deployment '%s' (api %s, auth=%s)", " (fast)" if fast else "",
             deployment, s.azure_openai_api_version, s.azure_openai_auth)
    return AzureChatOpenAI(**kwargs)


def get_vision_model():
    """Chat model for describing document pictures, or None until a vision deployment is configured.
    Uses its own endpoint / key when given (company Azure resource), else the main ones."""
    s = get_settings()
    if not s.vision_enabled:
        return None
    from langchain_openai import AzureChatOpenAI

    kwargs = {
        "azure_deployment": s.azure_openai_vision_deployment,
        "azure_endpoint": (s.azure_openai_vision_endpoint or s.azure_openai_endpoint).rstrip("/"),
        "api_version": s.azure_openai_vision_api_version or s.azure_openai_api_version,
        "timeout": s.llm_timeout_s,
        "max_retries": s.llm_max_retries,
        "max_tokens": s.vision_max_tokens,
        **({"api_key": s.azure_openai_vision_api_key} if s.azure_openai_vision_api_key else _azure_auth_kwargs()),
    }
    if s.vision_reasoning_model:
        kwargs["reasoning_effort"] = "low"
    else:
        kwargs["temperature"] = 0.0
    return AzureChatOpenAI(**kwargs)


def add_usage(acc: dict | None, msg) -> None:
    """Accumulate token usage reported on an LLM response message into acc (in place)."""
    if acc is None or msg is None:
        return
    um = getattr(msg, "usage_metadata", None) or {}
    acc["input_tokens"] = acc.get("input_tokens", 0) + int(um.get("input_tokens", 0) or 0)
    acc["output_tokens"] = acc.get("output_tokens", 0) + int(um.get("output_tokens", 0) or 0)
    acc["llm_calls"] = acc.get("llm_calls", 0) + 1


_warm_lock = threading.Lock()
_last_warm = 0.0


def warm_connections() -> bool:
    """Open the HTTPS connections to Azure ahead of a question (called while the user types).

    Azure closes idle keep-alive connections after a few seconds; re-connecting adds ~1 s to the
    first embedding call and to the first answer token. A free model listing (chat client) and a
    one-token embedding (embeddings client) re-open them. Throttled; runs in the background.
    """
    global _last_warm
    s = get_settings()
    with _warm_lock:
        if time.monotonic() - _last_warm < 2.5:
            return False
        _last_warm = time.monotonic()

    def run():
        try:
            if s.azure_embeddings_enabled:
                get_embedder().embed_query("ping")
            llm = get_chat_model()
            if llm is not None:
                llm.root_client.models.list()
        except Exception as e:  # noqa: BLE001 - warming is best effort
            log.debug("warm-up failed: %s", e)

    threading.Thread(target=run, daemon=True).start()
    return True


def describe_llm_error(e: Exception) -> str:
    """Readable message for the common Azure OpenAI failures."""
    import openai

    if isinstance(e, openai.AuthenticationError):
        return "Azure OpenAI authentication failed (check AZURE_OPENAI_API_KEY or Entra ID role 'Cognitive Services OpenAI User')."
    if isinstance(e, openai.NotFoundError):
        return "Azure OpenAI deployment not found (check AZURE_OPENAI_CHAT_DEPLOYMENT is the deployment name, and the API version)."
    if isinstance(e, openai.RateLimitError):
        return "Azure OpenAI rate limit / quota exceeded (429) after retries."
    if isinstance(e, openai.BadRequestError):
        body = getattr(e, "body", None) or {}
        code = (body.get("code") if isinstance(body, dict) else None) or ""
        if "content_filter" in str(code) or "content_filter" in str(e):
            return "The request was blocked by the Azure OpenAI content filter."
        return f"Azure OpenAI rejected the request: {e}"
    if isinstance(e, (openai.APITimeoutError, openai.APIConnectionError)):
        return "Could not reach Azure OpenAI (timeout / network / endpoint URL)."
    return f"{type(e).__name__}: {e}"
