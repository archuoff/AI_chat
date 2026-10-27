"""Put Engismart into a Chromosome FastAPI (uv) project.

    python tools/assemble.py --template <project folder or template .zip> --out <new folder>      # build a complete copy
    python tools/assemble.py --template <your GitLab clone> --in-place                              # add Engismart to a clone

What it does (safe to run twice):
  1. copies our folders  services/engismart  and  controller/engismart  into the project
  2. edits five template files with the few lines Engismart needs:
       router/router_outlet.py   mounts the Engismart routers
       constants/constant.py     registers the module name
       pyproject.toml            adds our packages (run `uv lock` afterwards)
       setup.py                  Cython must not compile our Alembic scripts (they are loaded as source files)
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
OUR_DIRS = ("services/engismart", "controller/engismart")
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
DEPENDENCIES = [
    "langgraph>=1.0", "langgraph-checkpoint-sqlite>=2.0", "langchain-core>=1.0", "langchain-openai>=1.0",
    "langchain-text-splitters>=1.0", "azure-identity>=1.19", "alembic>=1.13", "psycopg[binary,pool]>=3.2",
    "langgraph-checkpoint-postgres>=2.0", "qdrant-client>=1.12", "fastembed>=0.4", "pypdf>=5.0", "docling>=2.132",
    "docling-core>=2.50", "python-docx>=1.1", "python-pptx>=1.0", "openpyxl>=3.1", "pillow>=10.4",
]


def _copy_tree(src: Path, dst: Path) -> int:
    n = 0
    for f in src.rglob("*"):
        if f.is_dir() or SKIP & set(f.relative_to(src).parts) or f.suffix in (".pyc", ".pyo"):
            continue
        target = dst / f.relative_to(src)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, target)
        n += 1
    return n


def _edit(path: Path, change, label: str, report: list[str]) -> None:
    if not path.exists():
        report.append(f"MISSING  {label}: {path} not found - add the lines by hand (see docs/MERGE_INSTRUCTIONS.md)")
        return
    text = path.read_text(encoding="utf-8")
    new = change(text)
    if new is None:
        report.append(f"already  {label}")
    elif new == text:
        report.append(f"UNCHANGED {label}: could not find the place to edit - add the lines by hand")
    else:
        path.write_text(new, encoding="utf-8")
        report.append(f"edited   {label}")


def _router(text: str) -> str | None:
    if "engismart" in text:
        return None
    lines = text.splitlines(keepends=True)
    last_import = max((i for i, l in enumerate(lines) if l.startswith(("from ", "import "))), default=-1)
    lines.insert(last_import + 1, ROUTER_IMPORT)
    out = "".join(lines)
    return out.rstrip("\n") + "\n" + ROUTER_BLOCK


def _constants(text: str) -> str | None:
    if "'engismart'" in text or '"engismart"' in text:
        return None
    marker = "    # Infrastructure layers"
    if marker in text:
        return text.replace(marker, CONSTANT_LINE + "\n" + marker, 1)
    return text.replace("MODULE_NAMES = {\n", "MODULE_NAMES = {\n" + CONSTANT_LINE, 1)


def _pyproject(text: str) -> str | None:
    if "langgraph" in text:
        return None
    start = text.find("dependencies = [")
    end = text.find("\n]", start)
    if start < 0 or end < 0:
        return text
    block = "".join(f'    "{d}",\n' for d in DEPENDENCIES)
    return text[:end + 1] + block + text[end + 1:]


def _setup(text: str) -> str | None:
    if '"migrations"' in text:
        return None
    return text.replace("skip_files = [\n", 'skip_files = [\n    "migrations",  # Engismart: Alembic loads its scripts as source files\n', 1)


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
    _edit(project / "router" / "router_outlet.py", _router, "router/router_outlet.py", report)
    _edit(project / "constants" / "constant.py", _constants, "constants/constant.py", report)
    _edit(project / "pyproject.toml", _pyproject, "pyproject.toml", report)
    _edit(project / "setup.py", _setup, "setup.py", report)
    if fix_cython:
        _edit(project / "setup.py", _cython_fix, "setup.py (Cython 3 fixes)", report)
    snippet = (HERE / "overlay" / "env.engismart.example").read_text(encoding="utf-8")
    for f in sorted(project.glob(".env.*.example")):
        _edit(f, lambda t: _env_example(t, snippet), f.name, report)
    gi = project / ".gitignore"
    if gi.exists() and "data/engismart" not in gi.read_text(encoding="utf-8"):
        gi.write_text(gi.read_text(encoding="utf-8").rstrip("\n") + "\n\n# Engismart local data\ndata/\n", encoding="utf-8")
        report.append("edited   .gitignore")
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
