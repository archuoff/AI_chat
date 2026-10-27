# Engismart API  (prefix `{PREFIX}engismart`, header `access-token`)

Envelope on every JSON answer: `{"status": true|false, "data": ..., "message": "", "error": null}`.
Roles: **D** = developer only, **all** = developer, superuser and user (data limited by role and by the user's allowed domains).

| Method | Path | Role | What |
|---|---|---|---|
| GET | /me | all | who am I (role, allowed domains) |
| GET | /health | all | status; developers also get models, index location, chunk count |
| GET | /domains | all | domains (developers: with document counts) |
| GET | /users | D | platform users Engismart knows, with role, domains, 30-day usage |
| GET | /users/lookup?q= | D | find a platform user by name |
| PUT | /users/{id}/domains | D | limit the domains of a user (empty = all) |
| GET | /usage/summary?days= | D | questions and tokens per user and per day |
| POST | /documents/check | D | step 1 of an upload: read the file, suggest similar documents |
| POST | /documents/commit | D | step 2: ingest as new or as update of an existing document |
| POST | /documents | D | direct upload (scripts) |
| POST | /documents/ingest-folder | D | ingest a server-side folder |
| GET | /documents, /documents/{id}, /documents/{id}/chunks | D | library |
| DELETE | /documents/{id} | D | delete (an update's old version comes back) |
| PATCH | /documents/{id} , /documents/{id}/access | D | change domain, mark confidential |
| POST | /documents/bulk-domain, /documents/{id}/suggest-domain | D | domain tools |
| POST | /documents/{id}/restore | D | undo an update |
| POST | /documents/{id}/reprocess , PUT /documents/{id}/parse-options | D | re-process, apply sheet corrections |
| GET | /documents/{id}/excel-preview | D | sheet preview with pictures at their cells |
| POST | /documents/signatures | D | build similar-document data for older documents |
| POST | /search | D | raw hybrid search |
| GET | /images/summary, /documents/{id}/images, /images/job | D | pictures: counts, list, describe job state |
| POST | /images/describe, /images/job/cancel, /documents/{id}/images/extract | D | describe with the vision model, cancel, extract |
| PATCH | /images/{id} | D | include / exclude a picture |
| GET | /images/{id}/file?thumb= | all | the picture (same access rules as its document); **not** logged per request, not enveloped |
| POST | /chat | all | one question, full answer |
| POST | /chat/stream | all | the same as server-sent events (`status`, `token`, `reset`, `final`, `error`); **not** enveloped |
| GET | /chat/{session}/messages , DELETE /chat/{session} | all | the user's own conversation |
| POST | /warmup | all | pre-open the Azure connections while the user types |
