# Engismart is already inside this project

This folder is the Chromosome FastAPI template with Engismart added. Nothing else in the template was changed except these files:
`router/router_outlet.py`, `constants/constant.py`, `models/orm_models.py` (one class), `pyproject.toml` (+ `uv.lock`), `Dockerfile`, `.env.*.example`, `.gitignore`.
Engismart itself is in `controller/engismart/`. What it connects to and what changed: `ENGISMART_CHANGES.md`. More notes: `docs/engismart/`.

## Your steps (about 20 minutes, no coding)
1. **Environment file.** Copy `.env.development.example` to `.env.development` (or the file of your environment) and fill the normal platform values
   (`SECRET_KEY`, `DATABASE_*`). Fill the new Engismart block at the bottom: Azure keys, `DOCLING_ARTIFACTS_PATH`, `STORAGE_ROOT`.
   Never commit this file.
2. **Packages.** `uv sync` (first time: long, Docling downloads PyTorch).
3. **Tables and application.** Run `docs/engismart/ENGISMART_TABLES.sql`, then `docs/engismart/REGISTER_APPLICATION.sql` on the platform database. Then give yourself
   the application `Engismart` and the role `engismart_developer` (platform admin screens). A normal user also needs one or more `Engismart - <domain>` applications.
4. **Start.** `uv run run.py`, open `http://localhost:<PORT>/docs`. Send your platform token in the header `access-token` and call
   `GET /engismart/me` (shows your role) and `GET /engismart/health`.
5. **Try an upload.** `POST /engismart/documents/check` with an Excel file, then `POST /engismart/documents/commit` with the returned `check_id`
   (every upload is scanned by ClamAV: `VIRUS_SCAN=off` in `.env` only on a machine without it).
6. **Commit** to a branch of your GitLab repo and open the merge request. `docs/engismart/NOTES_FOR_TEAM.md` has the questions for the team.

If a step fails, send me the error text.
