# Engismart is already inside this project

This folder is the Chromosome FastAPI template with Engismart added. Nothing else in the template was changed except these files:
`router/router_outlet.py`, `constants/constant.py`, `pyproject.toml` (+ `uv.lock`), `setup.py`, `Dockerfile`, `.env.*.example`, `.gitignore`.
Engismart itself is in `controller/engismart/` and `services/engismart/`. More notes: `docs/engismart/`.

## Your steps (about 20 minutes, no coding)
1. **Environment file.** Copy `.env.development.example` to `.env.development` (or the file of your environment) and fill the normal platform values
   (`SECRET_KEY`, `DATABASE_*`). Fill the new Engismart block at the bottom: Azure keys, `DOCLING_ARTIFACTS_PATH`, `STORAGE_ROOT`.
   Never commit this file.
2. **Packages.** `uv sync` (first time: long, Docling downloads PyTorch).
3. **Register the application.** Run `docs/engismart/REGISTER_APPLICATION.sql` on the platform database, then give yourself the application
   and the role `engismart_developer` (platform admin screens).
4. **Start.** `uv run run.py`, open `http://localhost:<PORT>/docs`. Send your platform token in the header `access-token` and call
   `GET /engismart/me` (shows your role) and `GET /engismart/health`.
5. **Try an upload.** `POST /engismart/documents/check` with an Excel file, then `POST /engismart/documents/commit` with the returned `check_id`.
6. **Commit** to a branch of your GitLab repo and open the merge request. `docs/engismart/NOTES_FOR_TEAM.md` has the questions for the team.

If a step fails, send me the error text.
