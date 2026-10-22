# Frontend

React 19 + Vite + Tailwind CSS 4, themed with the Tata Technologies palette (`src/index.css`).

```powershell
npm install
npm run dev      # http://localhost:5173, proxies /api to the backend on :8000
npm run build
```

* `src/chat/`   assistant: streaming answers, citation chips, sources panel, scope filter
* `src/kb/`     knowledge base: stats, upload with metadata fields, documents table, chunk inspector
* `src/lib/`    API client (SSE streaming), types, local session storage
