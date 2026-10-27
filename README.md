# Engismart service (Chromosome FastAPI module)

Engismart is a knowledge assistant over engineering documents (Excel, PDF, Word, PowerPoint): ingestion, hybrid search, answers with sources.
This repository holds **only our own files**, laid out at the paths of the Chromosome FastAPI (uv) template, so they drop into the platform's
project as a new module.

```
controller/engismart/      HTTP layer: documents, images, chat, admin routers + response envelope
services/engismart/        the engine: ingestion, chunking, search store, LLM, retrieval, pictures, tables, migrations
overlay/                   the .env block to add
tools/assemble.py          copies the two folders into a template project and edits the six template files that need a line
docs/                      MERGE_INSTRUCTIONS.md (what to do), REGISTER_APPLICATION.sql, API.md, NOTES_FOR_TEAM.md
```

* Login, users, groups and roles belong to the platform. Engismart reads them (`UserContext`) and maps three application roles
  (developer / superuser / user) to what a person may do. Allowed domains per user are kept in our own table.
* Every JSON answer uses the platform envelope `{status, data, message, error}`. The chat stream and picture files are not JSON.
* Our tables are `tbl_engismart_*` with their own Alembic history (`alembic_version_engismart`); they are created at the first request.
* Start with **docs/MERGE_INSTRUCTIONS.md**.
