# Engismart backend: connections and changes

This file explains what the Engismart module is connected to in the Chromosome platform and what was changed compared with the first
version of this branch. It follows the platform's own pattern (see the drawing-validator module and `DEVELOPER_GUIDE.md` of the template).

## 1. Where everything is

Everything of ours is inside **one folder**, `controller/engismart/`. There is no `services/` folder any more.

```
controller/engismart/
  engismart_controller.py   the two routers the platform mounts (router + file_router); starts the search index in the background
  admin.py                  GET /me, /health, /domains
  chat.py                   POST /chat, /chat/stream, /warmup; GET /chat/{id}/messages; POST /chat/{id}/rewind; DELETE /chat/{id}
  documents.py              Manage knowledge: upload (check -> commit), library, corrections, access, domains, search
  pictures.py               pictures of documents: list, describe, include/exclude, the picture file
  helper.py                 run_endpoint (token -> role -> work in a thread pool -> envelope / 500 + audit log) and small helpers
  validator.py              request bodies (Pydantic)
  envelope.py               ok() / fail(): the platform's {status, data, message, error}
  access.py                 who may do what: token -> user -> roles and domains from the platform -> Principal
  file_upload.py            upload checks (extension, size, ClamAV, content) and the tbl_files row
  usage_log.py              tokens / cost / latency -> the platform's tbl_langfuse_usage_logs
  db.py                     the platform's engine (models/model.py) for our one table
  config.py                 settings (.env), Azure, Qdrant, retrieval tuning
  domains.py, classify.py   the six domains and the domain suggestion
  llm.py, store.py          Azure OpenAI clients; Qdrant search index
  uploads.py                files waiting between "check" and "commit"
  rag/ ingestion/ graphs/ images/   retrieval, reading documents, the LangGraph chat and ingest flows, picture catalog and describing
```

## 2. Connections to the platform

| Engismart needs | It uses (platform code or table) | Where in our code |
|---|---|---|
| Who is calling | `decode_token_and_get_user(request)` in `controller/common/common.py` (header `access-token`) | `access.authenticate` |
| Roles, application rows | `_PermissionService.fetch_roles_and_permissions` in `middleware/authentication.py`; tables `tbl_users`, `tbl_application`, `tbl_application_roles`, user/group permission maps | `access.py` |
| Domains of a person | platform application rows `engismart_<domain>` (no table of our own) | `access.domains_of` |
| Audit log | `application_logs(...)` -> `tbl_chromosome_user_logs` | `helper._audit`, `file_upload._audit` |
| Per-request tracking | `track_module_usage("engismart")` in `router_outlet.py` | assemble tool |
| Virus scan | `scan_file_content_for_virus` (ClamAV, `FILE_SCANNING_IP` / `FILE_SCANNING_PORT`) | `file_upload.check_upload` |
| Uploaded file list | table `tbl_files` (`file_type` = `pdf` or `file`, label from `CONSTANT`) | `file_upload.record_upload` |
| Tokens, cost, latency | table `tbl_langfuse_usage_logs` through `models().insert_record` | `usage_log.record` |
| Database connection | `models/model.py` (`engine`, `models`) | `db.py`, `usage_log.py`, `file_upload.py` |
| Labels | `constants/constant.py`: `MODULE_NAMES['engismart']`, `CONSTANT['file']` | assemble tool |
| Our one table | class `EngismartImage` in `models/orm_models.py` | `images/catalog.py` |
| Outside the platform | Azure OpenAI (chat, embeddings, pictures), Qdrant (embedded folder or server), the disk under `STORAGE_ROOT/engismart` | `llm.py`, `store.py`, `config.py` |

Roles (platform role aliases, set in `.env`: `ROLE_DEVELOPER`, `ROLE_SUPERUSER`; a platform admin acts as developer):

| | chat | confidential documents | Manage knowledge | token usage / plan in answers |
|---|---|---|---|---|
| normal user (no role) | yes, only the domains given to them | no | no | no |
| `engismart_superuser` | yes, every domain | yes | yes | no |
| `engismart_developer` | yes, every domain | yes | yes | yes |

