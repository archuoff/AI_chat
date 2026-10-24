# Engineering Knowledge Assistant

RAG assistant over Excel / PDF / Word / PowerPoint documents, organised into engineering domains.
FastAPI + LangGraph backend, Qdrant vector store, Azure OpenAI, React UI in Tata Technologies colours.

```
C:\KG
├── backend\    Python: ingestion pipeline, RAG chat pipeline, API   (see backend\README.md)
├── frontend\   React + Vite + Tailwind UI
└── DATA\       source documents
```

## Run
Double-click **`Start JLR Knowledge Partner.bat`**. The first time it installs whatever is missing
(Python 3.12, Node.js, the backend and frontend packages) and asks for the Azure OpenAI key; afterwards it
just starts the backend and frontend (two minimized windows) and opens http://localhost:5173.

Manual alternative, two terminals:
```powershell
.\start-backend.ps1     # http://localhost:8000   (API docs at /docs)
.\start-frontend.ps1    # http://localhost:5173   <- open this in the browser
```

## Moving to another PC
1. On the old PC, stop the app, then build the package (knowledge base, accounts, pictures and documents included;
   secrets, installed packages and caches left out):
   `backend\.venv\Scripts\python.exe scripts\make_package.py "D:\some\folder"`
2. Copy the two files it creates (`JLR-Knowledge-Partner.zip` and `Install JLR Knowledge Partner.bat`) into one
   folder on the new PC and double-click the `.bat`. It unpacks, installs, asks for the key once and starts.
   Any folder works; sign in with the same accounts (everyone signs in again once).
3. Needs internet on first start (Python / npm packages and the local search models).

## Screens
* **Assistant**: chat with citations; scope a question to one domain (ADAS, Benchmarking, EDS, Lead Engineering,
  Materials Net, Supplier Database) and/or a file type. Each answer shows its response time (hover for the per-step breakdown).
* **Manage knowledge**: domain overview; add documents into a domain; per document:
  * *Overview*: sheets, tables, records, chunks, data-captured %, corrections, metadata
  * *Sheet preview* (Excel): the original grid, every cell coloured by how it was interpreted
    (header / data / title / section / ignored / not captured / excluded); correct header rows or exclude
    tables/sheets, then *Apply & re-process*
  * *Extracted records*: exactly the rows the assistant can read
  * *Chunks*: what is stored in Qdrant
  * Move to another domain (labels updated in place, verified) or let Azure OpenAI *Suggest* the domain

## Accounts & access
Sign-in is JWT based; accounts, usage and picture records live in SQLite (`backend\data\app.db`) by default, or in PostgreSQL when
`DATABASE_URL` is set (see `backend\README.md`, section *Database*).

| Role | Can do |
|---|---|
| **User** | Chat. Only the domains assigned to them (none = all domains). Never sees documents marked *confidential*. |
| **Super user** | Chat across every domain, including confidential documents. |
| **Developer** | Everything: *Manage knowledge* (ingest, inspect, correct, classify, mark confidential) and *Users & usage* (create/edit/disable accounts, per-user questions and token usage). |

Restrictions are enforced inside the Qdrant search itself (domain + confidential filters), not only in the UI.
Conversations are stored per user. The last active developer cannot be removed or demoted.

Create the first developer from the command line (works while the API is running):
```powershell
cd C:\KG\backend; .\.venv\Scripts\python.exe -m app.cli create-user admin --role developer
```

## Configuration
`backend\.env` (see `backend\.env.example`): Azure OpenAI endpoint, chat + embedding deployments.
Without Azure the assistant runs in extractive mode with local models.
Changing the embedding model changes the vector size: use a new `COLLECTION_PREFIX` and re-ingest.

## Pictures in documents
Every upload extracts its pictures (PowerPoint, Word, PDF, Excel, with slide / page / cell and the text
around them) into `backend\data\images`. Icons, banners, repeated logos and duplicates are skipped
automatically. Pictures stay **waiting** until a vision model is connected; nothing is sent to Azure before.

To switch describing on (use the **company** Azure resource), add to `backend\.env` and restart:
```
AZURE_OPENAI_VISION_DEPLOYMENT=<vision-capable deployment, e.g. gpt-4.1-mini>
AZURE_OPENAI_VISION_ENDPOINT=https://<company-resource>.openai.azure.com/   # empty = main endpoint
AZURE_OPENAI_VISION_API_KEY=<company key>                                   # empty = main key
# optional: VISION_REASONING_MODEL=true for gpt-5 / o-series, VISION_PRICE_INPUT_PER_1M / _OUTPUT_PER_1M for cost estimates
```
Then Manage knowledge → document → **Pictures** (or the library overview) → **Describe**. The count and a
token estimate are shown before anything runs. Descriptions become searchable, and cited pictures show as
thumbnails in the chat sources. Re-processing a document keeps existing descriptions (no second charge).
Pictures of documents ingested earlier: `python -m app.cli extract-images` (backend stopped).

## Quality check
```powershell
# stop the backend first (embedded Qdrant allows one process)
cd C:\KG\backend; .\.venv\Scripts\python.exe -m app.eval --show-misses
```
