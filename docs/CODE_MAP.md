# Engismart code map: how the pieces connect

Read this before the code. It answers three questions: which layer does what, what happens step by step when something is done,
and where to look when something goes wrong. Function and file names are exact; use your editor's search to jump to them.

## 1. The layers

```
 browser / Angular remote                                   Chromosome platform (template)
        |                                                   -----------------------------
        v                                                   main.py  -> middleware (login check, rate limit, request id)
 router/router_outlet.py  --track_module_usage-->  one row per request in tbl_chromosome_user_logs
        |
        v
 controller/engismart/controller.py        35 endpoints, each a few lines
        |   calls
        v
 controller/engismart/helper.py            run_endpoint: token -> role -> work in a thread pool -> answer / error
        |   uses                                |  uses platform code: decode_token_and_get_user, _PermissionService,
        |                                       |  application_logs, models, scan_file_content_for_virus
        v
 controller/engismart/validator.py         request bodies + upload checks
        |
        +--------------------+---------------------+
        v                    v                     v
   chat/                ingestion/             core/            (chat/ and ingestion/ use core/, never each other)
   answer a question    load documents         shared engine: settings, Azure clients, Qdrant store, domains, Chunk, vocabulary, usage log
        |                    |                     |
        +--------------------+---------------------+
                             v
        Qdrant (search index)   Azure OpenAI (chat, embeddings, vision)   platform database (MySQL / PostgreSQL)   disk under STORAGE_ROOT/engismart
```

Three ideas explain most of the code:
* **Endpoints do no work.** `controller.py` only describes the route; the real work is in `chat/` and `ingestion/`.
* **Everything goes through `helper.run_endpoint`.** That is where login, roles, error handling and the audit log happen, once, for all 35 endpoints.
* **Two LangGraph flows.** `chat/chat_graph.py` answers a question; `ingestion/ingest_graph.py` loads a document. Each is a list of small steps (nodes) joined in order.

## 2. What happens on every request (helper.py)

1. `router_outlet.py` runs `track_module_usage("engismart")` (platform): checks the token, writes one audit-log row.
2. The endpoint in `controller.py` calls `run_endpoint(request, work, roles=..., body=...)`.
3. `authenticate(request)`: `decode_token_and_get_user` (platform) -> `load_principal` (cached ACCESS_CACHE_S seconds) -> `_read_principal`, which asks the platform for the person's roles and application rows (`_PermissionService`). Result: a `Principal` (id, role, domains).
   * No `engismart` application row -> 403. Role `user` with no `engismart_<domain>` row -> 403 "No domain is assigned". Role not allowed for this endpoint -> 403.
4. `read_body`: JSON into the Pydantic class of `validator.py` (wrong body -> 422), or the multipart form for uploads.
5. `work(p)` or `work(p, payload)` runs in a thread pool (`run_in_threadpool`) because it is blocking (Qdrant, LLM, database).
6. The return value becomes `{status, data, message, error}` (`ok`). A stream or file is returned as it is. `HTTPException` becomes the same envelope with its code. Any other error: `audit(...)` writes the audit line, the answer is the platform's 500 `Something went wrong!`.

## 3. Flow: someone asks a question (POST /chat)

