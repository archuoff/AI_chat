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
