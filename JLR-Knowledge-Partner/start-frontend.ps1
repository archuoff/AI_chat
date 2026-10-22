# Starts the React UI on http://localhost:5173 (proxies /api to the backend on :8000)
Set-Location $PSScriptRoot\frontend
npm run dev -- --port 5173
