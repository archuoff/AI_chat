# What to do on your side (backend)

You have two ways. Both end in the same project. Python 3.10+ is enough; the tool uses only the standard library.

## A. Let the tool do the copying and the small edits (recommended)
1. Get this branch onto the office PC (zip from your phone / Teams, or the text files).
2. Open a terminal in the folder that holds `tools/` and run, with the path of your GitLab clone (the folder that has `main.py`):
   ```
   python tools\assemble.py --template C:\path\to\your-gitlab-clone --in-place
   ```
   It prints what it did: two folders copied; `router/router_outlet.py`, `constants/constant.py`, `pyproject.toml`, `setup.py`, `Dockerfile`,
   every `.env.*.example` and `.gitignore` edited. Running it again changes nothing ("already").
   If a line says `UNCHANGED` or `MISSING`, send me that line; the by-hand version is in section B.
3. (Only if the team's Cython build fails with `Expected str, got Form` or `option --production not recognized`) run once more with `--fix-cython`.
   See NOTES_FOR_TEAM.md, item 1.

## B. By hand (what the tool does)
* Copy `controller/engismart` and `services/engismart` into the same places in your project.
* `router/router_outlet.py`: add `from controller.engismart import controller as engismart` with the other imports, and at the end of
  `register_router`:
  ```python
      app.include_router(engismart.router, prefix=f"{prefix}engismart", dependencies=[Depends(track_module_usage("engismart"))])
      app.include_router(engismart.file_router, prefix=f"{prefix}engismart")
  ```
* `constants/constant.py`: in `MODULE_NAMES` add `'engismart': 'Engismart',`.
* `pyproject.toml`: add the 18 packages listed in `DEPENDENCIES` at the top of `tools/assemble.py` to `dependencies`.
* `setup.py`: in `skip_files` add `"migrations",` (Alembic reads its scripts as source files; Cython must not compile them).
* `Dockerfile`: runtime stage, apt list add `libglib2.0-0` and `libgl1`; after `useradd` add
  `RUN mkdir -p /app/data && chown -R appuser:appuser /app/data`.
* `.env.<environment>.example`: append `overlay/env.engismart.example`.

## Then, in every case
1. **Packages:** `uv lock` then `uv sync` (the first lock downloads PyTorch for Docling; on a server without a GPU you can pin the CPU build, see NOTES_FOR_TEAM.md item 3).
2. **Settings:** copy the new block from `.env.<environment>.example` into the real `.env.<environment>` and fill it:
   * `DATABASE_*` is the platform's database, nothing new. Our tables are created at the first request.
   * Azure keys (`AZURE_OPENAI_*`), `DOCLING_ARTIFACTS_PATH` (your Hugging Face models folder), `QDRANT_URL` if the team runs a Qdrant server.
   * `STORAGE_ROOT`: where we write the search index, uploads and pictures (`<STORAGE_ROOT>/engismart/...`). Use a persistent volume.
3. **Register the application and roles:** run `docs/REGISTER_APPLICATION.sql` on the platform database (or create the same in the platform's admin screens),
   then give yourself the application and the `engismart_developer` role.
4. **Start:** `uv run run.py`, open `http://localhost:<PORT>/docs`, send a platform token in the `access-token` header,
   call `GET /engismart/me` (it must show your role), then `GET /engismart/health`.
5. **Check:** `uv run ruff check controller services` (clean here), and upload one Excel through `POST /engismart/documents/check` + `/commit`.
6. **Commit** to your GitLab branch and open the merge request. Do not commit `.env.*` files with real values or the `data/` folder.

## What changed compared with the old stand-alone app (for the Angular work)
* URLs: `/api/...` became `{PREFIX}engismart/...` (documents, images, chat, domains, users, usage, me, health). See docs/API.md.
* Header: `access-token: <platform JWT>` instead of `Authorization: Bearer`. The chat stream is `fetch()` with that header (not `EventSource`).
* Answers: `{status, data, message, error}`; errors have `status:false` and a readable `message`.
* No login or password endpoints; users and roles are managed in the platform. `GET /users` lists platform users Engismart knows; `PUT /users/{id}/domains` limits their domains.
