# KG Assistant – backend

Ingests Excel / PDF / Word / PowerPoint / CSV / TXT / MD into Qdrant (hybrid dense + BM25 search).
LLM: Azure OpenAI when configured in `.env`, otherwise offline mode.

## Setup
```powershell
cd C:\KG\backend
C:\Users\Dell\anaconda3\python.exe -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env   # optional: fill in Azure values
```

## Run the API
```powershell
.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```
Swagger UI: http://localhost:8000/docs

| Method | Path | Purpose |
|---|---|---|
| GET | /api/health | mode, models, counts |
| POST | /api/documents | upload files (`files`, `metadata` = JSON of manual fields, `force`) |
| POST | /api/documents/ingest-folder | `{"path": "C:\\KG\\DATA", "meta": {...}}` |
| POST | /api/documents/check | step 1 of the upload popup: reads the file once, returns exact copies + similar documents (name / content / topic) |
| POST | /api/documents/commit | step 2: add the checked file as `new` or as an `update` of an existing document (the old version is hidden, not deleted) |
| POST | /api/documents/{id}/restore | bring a replaced version back |
| POST | /api/documents/signatures | build the similar-document data of documents ingested earlier (CLI: `build-signatures`) |
| GET | /api/documents | list ingested files |
| GET | /api/documents/{id}/chunks | inspect chunks |
| DELETE | /api/documents/{id} | remove a file and its chunks |
| POST | /api/search | `{"query": "...", "top_k": 8, "mode": "hybrid", "filters": {"meta.project": "EDS"}}` |

## CLI (stop the API first – embedded Qdrant allows one process at a time)
```powershell
.venv\Scripts\python.exe -m app.cli ingest C:\KG\DATA --meta "{\"project\": \"EDS\"}"
.venv\Scripts\python.exe -m app.cli search "magnesium cross car beam"
.venv\Scripts\python.exe -m app.cli docs
```

## Pipeline (LangGraph, `app/graphs/ingest_graph.py`)
`fingerprint → (unchanged? skip) → parse → chunk → index`

* `app/ingestion/` – one parser per format, all producing `Element`s (`text` or `record` = table row with exact values)
* `app/ingestion/chunker.py` – records stay whole rows (wide rows split by columns, key repeated); text split recursively
* `app/store.py` – Qdrant collections `kg_chunks` (dense + sparse) and `kg_documents` (registry)

## Similar documents and updated versions
Every ingested document keeps a small signature (`ingestion/similarity.py`): hashes of its cleaned cells / lines, a topic vector
(mean of its chunk vectors) and its size. The upload popup uses it, with the cleaned file name and the file fingerprint, to suggest
"likely update" / "related" documents with the reasons; no LLM is involved and the SME decides. Choosing *Update of ...* sets
`superseded` on the old document (chunks + registry) and `access_filters` hides it from chat for every role; *Restore* undoes it,
deleting the update brings the old version back, and an update of a confidential document stays confidential. The previous original of
an in-place update is archived under `data/sources/<doc_id>/versions/`. Thresholds: `SIM_*` in `app/config.py` (calibrate them on real files).
Tests: `pytest backend/tests` (fake embedders, no model download).

## Database: SQLite or PostgreSQL
Accounts, usage events, upload decisions and picture records are SQL tables; chat memory (follow-up context) is stored by LangGraph in
the same database. With `DATABASE_URL` empty everything uses SQLite files in `data\` (`app.db`, `chat_memory.sqlite`). With
`DATABASE_URL=postgresql+psycopg://user:password@host:5432/dbname` everything uses PostgreSQL. Document files (`data\sources`, `data\images`)
and the Qdrant search store are separate and unaffected.

**Schema changes** are Alembic migrations (`backend/migrations`). The app upgrades the database to the latest revision at start-up (on
PostgreSQL under a lock, so two processes never race). A database created by an older version is adopted without touching its rows. For
a developer adding a column: change the model, then `alembic revision --autogenerate -m "what changed"` in `backend\`, review the file,
commit it. LangGraph's own `checkpoint*` tables are created by LangGraph and are not part of Alembic.

**Set up a local PostgreSQL (Windows, once):**
1. Install PostgreSQL 16 or newer (EDB installer from postgresql.org, or Docker: `docker run -d --name kp-pg -p 5432:5432 -e POSTGRES_PASSWORD=admin -v kp-pg:/var/lib/postgresql/data postgres:16`).
2. Create the user and database (psql as the `postgres` user):
   ```sql
   CREATE ROLE kp_user LOGIN PASSWORD 'choose-a-password';
   CREATE DATABASE knowledge_partner OWNER kp_user ENCODING 'UTF8';
   ```
3. Put `DATABASE_URL=postgresql+psycopg://kp_user:choose-a-password@localhost:5432/knowledge_partner` in `backend\.env`.
4. **Move the existing accounts** (stop the backend first; the SQLite file is only read, never changed):
   ```powershell
   cd C:\KG\backend
   .\.venv\Scripts\python.exe -m app.cli migrate-db
   ```
   It creates the tables, copies users (with their ids, roles, domains and password hashes), usage and picture records, moves the id
   counters, and prints row counts and checksums for both sides. Re-run with `--replace` to empty and copy again. Chat memory is not copied:
   conversations start empty on PostgreSQL.
5. Start the backend and sign in with an existing account.

**Back up / restore:** `pg_dump -Fc -U kp_user knowledge_partner > kp.dump` and `pg_restore -U kp_user -d knowledge_partner --clean kp.dump`.
**Go back to SQLite:** empty `DATABASE_URL` again; the old `data\app.db` still holds everything up to the day of the copy.

**Tests:** `pip install -r requirements-dev.txt`, then `pytest backend/tests`. Set `TEST_DATABASE_URL=postgresql+psycopg://user:pw@host/testdb`
(an empty throw-away database: its `public` schema is dropped for every test) to run the same suite on PostgreSQL.
