"""Run from backend: python -m experiment.excel_analyst EXTRACTION --out OUTPUT."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .analyst import PROMPT_VERSION, SYSTEM_PROMPT, AzureAnalyst, check_proposal
from .evidence import encoded, load_evidence
from .schema import LayoutProposal


def describe_error(exc: Exception) -> str:
    """Say why a call failed without echoing request or response content (it may hold document text)."""
    parts = [type(exc).__name__]
    errors = getattr(exc, 'errors', None)
    if callable(errors):  # pydantic ValidationError: field path + kind only, never the offending value
        try:
            parts.append('; '.join(f"{'.'.join(str(x) for x in e['loc'])}: {e['type']}" for e in errors()[:8]))
        except Exception:
            pass
    for attr in ('status_code', 'code'):
        value = getattr(exc, attr, None)
        if isinstance(value, (int, str)) and len(str(value)) <= 60:
            parts.append(f'{attr}={value}')
    if type(exc) is ValueError:  # raised by our own code with fixed messages (truncated / refusal / schema)
        parts.append(str(exc)[:200])
    return ' | '.join(p for p in parts if p)


def run(source: Path, out: Path, *, prepare_only: bool = False, sheet: str | None = None,
        max_calls: int = 20, max_cells: int = 200, max_chars: int = 48000,
        include_hidden: bool = False, provider=None) -> int:
    source, out = source.resolve(), out.resolve()
    if out == source or out in source.parents or source in out.parents:
        raise ValueError('Use a separate output folder outside the extraction folder')
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise ValueError('Output folder must be new or empty; existing results will not be overwritten')
    evidence = load_evidence(source, sheet=sheet, max_cells=max_cells, max_chars=max_chars, include_hidden=include_hidden)
    if len(evidence.items) > max_calls:
        raise ValueError(f'{len(evidence.items)} scopes need calls, above --max-calls {max_calls}; choose --sheet or explicitly raise the limit')
    if not evidence.items:
        raise ValueError('No analysable content in the selected sheets')
    if not prepare_only and provider is None:
        provider = AzureAnalyst()
    out.mkdir(parents=True, exist_ok=True)
    report = {'prompt_version': PROMPT_VERSION, 'source_sha256': evidence.digest,
              'status': 'prepared' if prepare_only else 'running', 'model': getattr(provider, 'metadata', None),
              'warnings': evidence.warnings, 'skipped_sheets': evidence.skipped_sheets,
              'limitations': ['Text and layout metadata only; image pixels are not sent.',
                              'Proposals only: no source mutation, extraction certification, second LLM validator, chunking or indexing.',
                              'Scopes cannot be joined automatically; proposed joins require review.'],
              'usage': {'input_tokens': 0, 'output_tokens': 0, 'successful_calls': 0, 'failed_calls': 0}, 'items': []}
    (out / 'prompt.txt').write_text(SYSTEM_PROMPT, encoding='utf-8')
    (out / 'schema.json').write_text(encoded(LayoutProposal.model_json_schema()), encoding='utf-8')

    def save():
        temp = out / 'analyst.json.tmp'
        temp.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')
        temp.replace(out / 'analyst.json')

    save()
    failed = False
    for item in evidence.items:
        (out / f'{item.id}.input.json').write_text(json.dumps(item.payload, indent=2, ensure_ascii=False), encoding='utf-8')
        entry = {'id': item.id, 'sheet': item.sheet, 'scope': item.scope,
                 'source_cell_count': len(item.cells), 'supplied_cells': len(item.payload['cells']),
                 'omitted_cells': item.payload['omitted_cells']}
        if not prepare_only:
            try:
                try:
                    proposal, usage = provider.analyse(item)
                except Exception as first:  # one retry: structured output or a rate limit often passes the second time
                    entry['first_attempt_error'] = describe_error(first)
                    proposal, usage = provider.analyse(item)
                proposal = LayoutProposal.model_validate(proposal)
                report['usage']['successful_calls'] += 1
                for key in ('input_tokens', 'output_tokens'):
                    report['usage'][key] += usage.get(key, 0)
                entry['proposal'] = proposal.model_dump()
                entry['validation'] = check_proposal(item, proposal)
                if not entry['validation']['valid_references']:
                    failed = True
            except Exception as exc:
                # Provider exceptions can embed request data; persist type, status and schema paths only.
                entry['error'] = f'analysis failed after 2 attempts: {describe_error(exc)}'
                report['usage']['failed_calls'] += 1
                failed = True
        report['items'].append(entry)
        save()
    report['status'] = 'prepared' if prepare_only else ('partial_failure' if failed else 'proposed')
    report['needs_review'] = not prepare_only and (bool(evidence.warnings or evidence.skipped_sheets) or failed or
                                                   any(e.get('validation', {}).get('needs_review') for e in report['items']))
    # Detect edits to source evidence during an API call; never attribute results to a changed input.
    if load_evidence(source, sheet=sheet, max_cells=max_cells, max_chars=max_chars, include_hidden=include_hidden).digest != evidence.digest:
        report['status'], report['needs_review'], failed = 'source_changed', True, True
    save()
    print(f"{report['status']}: {len(report['items'])} scope(s); results: {out / 'analyst.json'}")
    return 2 if failed else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Propose Excel layout using the configured Azure OpenAI chat deployment')
    parser.add_argument('extraction', type=Path, help='Folder containing model.json and cells/*.jsonl')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--prepare-only', action='store_true', help='Write model inputs without credentials or API calls')
    parser.add_argument('--sheet')
    parser.add_argument('--max-calls', type=int, default=20)
    parser.add_argument('--max-cells', type=int, default=200)
    parser.add_argument('--max-chars', type=int, default=48000, help='Serialized JSON character budget per call; not a token count')
    parser.add_argument('--include-hidden', action='store_true', help='Include hidden sheets; hidden rows/columns on visible sheets are retained')
    args = parser.parse_args(argv)
    try:
        return run(args.extraction, args.out, prepare_only=args.prepare_only, sheet=args.sheet,
                   max_calls=args.max_calls, max_cells=args.max_cells, max_chars=args.max_chars, include_hidden=args.include_hidden)
    except Exception as exc:
        # Configuration errors raised here contain names/paths, not secret values.
        if isinstance(exc, (ValueError, FileNotFoundError)):
            print(f'error: {exc}', file=sys.stderr)
        else:
            print(f'error: {type(exc).__name__}; verify extraction files and Azure setup', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
