# Findings and open questions (for the Chromosome team)

## Findings while building against the template (tested on Python 3.10 with SQLite as the platform database)
1. **Cython build.** With Cython 3.x, `python setup.py build_ext --inplace --production` fails on the template itself:
   `Expected str, got Form` in `controller/authentication/authentication.py` (annotation typing turns `x: str = Form(...)` into a type check), and
   setuptools rejects the unknown `--production` option before the script's own check. Two changes fix both (`tools/assemble.py --fix-cython`):
   `compiler_directives={"language_level": "3", "annotation_typing": False}` and removing `--production` from `sys.argv` before `setup()`.
   With them the whole project (166 modules, ours included) compiles, the sources are removed, and our tests pass against the compiled modules.
   Alembic loads its scripts as source files, so `migrations` is added to `skip_files`.
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
   `permissions_middleware` (the one `track_module_usage` uses).
5. Every request to `/engismart` writes one row to `tbl_chromosome_user_logs` (`track_module_usage`). Picture files are served by a second router without it
   because a sheet preview loads many thumbnails.

## Not done yet (waiting for answers)
* **Celery / RabbitMQ.** Long jobs (ingest, describe pictures, reprocess) still run inside the API process (threads). Moving them to a queue needs: queue name
  and vhost for a heavy task, where workers run, and a **Qdrant server** (the embedded Qdrant folder can be opened by one process only).
* **Database for chat memory.** LangGraph's PostgresSaver is used when the platform database is PostgreSQL, a SQLite file under `STORAGE_ROOT` otherwise.
  With MySQL the memory is per pod: please confirm the staging/production engine.
* How the `access-token` reaches the Angular remote's calls, including the streaming chat.
* ClamAV scan of uploads (`FILE_SCANNING_*`): mandatory for us? Not wired yet.
* Staging = UAT? Same stack as production?