| Step | Function | File | What it does |
|---|---|---|---|
| 1 | `chat` endpoint | controller.py | Calls `run_endpoint` with `ChatRequest`. |
| 2 | `access_filters(p, filters)` | helper.py | Adds the limits of the role: only the person's domains, no confidential documents, never superseded documents. Enforced inside the Qdrant query. |
| 3 | `run_chat(thread_id, ...)` | chat/chat_graph.py | Starts the LangGraph flow. The conversation is saved per user and session (memory in the database). |
| 4 | `plan_node` -> `plan_llm` | chat/chat_graph.py, chat/planner.py | Understands the question: intent (chit-chat or a real question), a standalone question, sub-questions, search phrases. An attached image is read first (`vision.describe`). |
| 5 | `prepare_node` -> `prepare`, `search_specs` | chat/retriever.py | Embeds every phrasing once and lists the searches to run. `searchjob.start` keeps them in memory. |
| 6 | `fan_out` -> `search_node` -> `run_search` (one branch per search, side by side) | chat/chat_graph.py, chat/retriever.py | Each search is one of three kinds: a structured lookup of a sheet or table (`store.scroll_chunks`), an exact-id keyword search, or a normal hybrid search (`store.search`: meaning + keywords). All use the filters from step 2. |
| 7 | `merge_node` -> `assemble` | chat/chat_graph.py, chat/retriever.py | Merges the hits (`merge_hits`), re-ranks them (`_score`), applies the gates, spreads evidence over documents (`_diversify`) and sub-questions (`_reserve_per_sub`), pulls in neighbouring rows and linked pictures (`_expand`, `_link_pictures`), asks the judge (`judge`). |
| 8 | route after merge | chat/chat_graph.py | Evidence found -> generate. Nothing found -> `rewrite_node` once (different phrasing), back to step 5. |
| 9 | `generate_node` -> `answer` | chat/chat_graph.py, chat/answer.py | `generate_llm` streams an answer with [n] citations; without Azure `compose_extractive` quotes the best rows. `cited_sources` lists the sources. |
| 10 | `record_turn` -> `usage_log.record` | helper.py, core/usage_log.py | One row in tbl_langfuse_usage_logs (tokens, cost, latency, session id). |
| 11 | `public_result` | helper.py | Removes the plan and the token counts unless the person is a developer. |

Variants: `/chat/stream` runs the same graph with `graph.stream`, sending status / token / final events (server-sent events). `/chat/{id}/rewind` (`rewind_session`) goes back to an earlier turn so an edited question is answered without the later turns. `/chat/{id}` DELETE (`delete_session`) forgets a conversation.

## 4. Flow: someone uploads a document (Manage knowledge)

**Step 1, POST /documents/check**
1. `read_limited` (validator.py): reads the file, refuses it above MAX_UPLOAD_MB.
2. `validate_upload` (validator.py): extension supported -> not empty -> ClamAV (`scan_file_content_for_virus`, platform) -> content matches the extension. Any failure is an HTTP error and, for a virus, an audit line.
3. `uploads.new_path` (ingestion/uploads.py): the file is kept in a waiting folder.
4. `parse_file` (ingestion/__init__.py): picks the reader by extension (excel.py, documents.py, pdf_docling.py).
5. `similarity.sample_texts / build_signature / suggest` (ingestion/similarity.py): finds exact copies and similar documents among those the person may see.
6. `uploads.add`: remembers the check. The answer holds `check_id` and the suggestions.

