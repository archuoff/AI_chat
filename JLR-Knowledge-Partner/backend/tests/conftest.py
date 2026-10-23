"""Test app: temporary Qdrant / accounts / uploads and tiny fake embedders (the real models need a download)."""
import hashlib
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DIM = 32


class FakeEmbedder:
    name, dim = "fake", DIM

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * DIM
        for tok in re.findall(r"\w+", text.lower()):
            v[int(hashlib.md5(tok.encode()).hexdigest(), 16) % DIM] += 1.0
        return v

    def embed_documents(self, texts):
        return [self._vec(t) for t in texts]

    def embed_query(self, text):
        return self._vec(text)


class FakeSparse:
    name = "fake-sparse"

    def _pair(self, text):
        counts: dict[int, float] = {}
        for tok in re.findall(r"\w+", text.lower()):
            i = int(hashlib.md5(tok.encode()).hexdigest(), 16) % 100_000
            counts[i] = counts.get(i, 0.0) + 1.0
        return list(counts), list(counts.values())

    def embed_documents(self, texts):
        return [self._pair(t) for t in texts]

    def embed_query(self, text):
        return self._pair(text)


@pytest.fixture()
def api(tmp_path, monkeypatch):
    for k, v in {"QDRANT_PATH": tmp_path / "q", "UPLOAD_DIR": tmp_path / "uploads", "DATABASE_URL": f"sqlite:///{tmp_path / 'app.db'}",
                 "CHAT_MEMORY_PATH": tmp_path / "chat.sqlite", "RERANK_ENABLED": "false", "AZURE_OPENAI_ENDPOINT": ""}.items():
        monkeypatch.setenv(k, str(v))
    from fastapi.testclient import TestClient

    from app import config, llm, store
    config.get_settings.cache_clear()
    store.get_store.cache_clear()
    monkeypatch.setattr(store, "get_embedder", lambda: FakeEmbedder())
    monkeypatch.setattr(store, "get_sparse_embedder", lambda: FakeSparse())
    from app.auth import db as auth_db
    monkeypatch.setattr(auth_db, "_engine", None)
    from app import main
    main.settings = config.get_settings()
    auth_db.init_db()
    from app.auth.security import hash_password
    with auth_db.SessionLocal() as s:
        s.add(auth_db.User(username="dev", display_name="Dev", password_hash=hash_password("password123"), role="developer"))
        s.commit()
    client = TestClient(main.app)
    token = client.post("/api/auth/login", json={"username": "dev", "password": "password123"}).json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    yield client
    store.get_store().close()
    store.get_store.cache_clear()
    config.get_settings.cache_clear()