A normal user must be given at least one domain (`engismart_<domain>` application row), otherwise every call answers 403
"No domain is assigned to you yet". Superusers and developers need no domain row.

## 3. What changed compared with the first version

**Moved**
* `services/engismart/*` -> `controller/engismart/` (rag, ingestion, graphs, images, store, llm, config, domains, classify, uploads).
* `controller/engismart/controller.py` -> `engismart_controller.py`; `images.py` (endpoints) -> `pictures.py` (it clashed with the `images/` package).

**Rewritten in the platform's style**
* Plain `APIRouter()` and `async def endpoint(request: Request)`; no `EnvelopeRoute`, no `Depends` auth.
* Every endpoint goes through `helper.run_endpoint`: `decode_token_and_get_user` first, then role check, then the blocking work in
  `run_in_threadpool`, and on an error `application_logs` + the platform's 500 answer `{status:false, message:"Something went wrong!", data:[], error}`.
  Answers keep the same envelope as before, so the frontends need no change for these endpoints.
* Request bodies are read after the login check (like the reference); a wrong body answers 422 in the envelope.
* No per-request `ensure_ready`: the search index opens once, in a background thread, when the router is imported
  (a problem there is logged and never stops the platform; a request that comes earlier waits for it).
* `get_store()` is now thread-safe (the start-up thread and a first request cannot open the embedded Qdrant folder twice).

**Removed**
* Our tables `tbl_engismart_user_access`, `tbl_engismart_usage`, `tbl_engismart_upload_decision`, the Alembic migrations and `db.py` engine/session.
* Endpoints `GET /users`, `GET /users/lookup`, `PUT /users/{id}/domains`, `GET /usage/summary` (Users & usage page). Domains are given in the platform;
  usage is read from `tbl_langfuse_usage_logs` (section 5). **The React and Angular screens that called them must be updated** (not part of this branch).
* The setting `ROLE_USER` (no role = plain user) and the database settings (`DATABASE_URL`, pool sizes): the platform's database is used.

**Added**
* `file_upload.py`: extension -> size -> ClamAV -> content-matches-extension, for every format we read; `tbl_files` row and audit line after the commit.
* `usage_log.py`: one row per chat question / classify / describe run in `tbl_langfuse_usage_logs`.
* MySQL chat memory (`langgraph-checkpoint-mysql`, `PyMySQLSaver`; MySQL >= 8.0.19). PostgreSQL and SQLite keep working.
* Settings: `MAX_UPLOAD_MB`, `VIRUS_SCAN`, `ACCESS_CACHE_S`, `WARM_UP_ON_START`, `LLM_PRICE_INPUT_PER_1M`, `LLM_PRICE_OUTPUT_PER_1M`.

## 4. The database

* Our own table: **`tbl_engismart_image`** (one row per picture found in a document: state, description, tokens). It is not replaceable by a
  platform table. Create it with `docs/ENGISMART_TABLES.sql` before the first start; the platform does not create tables by itself.
* Chat memory: `langgraph-checkpoint-mysql` creates its own tables (`checkpoints`, `checkpoint_blobs`, `checkpoint_writes`,
  `checkpoint_migrations`) the first time the chat is used. The database user needs CREATE TABLE rights, or DevOps runs the setup once.
* Rows to insert in platform tables (once per environment): `docs/REGISTER_APPLICATION.sql` (the `engismart` application, one application row per
  domain, the two roles).
* Everything else is the platform's tables: `tbl_users`, `tbl_application*`, `tbl_files`, `tbl_chromosome_user_logs`, `tbl_langfuse_usage_logs`.

## 5. Reading the token cost (developers)

One row per LLM call: `application_name` is `engismart` (a chat question), `engismart-classify` or `engismart-vision`; `trace_id` is the chat session id;
`token` = input + output tokens; `cost` = tokens x `LLM_PRICE_*_PER_1M` (0 while no price is set); `latency` in seconds.

