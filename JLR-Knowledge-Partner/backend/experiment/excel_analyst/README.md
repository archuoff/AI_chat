# Excel layout analyst (experiment)

This is the first LLM stage: it proposes a structural map from an existing Excel extraction.
It does not change cell values, modify the extractor output, approve extraction completeness,
describe image pixels, run the second LLM validation stage, create chunks, or index documents.
The existing application and extractor are unchanged.

## Input and flow

Use the folder produced by `python -m experiment.excel_extractor extract ... --out ...`.
It must contain **model.json and cells/*.jsonl**, not just report.html or layout.json.

1. Read every exported sheet and cell file and fingerprint their contents.
2. Build one request per leaf region from the full model. The compact layout.json is not used
   because it can omit regions. Unassigned cells, pictures, and shapes get a fallback scope.
3. Supply candidate geometry, merges, styles, comments, nearby candidate boundaries, picture
   anchors/context, shape metadata, and bounded cell evidence. Pictures are not uploaded.
4. Ask the Azure chat deployment for a structured map (one or more leaf regions per scope).
5. Independently check bounds, overlap within each response, header indices, evidence references,
   orientation, source-cell coverage, and picture association references.
6. Save proposals and review findings separately. Never apply them to the extraction or app.

The analyst can confirm or reclassify a region, change its orientation, or split it. Joins across
candidate scopes are reported as unresolved, not automatically applied. This is a deliberate
first-version limit; it does not yet implement a workbook-wide correction/reconciliation loop.

## Install

Run from `JLR-Knowledge-Partner/backend`. The backend requirements already contain all runtime
dependencies. With an existing backend environment, no additional packages are needed.
For an extractor-only office installation, add the Azure dependencies:

```powershell
python -m pip install openpyxl langchain-openai pydantic-settings python-dotenv azure-identity
```

Use `python`, `py`, or your environment's Python executable as appropriate. No `.venv` path is assumed.

## Prepare inputs offline first

```powershell
python -m experiment.excel_analyst "..\test_ex" --out "..\analyst-inputs" --prepare-only
```

This requires no Azure configuration and makes no network calls. It writes the exact per-scope
payloads, prompt, response schema, and a prepared manifest. Inspect the JSON inputs before a live run;
they contain document content, including hidden rows/columns on visible sheets. Hidden sheets are
excluded unless `--include-hidden` is supplied. Existing nonempty output directories are refused.

## Configure Azure

Reuse the application's settings in **backend/.env** or process environment variables. Preserve any
existing settings. The deployment must be an Azure OpenAI chat deployment with tool/function calling.

```dotenv
AZURE_OPENAI_ENDPOINT=https://<resource-name>.openai.azure.com/
AZURE_OPENAI_CHAT_DEPLOYMENT=<deployment-name>
AZURE_OPENAI_API_VERSION=2024-10-21
AZURE_OPENAI_AUTH=key
```

Supply `AZURE_OPENAI_API_KEY` securely on the machine, using the existing backend configuration
mechanism. Do not put keys in source control, output JSON, screenshots, or chat. Alternatively use
`AZURE_OPENAI_AUTH=entra` with the existing DefaultAzureCredential flow and suitable Azure role.
Use the API version supported by your deployment. The analyst reuses the configured timeout,
bounded retries, and reasoning-model settings; embeddings and local search models are not loaded.

## Run the Azure stage

```powershell
python -m experiment.excel_analyst "..\test_ex" --out "..\analyst-results"
```

For one named sheet:

```powershell
python -m experiment.excel_analyst "..\test_ex" --out "..\analyst-radar" --sheet "Radar Sensor"
```

By default, up to 20 scopes/calls are allowed, with 200 sampled cells and 48,000 serialized JSON
characters per request. The character budget is **not a model token guarantee**. Calls are sequential,
with a 6,000-token output budget. Set reasoning-model options appropriately in backend configuration.
If the planned call count exceeds `--max-calls`, the command fails **before** making any calls.
Raise the limit explicitly or select a sheet. SDK retries can produce more HTTP attempts than scopes.

Cells are sampled deterministically, prioritizing candidate headers and including distributed samples.
If a request is too large, the sample shrinks and omissions are counted. Oversized metadata or a scope
where no cell evidence fits causes an explicit preflight error instead of silently dropping the scope.
Use `--max-cells` and `--max-chars` to tune the budgets. **Every sampled scope requires review**;
the analyst has not semantically inspected omitted cells, even if its map geometrically covers them.

## Output and review

`analyst.json` contains source fingerprint, prompt version, deployment metadata (no key), token usage,
skipped sheets, extraction warnings, and each proposed map with deterministic validation results.
`sNN-rNNNN.input.json` contains each model input. `prompt.txt` and `schema.json` record the contract.
The manifest is saved after each scope, preserving successful work when another scope fails.

- `prepared`: inputs only; no LLM calls.
- `running`: the manifest was checkpointed before all scopes completed; an interrupted run is incomplete.
- `proposed`: structured responses produced; inspect `needs_review` and each validation object.
- `partial_failure`: an API/schema error or invalid references occurred; do not apply the results.
- `source_changed`: input files changed during the run; regenerate against a stable extraction.

`valid_references` means structural checks passed; it does **not** establish that the interpretation
is correct. Confidence is self-reported, not calibrated. Picture links remain hypotheses: code checks
IDs, geometry and evidence, not visual meaning. Unlinked pictures, uncertain proposals, uncovered cells,
sampled content, and upstream extraction issues require review. The extractor's known blind spots
(e.g. missing comments or formula caches) cannot be certified away by an LLM reading its output.

Output directories must be separate from the extraction and new or empty. There is no automatic
resume/cache or output overwrite: use a new directory for another run. Provider exceptions are recorded
as categories rather than raw text to avoid leaking document data or credentials. Check configuration
and Azure service diagnostics when a call fails. Exit codes: 0 = command completed (review may still
be needed), 1 = setup/input/preflight error, 2 = partial failure or source change.

## Tests

```powershell
python -m pip install pytest xlsxwriter lxml pillow
python -m pytest experiment/tests -q
```

Analyst tests cover fabricated references, value-rewrite rejection, overlaps, missing coverage,
sampling, zeros/False, hidden sheets, unassigned objects, budgets, partial failures, source preservation,
and an AzureChatOpenAI structured call through a mocked HTTP transport. Mocked Azure success does
not establish live endpoint access or real-workbook layout quality; those require office validation.
