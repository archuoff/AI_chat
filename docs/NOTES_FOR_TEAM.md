# Findings and open questions (for the Chromosome team)

## Findings while building against the template (tested on Python 3.10 with SQLite as the platform database)
1. **Cython build.** With Cython 3.x, `python setup.py build_ext --inplace --production` fails on the template itself:
   `Expected str, got Form` in `controller/authentication/authentication.py` (annotation typing turns `x: str = Form(...)` into a type check), and
   setuptools rejects the unknown `--production` option before the script's own check. Two changes fix both (`tools/assemble.py --fix-cython`):
   `compiler_directives={"language_level": "3", "annotation_typing": False}` and removing `--production` from `sys.argv` before `setup()`.
   With them the whole project (166 modules, ours included) compiles, the sources are removed, and our tests pass against the compiled modules.
2. **Admin flag.** `tbl_users.is_admin` is declared `String` but `UserContext.is_admin` is computed as `user.is_admin == 1`. That is true only if the
   database driver returns an integer. If admins are not recognised in staging, Engismart treats them as plain users (roles still work). Please confirm the column type.
3. **PyTorch size.** `docling` pulls PyTorch; the default wheels include CUDA (several GB). For servers without a GPU, add to `pyproject.toml`:
   ```
   [tool.uv.sources]
   torch = { index = "pytorch-cpu" }
   [[tool.uv.index]]
   name = "pytorch-cpu"
   url = "https://download.pytorch.org/whl/cpu"
   explicit = true
   ```
   (and `torch` in `dependencies`). It is not applied by default because it needs access to download.pytorch.org.
4. **Two permission modules.** `middleware/authentication.py` and `middleware/permissions_middleware.py` both define `UserContext` and the guards. We use
   `authentication._PermissionService` (roles and application rows); `track_module_usage` still uses the older copy.
5b. **Tables are not created automatically.** The `@app.on_event("startup")` + `create_all` at the end of `models/orm_models.py` belongs to a `FastAPI()` that is never served,
   and there is no Alembic or SQL in the template (the drawing validator's two tables have none either). Our one table comes with `docs/ENGISMART_TABLES.sql`. How do you apply table changes?
5. Every request to `/engismart` writes one row to `tbl_chromosome_user_logs` (`track_module_usage`). Picture files are served by a second router without it
   because a sheet preview loads many thumbnails.

## Questions for the team
1. How do you apply table changes in dev / UAT / production (SQL scripts, a manual `create_all`, something else)?
2. Which engine is each environment (the template defaults to MySQL on port 3306; only the `aws` config is PostgreSQL)? Chat memory uses
   `langgraph-checkpoint-mysql` on MySQL >= 8.0.19: is that third-party package approved? May the database user create tables (the chat memory makes four)?
3. May we add application rows `engismart_<domain>` to `tbl_application`? Do they show on the platform's home page or app lists? Who creates and assigns them in each environment?
4. Does anything read `tbl_langfuse_usage_logs`? May we write one row per LLM call there? Price per 1M input / output tokens of the chat deployment?
5. Upload: may the Word / PowerPoint / xlsm / txt / md formats be added next to csv/xlsx (we wrote `validator.validate_upload` for them; it can move to `common.py`)?
   Is ClamAV reachable in every environment, and what is the file size limit? `tbl_files.file_type` is a fixed list: we store `pdf` and `file`.
6. Endpoint style: we use `decode_token_and_get_user` + per-endpoint pattern through `helper.run_endpoint`, and keep Pydantic bodies for JSON. OK?
   The module folder has `chat/`, `ingestion/` and `core/` sub-folders (functions only) next to `controller.py`, `helper.py`, `validator.py`, `websocket.py`. OK?
7. Does the gateway buffer or time out the chat stream (server-sent events)? Does `BaseHTTPMiddleware` / SlowAPI keep it streaming?
8. Which header does the host's interceptor send: `access-token` or `Authorization: Bearer` (the backend reads only `access-token`)?
9. Is a Qdrant server available (the embedded folder can be opened by one process only)? Celery / RabbitMQ for long ingestion jobs (they run in the API process today)?
10. Cython mandatory? Staging = UAT? Remote path and name of the Angular remote?
11. Connection limits: the platform pool is 10 + 20 per process; the chat memory adds one connection per process.