**Step 2, POST /documents/commit** (the person chose "new" or "update of ...")
1. `uploads.get(check_id)`; checks for a name clash or a duplicate.
2. `run_ingest` (ingestion/ingest_graph.py), a LangGraph flow: `fingerprint` (same content already there? skip) -> `parse` (reuses the check's result) -> `chunk` (`build_chunks`, ingestion/chunker.py) -> `index` (`store.index_document`, `invalidate_vocabulary`) -> `images` (`catalog.sync`: one row per picture in tbl_engismart_image) -> `signature` (similarity data for later checks).
3. `record_upload` (helper.py): one row in `tbl_files` and an audit line.
4. If it is an update: the old document is marked superseded (hidden from chat, can be restored).

Other Manage knowledge endpoints are one-liners over `core/store.py`: change domain or confidential flag, delete, restore, list, chunks, search. `PUT /parse-options` and `/reprocess` run `run_ingest` again on the stored original (`source_file`).

## 5. Flow: describing pictures (POST /images/describe)

`start_job` (ingestion/images/describe.py) starts a background thread -> `_run` describes each waiting picture with the vision model (`_describe_one`, `parse_answer`) -> `catalog.record_result` stores the text -> `share_with_duplicates` copies it to identical pictures -> `catalog.index_described` writes picture chunks into Qdrant so chat can find them -> `usage_log.record(kind="vision")`. `GET /images/job` returns the progress (polled by the screen).

## 6. Where to look when ...

| Problem | Start here |
|---|---|
| 401 / 403 on every call | helper.authenticate, load_principal, _read_principal; then the application and role rows in the platform |
| 403 "No domain is assigned" | The person has no `engismart_<domain>` application row |
| Upload refused | validator.validate_upload (type, size, virus, content); ClamAV settings |
| Upload accepted but nothing found in chat | ingestion/ingest_graph.py (run_ingest report), the reader for that file type, then domain and confidential flags in core/store.py |
| Wrong or empty answer | chat/planner.py (was the question understood?), chat/retriever.py (assemble: gates, spread), chat/judge.py, chat/answer.py |
| An answer should not show a document | helper.access_filters and the document's domain / confidential / superseded flags |
| Chat forgets earlier questions | chat/chat_graph.py (_mysql_checkpointer / _postgres_checkpointer), database permissions |
| Pictures not described | ingestion/images/describe.py, vision deployment in core/config.py |
| Token numbers missing | core/usage_log.py, table tbl_langfuse_usage_logs |
| A setting is ignored | core/config.py (field name = the .env name in capitals) |

## 7. File index (public functions and classes; names starting with _ are internal)

| File | Use | Main functions / classes |
|---|---|---|
| `chat/answer.py` | Writes the answer with [n] citations: with the LLM (streamed) or extractive without it; picks the cited sources. | compose_extractive(), generate_llm(), answer(), cited_sources() |
| `chat/chat_graph.py` | The LangGraph chat flow (plan, prepare, search x N, merge, rewrite, generate) and the saved conversation memory (MySQL / PostgreSQL / SQLite). | ChatState, plan_node(), prepare_node(), fan_out(), search_node(), merge_node(), rewrite_node(), generate_node(), smalltalk_node(), build_chat_graph(), get_chat_graph(), close_chat_memory(), turn_input(), config_for() ... |
| `chat/judge.py` | Asks the LLM which retrieved passages really help answer the question. | JudgedPassage, Judgement, judge() |
| `chat/planner.py` | Understands the question: intent, a standalone question, sub-questions, search phrases, ids to look for. | QueryPlan, plan_rules(), needs_llm_planning(), plan_llm() |
| `chat/retriever.py` | Searches, merges the hits, re-ranks, applies gates, spreads evidence over documents and sub-questions, pulls in neighbouring rows and pictures. | search_specs(), run_search(), run_specs(), merge_hits(), prepare(), retrieve(), assemble() |
| `chat/searchjob.py` | Keeps the searches of one question in memory so they can run side by side. | start(), spec(), count(), add(), finish() |
| `chat/vision.py` | Images attached to a question: validate, hold for one turn, describe with the vision model. | validate_images(), hold(), get(), release(), image_parts(), describe() |
| `controller.py` | All 35 endpoints. Each one is a few lines: it calls helper.run_endpoint with a small `work` function that calls chat/ or ingestion/ code. |  |
| `core/chunk.py` | The Chunk class: the unit that is embedded, stored and searched. | Chunk |
| `core/config.py` | All settings from .env (Azure, Qdrant, retrieval tuning, upload limit, prices) and the platform database URL. | Settings, get_settings() |
| `core/domains.py` | The six domains and their keywords. | Domain, validate_domain(), domains_payload() |
| `core/llm.py` | The model clients: Azure chat / vision / embeddings, local embeddings, keyword (BM25) vectors, the re-ranker, token counting. | Embedder, LocalEmbedder, AzureEmbedder, get_embedder(), SparseEmbedder, get_sparse_embedder(), Reranker, get_reranker(), get_chat_model(), get_vision_model(), add_usage(), warm_connections(), describe_llm_error() |
| `core/store.py` | The Qdrant search index: save a document and its chunks, search (dense + keyword), list / change / delete documents. | doc_id_for(), KGStore, get_store() |
| `core/usage_log.py` | Writes tokens, cost and latency of one LLM call to tbl_langfuse_usage_logs. | cost_of(), record() |
| `core/vocab.py` | Names found in the data (sheets, vehicles), used to recognise them in questions. Rebuilt after every ingest. | norm_tokens(), norm(), content_tokens(), entity_key(), Vocabulary, invalidate_vocabulary(), get_vocabulary() |
| `helper.py` | Common helpers: the endpoint runner (token, role, thread pool, errors), who-may-do-what (roles, domains, search filters), the answer envelope, small document and chat helpers, the tbl_files record. | ok(), fail(), Principal, role_of(), domains_of(), load_principal(), authenticate(), access_filters(), warm_up(), audit(), read_body(), run_endpoint(), checked_domain(), parse_meta() ... |
| `ingestion/__init__.py` | parse_file: picks the reader by file extension. SUPPORTED_EXTENSIONS lives here. | parse_file() |
| `ingestion/chunker.py` | Cuts parsed content into chunks, adds the breadcrumb and the links between neighbouring chunks. | breadcrumb_of(), add_relations(), split_semantic(), build_chunks() |
| `ingestion/classify.py` | Suggests a domain for a document (keywords, or the LLM). | DomainSuggestion, suggest_domain() |
| `ingestion/cleaning.py` | Removes noise (headers, footers, repeated logos) without AI. | clean_text_elements(), filter_images(), clean_document() |
| `ingestion/documents.py` | Readers for PDF (Docling or pypdf), Word, PowerPoint, text, markdown and CSV. | parse_pdf(), parse_docx(), parse_pptx(), parse_text(), parse_csv() |
| `ingestion/excel.py` | Excel reader: finds every table on every sheet, one record per row, pictures with their cell. | is_picture(), addr(), TableInfo, analyze_sheet(), parse_excel() |
| `ingestion/images/catalog.py` | The picture catalog: one database row per picture (tbl_engismart_image), their files, their search chunks. | utcnow(), iso(), image_dir(), file_path(), public(), sync(), delete_document(), list_images(), get_image(), summary(), summaries_by_document(), waiting(), set_included(), share_with_duplicates() ... |
| `ingestion/images/describe.py` | The background job that asks the vision model to describe waiting pictures. | estimate(), config(), status(), cancel(), parse_answer(), start_job() |
| `ingestion/incell.py` | Reads "Place in Cell" pictures of Excel (which openpyxl cannot). | InCellPicture, read_incell_pictures() |
| `ingestion/ingest_graph.py` | The LangGraph loading flow (fingerprint, parse, chunk, index, images, signature) and run_ingest. | IngestState, fingerprint(), parse(), chunk(), index(), images(), signature(), rebuild_signature(), refresh_images(), source_dir(), source_file(), keep_source_copy(), build_ingest_graph(), run_ingest() |
| `ingestion/models.py` | Element, RawImage, ParsedDocument: the common format every reader produces. | Element, RawImage, ParsedDocument |
| `ingestion/pdf_docling.py` | PDF reader using Docling (layout, tables, pictures). | convert(), export_chunk_ready(), to_parsed_document(), parse_pdf_docling() |
| `ingestion/preview.py` | Builds the Excel sheet preview for Manage knowledge. | build_excel_preview() |
| `ingestion/similarity.py` | Finds documents that look like an uploaded file (same name, same content, same topic). | clean_name(), name_score(), normalize(), content_codes(), size_of(), mean_vector(), cosine(), sample_texts(), build_signature(), jaccard(), document_frequency(), classify(), suggest() |
| `ingestion/tables.py` | Turns tables inside Word and PowerPoint into records. | table_to_elements(), dedupe_merged() |
| `ingestion/uploads.py` | Keeps a checked file between the "check" and "commit" steps. | Pending, new_path(), add(), get(), discard(), cleanup() |
| `ingestion/utils.py` | Small cleaning helpers for cell values. | clean_text(), normalize_value(), is_textual(), render_fields(), unique_keys() |
| `validator.py` | All validators: the JSON request bodies and the upload checks (extension, size, virus scan, content). | SearchRequest, FolderIngestRequest, ParseOptionsUpdate, DomainUpdate, BulkDomainUpdate, AccessUpdate, ImageUpdate, DescribeRequest, CommitRequest, ChatRequest, RewindRequest, content_matches_extension(), read_limited(), validate_upload() |
| `websocket.py` | Empty for now. |  |

## 8. Ways to learn the code yourself
* Start the app and open `/docs` (FastAPI lists every route). Call `/engismart/me`, then `/engismart/chat` and read the log.
* Search the code for a function name from section 3 or 4 and follow the calls; every step above is one function.
* Read in this order: `controller.py` (one endpoint), `helper.run_endpoint`, `chat/chat_graph.py` (`build_chat_graph` shows the whole flow in 15 lines), then `ingestion/ingest_graph.py` (`build_ingest_graph`).
* Set `WARM_UP_ON_START=false` and `VIRUS_SCAN=off` on your own PC to start faster and without ClamAV.
