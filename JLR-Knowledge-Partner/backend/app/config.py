from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    # ---------------- Azure OpenAI (leave endpoint/deployment empty -> offline mode)
    azure_openai_endpoint: str = ""  # https://<resource>.openai.azure.com/
    azure_openai_auth: Literal["key", "entra"] = "key"  # entra = keyless (DefaultAzureCredential / az login / managed identity)
    azure_openai_api_key: str = ""
    azure_openai_api_version: str = "2024-10-21"
    azure_openai_chat_deployment: str = ""  # the DEPLOYMENT name in Azure AI Foundry, not the model name
    azure_openai_embedding_deployment: str = ""  # optional; empty -> local fastembed
    azure_openai_embedding_dimensions: int = 0  # 0 = model default (text-embedding-3-small = 1536)

    # Optional faster deployment for short tasks (planning, relevance judging, rewrites, classification),
    # e.g. a gpt-4.1-mini deployment. Empty = use the chat deployment with the fast reasoning effort.
    azure_openai_fast_deployment: str = ""
    llm_fast_reasoning_model: bool | None = None  # None = same as llm_reasoning_model
    llm_reasoning_model: bool = False  # true for o-series / gpt-5 deployments (no temperature, uses reasoning_effort)
    llm_reasoning_effort: Literal["minimal", "low", "medium", "high"] = "low"  # answer writing
    llm_fast_reasoning_effort: Literal["minimal", "low", "medium", "high"] = "minimal"  # planning / rewrite / classify
    llm_temperature: float = 0.0
    llm_max_tokens: int = 1500
    llm_timeout_s: float = 60.0
    llm_max_retries: int = 3  # retries 429 / 5xx with exponential backoff

    # ---------------- local models (no key needed)
    local_embedding_model: str = "BAAI/bge-small-en-v1.5"
    sparse_embedding_model: str = "Qdrant/bm25"
    reranker_model: str = "Xenova/ms-marco-MiniLM-L-6-v2"
    sparse_embedding_path: str = ""  # optional local folder of the BM25 model (skips any download)
    reranker_path: str = ""  # optional local folder of the reranker (ONNX) model (skips any download)
    rerank_enabled: bool = True

    # ---------------- Qdrant (empty URL -> embedded on-disk mode)
    qdrant_url: str = ""
    qdrant_api_key: str = ""
    qdrant_path: str = str(BASE_DIR / "data" / "qdrant")
    collection_prefix: str = "kg"

    # ---------------- ingestion
    upload_dir: str = str(BASE_DIR / "data" / "uploads")
    chunk_size: int = 1200
    chunk_overlap: int = 150
    pdf_engine: Literal["auto", "docling", "pypdf"] = "auto"  # auto = Docling when installed, else pypdf (with a warning)

    # ---------------- upload suggestions (similar documents; code only, no LLM)
    sim_likely_content: float = 0.5  # share of identical cells / lines that makes a file a "likely update"
    sim_related_content: float = 0.2
    sim_likely_name: float = 0.85  # cleaned file-name similarity (Rev / v1 / dates / "copy" removed)
    sim_related_name: float = 0.7
    sim_likely_topic: float = 0.9  # cosine of the document topic vectors (needs a name match as well)
    sim_related_topic: float = 0.85

    # ---------------- RAG
    top_k: int = 8  # evidence units passed to the answer step
    retrieve_candidates: int = 30  # chunks fetched per search before reranking
    max_rerank_candidates: int = 80  # cross-encoder cost grows linearly with this
    rerank_chars: int = 400  # text per candidate given to the cross-encoder (30 x 400 chars ~ 0.6 s on CPU)
    # reranker probability below which evidence counts as "not found". Calibrated with app.eval:
    # answerable questions scored >= 0.90, unanswerable <= 0.20.
    min_relevance: float = 0.3
    # Second gate (Azure embeddings only): evidence also passes when its embedding similarity to the
    # question is high, even if the cross-encoder misses domain synonyms (ADAS sensor <-> "USS Front S1").
    # Calibrated: relevant pairs >= 0.44, unrelated <= 0.34 (hard negative: Tesla battery vs car benchmark).
    semantic_min_similarity: float = 0.42
    semantic_gate: Literal["auto", "on", "off"] = "auto"  # auto = on with Azure embeddings
    # Quality mode (Azure chat): the LLM plans every question (sub-questions + synonyms) and judges
    # which retrieved evidence is relevant, instead of relying on score thresholds alone.
    llm_planning: Literal["always", "follow-ups"] = "always"
    llm_judge: bool = True
    judge_candidates: int = 24
    max_table_rows: int = 30  # list/comparison questions: rows pulled in from a qualifying table
    max_context_chars: int = 16000  # cap on evidence text sent to the LLM
    chat_memory_path: str = str(BASE_DIR / "data" / "chat_memory.sqlite")
    history_turns: int = 6

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # ---------------- document pictures (vision)
    # Pictures are always extracted at ingest and wait. Describing them needs a vision-capable deployment:
    # set it from the COMPANY Azure resource. Endpoint / key / version fall back to the main ones when empty.
    azure_openai_vision_deployment: str = ""
    azure_openai_vision_endpoint: str = ""
    azure_openai_vision_api_key: str = ""
    azure_openai_vision_api_version: str = ""
    vision_reasoning_model: bool = False  # true for gpt-5 / o-series vision deployments
    vision_detail: Literal["low", "high", "auto"] = "high"  # high reads small labels and dimensions on drawings
    vision_max_tokens: int = 700
    vision_concurrency: int = 4
    # optional prices (per 1M tokens) so the cost estimate before a run can show money, not only tokens
    vision_price_input_per_1m: float = 0.0
    vision_price_output_per_1m: float = 0.0

    # ---------------- accounts / auth
    database_url: str = f"sqlite:///{(BASE_DIR / 'data' / 'app.db').as_posix()}"  # any SQLAlchemy URL (e.g. Postgres)
    db_pool_size: int = 5  # PostgreSQL connection pool (ignored for SQLite)
    db_max_overflow: int = 10
    db_pool_recycle_s: int = 1800
    jwt_secret: str = ""  # empty -> generated once and kept in data/.jwt_secret
    jwt_expire_minutes: int = 720

    @property
    def db_url(self) -> str:
        """SQLAlchemy URL; plain postgres:// and postgresql:// are routed to the psycopg 3 driver."""
        url = self.database_url.strip()
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix):]
        return url

    @property
    def db_is_postgres(self) -> bool:
        return self.db_url.startswith("postgresql")

    @property
    def chunks_collection(self) -> str:
        return f"{self.collection_prefix}_chunks"

    @property
    def documents_collection(self) -> str:
        return f"{self.collection_prefix}_documents"

    @property
    def _azure_auth_ok(self) -> bool:
        return self.azure_openai_auth == "entra" or bool(self.azure_openai_api_key)

    @property
    def llm_enabled(self) -> bool:
        return bool(self.azure_openai_endpoint and self.azure_openai_chat_deployment and self._azure_auth_ok)

    @property
    def vision_enabled(self) -> bool:
        endpoint = self.azure_openai_vision_endpoint or self.azure_openai_endpoint
        auth = bool(self.azure_openai_vision_api_key) or self._azure_auth_ok
        return bool(self.azure_openai_vision_deployment and endpoint and auth)

    @property
    def azure_embeddings_enabled(self) -> bool:
        return bool(self.azure_openai_endpoint and self.azure_openai_embedding_deployment and self._azure_auth_ok)


@lru_cache
def get_settings() -> Settings:
    return Settings()