```sql
-- per person, last 30 days
SELECT u.username, COUNT(*) AS calls, SUM(l.token) AS tokens, SUM(l.cost) AS cost
FROM tbl_langfuse_usage_logs l JOIN tbl_users u ON u.id = l.user_id
WHERE l.application_name LIKE 'engismart%' AND l.input_timestamp >= NOW() - INTERVAL 30 DAY
GROUP BY u.username ORDER BY tokens DESC;

-- per day
SELECT DATE(input_timestamp) AS day, SUM(token) AS tokens, SUM(cost) AS cost
FROM tbl_langfuse_usage_logs WHERE application_name LIKE 'engismart%' GROUP BY DATE(input_timestamp) ORDER BY day;
```
Not stored any more: the "answer found" flag, the input/output token split, the number of LLM calls.

## 6. Setup in one place

1. `python tools/assemble.py --template <project> --in-place` (or `--out <new folder>`), then `uv lock && uv sync`.
2. Fill the Engismart block of `.env.<environment>` (Azure, Qdrant, `STORAGE_ROOT`, prices, `FILE_SCANNING_*` of the platform).
3. Run `docs/ENGISMART_TABLES.sql`, then `docs/REGISTER_APPLICATION.sql` on the platform database.
4. In the platform's admin screens: give people the **Engismart** application and, for normal users, one or more **Engismart - <domain>** applications;
   give the roles `Engismart Superuser` / `Engismart Developer` to those who need them.
5. Start the app and call `GET /engismart/me` with a platform token.

## 7. What was and was not verified

Tested by assembling the template (`tools/assemble.py`) with this module and running the 39 tests in `tests/engismart/`
(`PROJ=<assembled project> uv run pytest tests/engismart`; add `DB_URL=<sqlalchemy url>` for PostgreSQL; offline, no Azure needed) through the platform's real app (`main.py`, the global
authentication middleware, `track_module_usage`, `decode_token_and_get_user`, `_PermissionService`) with real platform tables and real JWTs:

* login and access: missing token, user with one / two domains, user without a domain (403), user without the application (403), superuser, developer, platform admin;
* roles: Manage knowledge refused for normal users, ingest-folder for developers only, token usage and plan only in developers' answers;
* uploads: unsupported type, empty file, content not matching the extension, virus found (rejected and logged), scanner unreachable (refused), check -> commit,
  duplicate detection, multi-file upload, `tbl_files` row (`file`, "Document") and audit line;
* chat: answers only from the user's own domains, confidential documents hidden from users, history, rewind, delete, streaming, usage row in `tbl_langfuse_usage_logs`;
* errors: bad JSON / missing field answer 422 in the envelope; an internal error answers the platform's 500 and writes the audit log;
* `tools/assemble.py` is idempotent (a second run reports "already" everywhere); `ruff check controller/engismart` is clean with the template's rules.

Ran green on **SQLite** and on **PostgreSQL 16** (PostgreSQL chat memory included), and the whole project (template + ours) was compiled with Cython
(`setup.py build_ext --inplace --production`, with `--fix-cython`) and the same 39 tests passed against the compiled modules.

**Not verified (please check in UAT):**
* **MySQL on a live server.** None could be started here. The MySQL chat-memory wiring (`PyMySQLSaver`, reconnect before each use) is tested with a fake connection only;
  `ENGISMART_TABLES.sql` is written for MySQL 8 but was not run on one. Rewind and delete-session on `langgraph-checkpoint-mysql` are covered by the package, not by us.
* Real Azure OpenAI (tests run in offline mode with a fake embedder), real embedding / re-ranking models, Docling PDF reading (not installed in the test environment).
* A real ClamAV (the scan call is replaced in the tests); the Angular and React screens (they must drop the Users & usage page and the domain editor).
* Your platform's admin screens for the new application rows, and whether `engismart_<domain>` rows appear in the platform's application lists.
