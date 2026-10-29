# Engismart API  (prefix `{PREFIX}engismart`, header `access-token`)

Envelope on every JSON answer: `{"status": true|false, "data": ..., "message": "", "error": null}`.
Roles: **D** = developer only, **M** = superuser or developer (Manage knowledge), **all** = developer, superuser and user (data limited by role and by the domains the person was given in the platform).
A normal user without any `engismart_<domain>` application row gets 403 on every call. Errors: `{status:false, message, error}` (platform 500: `Something went wrong!`).

| Method | Path | Role | What |
|---|---|---|---|
| GET | /me | all | who am I (role, domains) |
| GET | /health | all | status; developers also get models, index location, chunk count |
| GET | /domains | all | domains (superuser and developer: with document counts; normal users: the domains they were given) |
| POST | /documents/check | M | step 1 of an upload: read the file, suggest similar documents |
| POST | /documents/commit | M | step 2: ingest as new or as update of an existing document |
| POST | /documents | M | direct upload (scripts) |
| POST | /documents/ingest-folder | D | ingest a server-side folder (developer only: it reads a server path) |
| GET | /documents, /documents/{id}, /documents/{id}/chunks | M | library |
| DELETE | /documents/{id} | M | delete (an update's old version comes back) |
| PATCH | /documents/{id} , /documents/{id}/access | M | change domain, mark confidential |
| POST | /documents/bulk-domain, /documents/{id}/suggest-domain | M | domain tools |
| POST | /documents/{id}/restore | M | undo an update |
| POST | /documents/{id}/reprocess , PUT /documents/{id}/parse-options | M | re-process, apply sheet corrections |
| GET | /documents/{id}/excel-preview | M | sheet preview with pictures at their cells |
| POST | /documents/signatures | M | build similar-document data for older documents |
| POST | /search | M | raw hybrid search |
| GET | /images/summary, /documents/{id}/images, /images/job | M | pictures: counts, list, describe job state |
| POST | /images/describe, /images/job/cancel, /documents/{id}/images/extract | M | describe with the vision model, cancel, extract |
| PATCH | /images/{id} | M | include / exclude a picture |
| GET | /images/{id}/file?thumb= | all | the picture (same access rules as its document); **not** logged per request, not enveloped |
| POST | /chat | all | one question, full answer |
| POST | /chat/stream | all | the same as server-sent events (`status`, `token`, `reset`, `final`, `error`); **not** enveloped |
| GET | /chat/{session}/messages , DELETE /chat/{session} | all | the user's own conversation |
| POST | /warmup | all | pre-open the Azure connections while the user types |

Removed in this version: `/users`, `/users/lookup`, `PUT /users/{id}/domains`, `/usage/summary`. Domains are given in the platform; token usage is in `tbl_langfuse_usage_logs` (ENGISMART_CHANGES.md, section 5).
Bodies of `POST /chat`, `/commit` ... are JSON read after the login check; `POST /documents` and `/documents/check` are `multipart/form-data`.
