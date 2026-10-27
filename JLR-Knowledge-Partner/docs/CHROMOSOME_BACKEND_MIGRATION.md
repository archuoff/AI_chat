# Moving the backend into the Chromosome FastAPI (uv) boilerplate

Source: `chromosome-fastapi-uv-boilerplate-code` (zip shared by the team) and its `DEVELOPER_GUIDE.md`. Facts below are read from it;
anything marked **ASK** is a decision or fact we still need from the Chromosome team.

## 1. What the boilerplate is
A FastAPI service template ("api-gateway"; the Jenkinsfile builds it as its own microservice image for AWS ECR / Kubernetes).
- Python **3.10** (`.python-version`), packages with **uv** (`pyproject.toml` + `uv.lock`), start: `uv sync` then `uv run run.py`.
- Layers: `controller/<module>/{controller,helper,validator}.py` -> `db_resources/<module>_table_resources.py` -> `models/{model,orm_models}.py`.
  Cross-cutting: `middleware/`, `utility/` (settings, logger, celery_worker, error_handler), `helper/` (connectors), `services/`, `sockets/`.
- A new module = a controller folder + one `include_router` line in `router/router_outlet.py` + an alias in `constants/constant.py`
  + a row in `tbl_application`. Each router is wrapped with `track_module_usage("<alias>")`.
- **Auth is the platform's:** a global `AuthenticationMiddleware`, JWT (HS256, `python-jose`) in the header **`access-token`**,
  `UserContext` (user_id, username, display_name, is_admin, roles, permissions) and guards `get_current_user`, `require_admin`,
  `require_role`, `check_access("<app alias>", "<role>")`. RBAC tables: `tbl_users`, `tbl_application`, `tbl_application_roles`, groups ...
- **Response envelope for every endpoint:** `{"status": bool, "data": ..., "message": str, "error": str|None}`.
- Settings: `utility/settings.py` (pydantic-settings), environment `ENVIRONMENT` = development | staging | production | aws | test,
  file `.env.<ENVIRONMENT>`, system variables win. `PREFIX` is `/` (aws: `/api/v1/`). `SECRET_KEY` must be changed outside development.
- Database: SQLAlchemy 2 + `models/model.py` CRUD class, psycopg2 / pymysql (default port 3306; aws = PostgreSQL RDS). **No Alembic.**
- Celery + RabbitMQ (AMQPS), result backend = the SQL database, queue `SMALL_QUEUE_NAME` per environment; Socket.IO (python-socketio 4.6).
- slowapi rate limit, `X-Request-ID`, Prometheus `/metrics`, loguru JSON logs, `/health` (DB ping).
- ruff (E, W, F, I, UP, B; line length 120). Cython compile (`setup.py`) removes the .py files in the production image.
- Docker: multi-stage `python:3.10`, non-root user, `uvicorn --workers 1`; Jenkins builds, pushes to ECR, deploys to Kubernetes.

## 2. Where our code goes
| Ours today | In the boilerplate |
|---|---|
| `app/main.py` (33 routes, own login, own CORS) | `controller/engismart/controller.py` (+ split into several routers: documents, images, chat, usage), registered in `router_outlet.py` |
| `app/auth/*` (own users, JWT, roles, domains) | **dropped**: `UserContext` + `check_access("engismart", role)`. Roles developer / superuser / user = application roles. Our per-user *allowed domains* need a small table of our own (**ASK**) |
| `app/auth/db.py`, `usage.py`, `images/catalog.py` tables (`usage_events`, `upload_decisions`, `doc_images`) | `models/orm_models.py` + `db_resources/engismart_table_resources.py` (table prefix `tbl_`) |
| `app/ingestion`, `rag`, `graphs`, `images`, `store.py`, `llm.py`, `config.py` (the engine) | `services/engismart/...` (kept as one package, relative imports stay) |
| `app/config.py` (~60 settings) | our fields added to `utility/settings.py` (or a second Settings class reading the same `.env.<ENVIRONMENT>`) |
| in-process threads (describe job) and blocking ingest | Celery tasks `ingest_document`, `describe_pictures`, `reprocess_all` on a queue; progress in `tbl_tasks` |
| `data/sources`, `data/images` | `STORAGE_ROOT/engismart/...` on a volume shared by api and workers |
| Alembic (`migrations/`) | keep for OUR tables only, with its own version table name (`alembic_version_engismart`), so it never collides with the platform DB |
| SSE chat stream | `StreamingResponse` inside the module (check it passes `socketio_app` and the middleware) |
| `requirements*.txt` | `pyproject.toml` dependencies + `uv.lock` (checked: both sets resolve together on 3.10, 260 packages) |

## 3. Checked here
- All our tests pass on **Python 3.10.20** (69 app + 78 experiment).
- Boilerplate dependencies + ours resolve with `uv lock` (fastapi 0.162, pydantic 2.14, sqlalchemy 2.1, docling 2.143, torch 2.14, celery 5.6).
- Default torch pulls CUDA wheels (18 nvidia packages): use the CPU index in `[tool.uv.sources]` for the image (no GPU assumed).

## 4. Open questions for the Chromosome team (ASK)
1. Is our backend a **new microservice repo from this template** (like the "marshal" service), or a module inside an existing gateway repo?
2. Which database in staging / production: PostgreSQL (needed for chat memory with LangGraph PostgresSaver) or MySQL? Who creates our tables?
3. Roles and domains: can we register application alias `engismart` with roles developer / superuser / user, and how do we express "allowed domains per user"?
4. The frontend remote has "no auth logic": how does the `access-token` reach our API calls, **including the streaming chat (fetch / SSE)**?
5. Response envelope for streaming and file endpoints: exempt?
6. RabbitMQ: our own queue names (a heavy-task queue for Docling), vhost, and where workers run. Is a result backend in SQL OK for our job progress?
7. Qdrant: a server in each environment (embedded folder cannot be shared by api + workers). Who runs it?
8. Storage: `STORAGE_ROOT` shared volume or S3; is the ClamAV scan (`FILE_SCANNING_*`) mandatory for uploads?
9. Cython compile: mandatory for our module? (pydantic / dataclass / LangGraph state classes can break when compiled; we test before deciding.)
10. Image size / GPU: CPU-only acceptable? Where do the Docling models live (baked in image or mounted volume)?
11. Environment naming: is UAT = `staging`? Must staging use the same stack (Celery, RabbitMQ) as production?

## 5. Work plan
1. **Skeleton**: our module in the boilerplate layout (overlay: `controller/engismart`, `services/engismart`, `db_resources`, `models` additions, router line, constants alias,
   settings fields, `.env.*.example`, `pyproject.toml`). Tested here against an unmodified copy of the boilerplate, not committed to our repo.
2. **Auth swap**: drop login / users; `UserContext` everywhere; our domain table; usage rows keyed by platform user id.
3. **Envelope + routers**: split the 33 routes, wrap responses, keep SSE as the documented exception.
4. **Jobs**: Celery tasks + the in-process fallback switch (`JOBS_MODE=inline|celery`), progress in `tbl_tasks`.
5. **Tests**: current 69 tests ported (TestClient with a test token), plus contract tests for the envelope and auth guards; ruff clean.
6. **Docker / CI**: Dockerfile from theirs (CPU torch, models volume), compose for local, Cython smoke test.
7. Then features (transposed tables, retrieval measuring ...) in the new layout.
