"""Tests run against the ASSEMBLED project (template + our overlay): PROJ=<folder> DB_URL=<sqlalchemy url> pytest ..."""
import hashlib
import math
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

PROJ = Path(os.environ["PROJ"]).resolve()
sys.path.insert(0, str(PROJ))
os.chdir(PROJ)
TMP = Path(tempfile.mkdtemp(prefix="engismart_test_"))
os.environ.update({
    "ENVIRONMENT": "development", "SECRET_KEY": "test-secret-key-for-engismart-tests-0123456789",
    "DATABASE_URL": os.environ.get("DB_URL", f"sqlite:///{TMP / 'platform.db'}"), "STORAGE_ROOT": str(TMP / "storage"),
    "LOG_DIR": str(TMP / "logs"), "VIRUS_SCAN": "off", "RERANK_ENABLED": "false", "WARM_UP_ON_START": "false",
    "ACCESS_CACHE_S": "0", "QDRANT_PATH": str(TMP / "qdrant"), "UPLOAD_DIR": str(TMP / "uploads"), "CHAT_MEMORY_PATH": str(TMP / "mem.sqlite"),
    "AZURE_OPENAI_ENDPOINT": "", "AZURE_OPENAI_CHAT_DEPLOYMENT": "", "LLM_PRICE_INPUT_PER_1M": "2", "LLM_PRICE_OUTPUT_PER_1M": "8",
})


def _tokens(text):
    return [w for w in "".join(c.lower() if c.isalnum() else " " for c in text).split() if w]


class FakeDense:
    dim, name = 64, "fake-dense"

    def _vec(self, text):
        v = [0.0] * 64
        for w in _tokens(text):
            v[int(hashlib.md5(w.encode()).hexdigest(), 16) % 64] += 1
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]

    def embed_documents(self, texts):
        return [self._vec(t) for t in texts]

    def embed_query(self, text):
        return self._vec(text)


class FakeSparse:
    name = "fake-sparse"

    def _pair(self, text):
        d = {}
        for w in _tokens(text):
            d[int(hashlib.md5(w.encode()).hexdigest(), 16) % 100000] = d.get(int(hashlib.md5(w.encode()).hexdigest(), 16) % 100000, 0) + 1.0
        return list(d), list(d.values())

    def embed_documents(self, texts):
        return [self._pair(t) for t in texts]

    def embed_query(self, text):
        return self._pair(text)


import controller.engismart.core.llm as llm  # noqa: E402  (patched before store / rag import their names)

_dense, _sparse = FakeDense(), FakeSparse()
llm.get_embedder = lambda: _dense
llm.get_sparse_embedder = lambda: _sparse

from fastapi.testclient import TestClient  # noqa: E402
from jose import jwt  # noqa: E402

from main import fastapi_app  # noqa: E402
from models.model import models  # noqa: E402
from models.orm_models import (  # noqa: E402
    Application, ApplicationRole, ApplicationUserRolePermission, Base, User, UserApplicationPermissionMap, engine,
)
from utility.settings import settings  # noqa: E402

DOMAINS = ["adas", "benchmarking", "eds", "lead-engineering", "materials-net", "supplier-database"]


def make_token(username: str) -> str:
    return jwt.encode({"username": username, "token_version": 1, "exp": datetime.utcnow() + timedelta(hours=1)}, settings.SECRET_KEY, settings.ALGORITHM)


@pytest.fixture(scope="session", autouse=True)
def platform_db():
    Base.metadata.create_all(engine)
    with models() as db:
        s = db.session
        apps = {}
        for alias in ["engismart"] + [f"engismart_{d}" for d in DOMAINS] + ["other_module"]:
            a = Application(application_name=alias, application_alias=alias, token=alias, status=1, category="AI")
            s.add(a)
            apps[alias] = a
        s.flush()
        roles = {}
        for alias in ("engismart_developer", "engismart_superuser"):
            r = ApplicationRole(application_id=apps["engismart"].id, permission=alias, token=alias, permission_alias=alias)
            s.add(r)
            roles[alias] = r
        s.flush()

        def user(name, apps_given, role=None, admin="0"):
            u = User(username=name, email=f"{name}@x.test", display_name=name.title(), token=f"tok-{name}", password="x", is_admin=admin,
                     approved=1, status=1, is_deleted=0, token_version=1)
            s.add(u)
            s.flush()
            for al in apps_given:
                s.add(UserApplicationPermissionMap(user_id=u.id, application_id=apps[al].id))
            if role:
                s.add(ApplicationUserRolePermission(user_id=u.id, application_role_id=roles[role].id))
            return u

        user("anil", ["engismart", "engismart_adas"])
        user("priya", ["engismart", "engismart_adas", "engismart_eds"])
        user("nodomain", ["engismart"])
        user("noapp", ["other_module", "engismart_adas"])
        user("sue", ["engismart"], role="engismart_superuser")
        user("dev", ["engismart"], role="engismart_developer")
        user("root", ["engismart"], admin="1")
        s.commit()
    yield


@pytest.fixture(scope="session")
def client():
    with TestClient(fastapi_app) as c:
        yield c


def H(name: str) -> dict:
    return {"access-token": make_token(name)}
