# Starts the FastAPI backend on http://localhost:8000  (API docs: /docs)
$env:PYTHONIOENCODING = "utf-8"
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"
Set-Location $PSScriptRoot\backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
