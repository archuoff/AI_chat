# What to do on your side (backend)

You have two ways. Both end in the same project. Python 3.10+ is enough; the tool uses only the standard library.

## A. Let the tool do the copying and the small edits (recommended)
1. Get this branch onto the office PC (zip from your phone / Teams, or the text files).
2. Open a terminal in the folder that holds `tools/` and run, with the path of your GitLab clone (the folder that has `main.py`):
   ```
   python tools\assemble.py --template C:\path\to\your-gitlab-clone --in-place
   ```
   It prints what it did: the folder `controller/engismart` copied; `router/router_outlet.py`, `constants/constant.py`, `models/orm_models.py`,
   `pyproject.toml`, `Dockerfile`, every `.env.*.example` and `.gitignore` edited. Running it again changes nothing ("already").
   If a line says `UNCHANGED` or `MISSING`, send me that line; the by-hand version is in section B.
3. (Only if the team's Cython build fails with `Expected str, got Form` or `option --production not recognized`) run once more with `--fix-cython`.
   See NOTES_FOR_TEAM.md, item 1.

## B. By hand (what the tool does)
* Copy `controller/engismart` into the same place in your project.
* `router/router_outlet.py`: add `from controller.engismart import controller as engismart` with the other imports, and at the end of
  `register_router`:
  ```python
      app.include_router(engismart.router, prefix=f"{prefix}engismart", dependencies=[Depends(track_module_usage("engismart"))])
      app.include_router(engismart.file_router, prefix=f"{prefix}engismart")
  ```
* `constants/constant.py`: in `MODULE_NAMES` add `'engismart': 'Engismart',` and in `CONSTANT` add `'file': 'Document',`.
* `models/orm_models.py`: add the class `EngismartImage` (copy it from `ORM_BLOCK` in `tools/assemble.py`, before the `# Table Creation` comment; the file needs `Boolean` and `timezone` in its imports).
* `pyproject.toml`: add the packages listed in `DEPENDENCIES` at the top of `tools/assemble.py` to `dependencies`.
* `Dockerfile`: runtime stage, apt list add `libglib2.0-0` and `libgl1`; after `useradd` add
  `RUN mkdir -p /app/data && chown -R appuser:appuser /app/data`.
* `.env.<environment>.example`: append `overlay/env.engismart.example`.

## Then, in every case
1. **Packages:** `uv lock` then `uv sync` (the first lock downloads PyTorch for Docling; on a server without a GPU you can pin the CPU build, see NOTES_FOR_TEAM.md item 3).
2. **Settings:** copy the new block from `.env.<environment>.example` into the real `.env.<environment>` and fill it:
   * `DATABASE_*` is the platform's database, nothing new. The platform does not create tables by itself: run `docs/ENGISMART_TABLES.sql` (one table).
   * `FILE_SCANNING_IP` / `FILE_SCANNING_PORT` (ClamAV) must be reachable: every upload is scanned (`VIRUS_SCAN=on`).
   * `LLM_PRICE_INPUT_PER_1M` / `LLM_PRICE_OUTPUT_PER_1M`: prices of the chat deployment, for the cost column of `tbl_langfuse_usage_logs`.
   * Azure keys (`AZURE_OPENAI_*`), `DOCLING_ARTIFACTS_PATH` (your Hugging Face models folder), `QDRANT_URL` if the team runs a Qdrant server.
   * `STORAGE_ROOT`: where we write the search index, uploads and pictures (`<STORAGE_ROOT>/engismart/...`). Use a persistent volume.
3. **Register the application, domains and roles:** run `docs/REGISTER_APPLICATION.sql` on the platform database (or create the same in the platform's admin screens),
   then give yourself the application `Engismart` and the role `engismart_developer`. Every normal user needs the application plus at least one `Engismart - <domain>` application.
4. **Start:** `uv run run.py`, open `http://localhost:<PORT>/docs`, send a platform token in the `access-token` header,
   call `GET /engismart/me` (it must show your role), then `GET /engismart/health`.
5. **Check:** `uv run ruff check controller` (clean here), and upload one Excel through `POST /engismart/documents/check` + `/commit`.
6. **Commit** to your GitLab branch and open the merge request. Do not commit `.env.*` files with real values or the `data/` folder.

## What changed compared with the old stand-alone app (for the Angular work)
* URLs: `/api/...` became `{PREFIX}engismart/...` (documents, images, chat, domains, me, health). See docs/API.md.
* Header: `access-token: <platform JWT>` instead of `Authorization: Bearer`. The chat stream is `fetch()` with that header (not `EventSource`).
* Answers: `{status, data, message, error}`; errors have `status:false` and a readable `message`.
* No login or password endpoints; users, roles and domains are managed in the platform. The endpoints `/users`, `/users/lookup`, `/users/{id}/domains` and `/usage/summary` are gone:
  the Users & usage page and the domain editor must be removed from the screens. Manage knowledge is for superusers and developers; token usage only for developers (in the answers).
