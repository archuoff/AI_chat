"""Put Engismart into a Chromosome FastAPI (uv) project.

    python tools/assemble.py --template <project folder or template .zip> --out <new folder>      # build a complete copy
    python tools/assemble.py --template <your GitLab clone> --in-place                              # add Engismart to a clone

What it does (safe to run twice):
  1. copies our folder  controller/engismart  into the project
  2. edits the template files with the few lines Engismart needs:
       router/router_outlet.py   mounts the Engismart routers
       constants/constant.py     the module name (MODULE_NAMES) and the file label 'file' (CONSTANT)
       models/orm_models.py      the class of Engismart's one table, EngismartImage (tbl_engismart_image)
       pyproject.toml            adds our packages (run `uv lock` afterwards)
       Dockerfile                libraries the PDF reader needs + a writable data folder for the non-root user
       .env.*.example            lists our settings
  3. prints what it changed. Nothing else in the project is touched.
Only the Python standard library is used."""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
OUR_DIRS = ("controller/engismart",)
SKIP = {".git", "__pycache__", ".venv", "node_modules", ".ruff_cache", ".pytest_cache"}

ROUTER_IMPORT = "from controller.engismart import controller as engismart\n"
ROUTER_BLOCK = '''
    # Engismart - knowledge assistant. Every request to /engismart is tracked under alias "engismart";
    # picture files are served without per-request tracking (a sheet preview loads many thumbnails).
    app.include_router(
        engismart.router,
        prefix=f"{prefix}engismart",
        dependencies=[Depends(track_module_usage("engismart"))],
    )
    app.include_router(engismart.file_router, prefix=f"{prefix}engismart")
'''
CONSTANT_LINE = "    'engismart':      'Engismart',\n"
FILE_TYPE_LINE = "    'file': 'Document',  # Engismart: Excel / Word / PowerPoint / text documents (tbl_files.file_type has no finer value)\n"
ORM_MARKER = "# ------------------ Table Creation ------------------ #"
ORM_BLOCK = '''# ------------------ Engismart Picture Catalog ------------------ #
class EngismartImage(Base):
    """One picture found in an Engismart document (state, description, tokens). Create the table with docs/ENGISMART_TABLES.sql."""
    __tablename__ = 'tbl_engismart_image'

    id = Column(String(36), primary_key=True)
    doc_id = Column(String(64), nullable=False, index=True)
    position = Column(Integer, nullable=False, default=0)
    sha256 = Column(String(64), nullable=False, index=True)
    location = Column(JSON, nullable=False, default=dict)
    context = Column(Text, nullable=False, default="")
    width = Column(Integer, nullable=False, default=0)
    height = Column(Integer, nullable=False, default=0)
    status = Column(String(16), nullable=False, default="waiting", index=True)
    reason = Column(String(160), nullable=False, default="")
    manual = Column(Boolean, nullable=False, default=False)
    description = Column(Text, nullable=False, default="")
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    described_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


'''
DEPENDENCIES = [
    "langgraph>=1.0", "langgraph-checkpoint-sqlite>=2.0", "langgraph-checkpoint-mysql>=3.0", "langchain-core>=1.0", "langchain-openai>=1.0",
    "langchain-text-splitters>=1.0", "azure-identity>=1.19", "psycopg[binary,pool]>=3.2",
    "langgraph-checkpoint-postgres>=2.0", "qdrant-client>=1.12", "fastembed>=0.4", "pypdf>=5.0", "docling>=2.132",
    "docling-core>=2.50", "python-docx>=1.1", "python-pptx>=1.0", "openpyxl>=3.1", "pillow>=10.4",
]


def _copy_tree(src: Path, dst: Path) -> int:
    n = 0
    for f in src.rglob("*"):
        if SKIP & set(f.relative_to(src).parts) or f.suffix in (".pyc", ".pyo"):
            continue
        if f.is_dir():  # keep empty folders (the template has an empty certificates/)
            (dst / f.relative_to(src)).mkdir(parents=True, exist_ok=True)
            continue
        target = dst / f.relative_to(src)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, target)
        n += 1
    return n


def _read(path: Path) -> tuple[str, bool]:
    raw = path.read_bytes().decode("utf-8")
    return raw.replace("\r\n", "\n"), "\r\n" in raw  # edits are written for LF; Windows clones (CRLF) are handled


def _write(path: Path, text: str, crlf: bool) -> None:
    path.write_bytes((text.replace("\n", "\r\n") if crlf else text).encode("utf-8"))


def _edit(path: Path, change, label: str, report: list[str]) -> None:
    if not path.exists():
        report.append(f"MISSING  {label}: {path} not found - add the lines by hand (see docs/MERGE_INSTRUCTIONS.md)")
        return
    text, crlf = _read(path)
    new = change(text)
    if new is None:
        report.append(f"already  {label}")
    elif new == text:
        report.append(f"UNCHANGED {label}: could not find the place to edit - add the lines by hand")
    else:
        _write(path, new, crlf)
        report.append(f"edited   {label}")


def _router(text: str) -> str | None:
    if "engismart" in text:
        return None
    lines = text.splitlines(keepends=True)
    last_import = max((i for i, ln in enumerate(lines) if ln.startswith(("from ", "import "))), default=-1)
    lines.insert(last_import + 1, ROUTER_IMPORT)
    out = "".join(lines)
    return out.rstrip("\n") + "\n" + ROUTER_BLOCK


def _constants(text: str) -> str | None:
    new = text
    if "'engismart'" not in new and '"engismart"' not in new:
        marker = "    # Infrastructure layers"
        if marker in new:
            new = new.replace(marker, CONSTANT_LINE + "\n" + marker, 1)
        else:
            new = new.replace("MODULE_NAMES = {\n", "MODULE_NAMES = {\n" + CONSTANT_LINE, 1)
    if "'file':" not in new and '"file":' not in new:
        new = new.replace("    'pdf': 'PDF',\n", "    'pdf': 'PDF',\n" + FILE_TYPE_LINE, 1)
    return None if new == text else new


def _orm(text: str) -> str | None:
    """Adds the class of our one table. It needs Boolean and timezone, which the template's imports do not have."""
    if "EngismartImage" in text:
        return None
    new = text
    if "Boolean" not in new.split("# ------------------ Models")[0]:
        new = new.replace("from sqlalchemy import JSON,", "from sqlalchemy import JSON, Boolean,", 1)
    new = new.replace("from datetime import datetime\n", "from datetime import datetime, timezone\n", 1) if "timezone" not in new.split("# ------------------ Models")[0] else new
    if ORM_MARKER in new:
        return new.replace(ORM_MARKER, ORM_BLOCK + ORM_MARKER, 1)
    return new.rstrip("\n") + "\n\n\n" + ORM_BLOCK.rstrip("\n") + "\n"


def _pyproject(text: str) -> str | None:
    if "langgraph" in text:
        return None
    start = text.find("dependencies = [")
    end = text.find("\n]", start)
    if start < 0 or end < 0:
        return text
    block = "".join(f'    "{d}",\n' for d in DEPENDENCIES)
    return text[:end + 1] + block + text[end + 1:]


def _dockerfile(text: str) -> str | None:
    if "libgl1" in text:
        return None
    old = "    libpq-dev \\\n    curl \\\n && rm -rf /var/lib/apt/lists/*\n\n# Non-root user for security\nRUN useradd --create-home --shell /bin/bash appuser\n"
    new = ("    libpq-dev \\\n    curl \\\n    libglib2.0-0 \\\n    libgl1 \\\n && rm -rf /var/lib/apt/lists/*\n\n"
           "# Non-root user for security\nRUN useradd --create-home --shell /bin/bash appuser\n\n"
           "# Engismart writes its search index, uploads and pictures here (mount a volume on STORAGE_ROOT in production)\n"
           "RUN mkdir -p /app/data && chown -R appuser:appuser /app/data\n")
    return text.replace(old, new, 1)


def _cython_fix(text: str) -> str | None:
    """Only with --fix-cython. Two defects of the template's setup.py found when compiling it with Cython 3:
    annotation typing makes `x: str = Form(...)` fail at import, and setuptools rejects the unknown --production option."""
    if "annotation_typing" in text:
        return None
    text = text.replace('compiler_directives={"language_level": "3"}', 'compiler_directives={"language_level": "3", "annotation_typing": False}')
    text = text.replace("# Run setup (first part of the setup before removal)",
                        'PRODUCTION = "--production" in sys.argv\nif PRODUCTION:\n    sys.argv.remove("--production")\n'
                        "# Run setup (first part of the setup before removal)")
    return text.replace('if "--production" not in sys.argv:', "if not PRODUCTION:")


def _env_example(text: str, snippet: str) -> str | None:
    return None if "Engismart" in text else text.rstrip("\n") + "\n" + snippet


def assemble(template: Path, out: Path | None, in_place: bool, fix_cython: bool = False) -> list[str]:
    report: list[str] = []
    tmp = None
    if template.is_file() and template.suffix == ".zip":
        tmp = Path(tempfile.mkdtemp(prefix="tpl_"))
        with zipfile.ZipFile(template) as z:
            z.extractall(tmp)
        roots = [p for p in tmp.iterdir() if p.is_dir()]
        template = roots[0] if len(roots) == 1 and not (tmp / "main.py").exists() else tmp
    if not (template / "router" / "router_outlet.py").exists():
        raise SystemExit(f"{template} does not look like a Chromosome FastAPI project (router/router_outlet.py is missing)")
    if in_place:
        project = template
    else:
        project = out
        if project.exists() and any(project.iterdir()):
            raise SystemExit(f"{project} is not empty")
        project.mkdir(parents=True, exist_ok=True)
        _copy_tree(template, project)
        report.append(f"copied   template -> {project}")
    for d in OUR_DIRS:
        report.append(f"copied   {d} ({_copy_tree(HERE / d, project / d)} files)")
    shutil.copy2(HERE / "overlay" / "START_HERE.md", project / "ENGISMART_START_HERE.md")
    shutil.copy2(HERE / "ENGISMART_CHANGES.md", project / "ENGISMART_CHANGES.md")
    report.append(f"copied   docs -> docs/engismart ({_copy_tree(HERE / 'docs', project / 'docs' / 'engismart')} files), "
                  "ENGISMART_START_HERE.md, ENGISMART_CHANGES.md")
    _edit(project / "router" / "router_outlet.py", _router, "router/router_outlet.py", report)
    _edit(project / "constants" / "constant.py", _constants, "constants/constant.py", report)
    _edit(project / "models" / "orm_models.py", _orm, "models/orm_models.py", report)
    _edit(project / "pyproject.toml", _pyproject, "pyproject.toml", report)
    _edit(project / "Dockerfile", _dockerfile, "Dockerfile", report)
    if fix_cython:
        _edit(project / "setup.py", _cython_fix, "setup.py (Cython 3 fixes)", report)
    snippet = (HERE / "overlay" / "env.engismart.example").read_text(encoding="utf-8").replace("\r\n", "\n")
    for f in sorted(project.glob(".env.*.example")):
        _edit(f, lambda t: _env_example(t, snippet), f.name, report)
    _edit(project / ".gitignore", lambda t: None if "Engismart local data" in t else t.rstrip("\n") + "\n\n# Engismart local data\ndata/\n",
          ".gitignore", report)
    if tmp:
        shutil.rmtree(tmp, ignore_errors=True)
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--template", required=True, type=Path, help="the template project folder (or its .zip)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--out", type=Path, help="a new empty folder for the complete project")
    g.add_argument("--in-place", action="store_true", help="change the project given by --template")
    ap.add_argument("--fix-cython", action="store_true", help="also repair two defects of the template's setup.py (Cython 3 build)")
    a = ap.parse_args()
    for line in assemble(a.template, a.out, a.in_place, a.fix_cython):
        print(line)
    print("Next: uv lock && uv sync   (see docs/MERGE_INSTRUCTIONS.md)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
