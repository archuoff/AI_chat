"""Grounding, boundaries and Azure transport are tested without paid API calls."""
import hashlib
import json

import pytest
from pydantic import ValidationError

from experiment.excel_analyst.__main__ import run
from experiment.excel_analyst.analyst import AzureAnalyst, check_proposal
from experiment.excel_analyst.evidence import load_evidence
from experiment.excel_analyst.schema import LayoutProposal


@pytest.fixture
def exported(tmp_path):
    folder = tmp_path / 'source'
    (folder / 'cells').mkdir(parents=True)
    model = {'file': 'sample.xlsx', 'sheets': [{'name': 'Sheet', 'state': 'visible', 'regions': [
        {'id': 'R1', 'r0': 1, 'c0': 1, 'r1': 3, 'c1': 2, 'kind': 'table', 'header_rows': [1]}]}]}
    (folder / 'model.json').write_text(json.dumps(model))
    cells = [{'r': 1, 'c': 1, 'v': 'Part'}, {'r': 1, 'c': 2, 'v': 'Mass'},
             {'r': 2, 'c': 1, 'v': 'Beam'}, {'r': 2, 'c': 2, 'v': 0},
             {'r': 3, 'c': 1, 'v': 'Bracket'}, {'r': 3, 'c': 2, 'v': False}]
    (folder / 'cells' / '00_Sheet.jsonl').write_text('\n'.join(json.dumps(c) for c in cells))
    return folder


def proposal(**changes):
    reg = {'range': 'A1:B3', 'kind': 'table', 'orientation': 'rows', 'header_rows': [1],
           'header_columns': [], 'title_cell': None, 'evidence_cells': ['A1', 'B1', 'A2'],
           'evidence_pictures': [], 'evidence_shapes': [], 'picture_links': [], 'confidence': 0.9, 'needs_review': False,
           'reason': 'A labelled table with one part per row'}
    reg.update(changes)
    return LayoutProposal.model_validate({'regions': [reg], 'unresolved': []})


def read_model(folder):
    path = folder / 'model.json'
    return json.loads(path.read_text()), path


class FakeProvider:
    metadata = {'provider': 'test-only'}

    def analyse(self, item):
        return proposal(), {'input_tokens': 10, 'output_tokens': 20}


def test_full_evidence_keeps_zero_false_and_validates(exported):
    ex = load_evidence(exported)
    item = ex.items[0]
    shown = {c['ref']: c for c in item.payload['cells']}
    assert shown['B2']['v'] == 0 and shown['B3']['v'] is False
    assert len(shown) == 6 and item.payload['omitted_cells'] == 0
    check = check_proposal(item, proposal())
    assert check['valid_references'] and not check['needs_review']


@pytest.mark.parametrize('changes', [
    {'range': 'A1:C3'}, {'range': 'Sheet!A1:B3'}, {'range': 'A0:B3'},
    {'evidence_cells': ['Z999']}, {'title_cell': 'C1'}, {'header_rows': [99]},
    {'header_columns': [3]}, {'orientation': 'columns'}, {'evidence_cells': []},
    {'evidence_pictures': ['invented']},
    {'evidence_shapes': ['invented']},
    {'picture_links': [{'picture_id': 'invented', 'target_range': 'A2:B2', 'evidence_cells': ['A2'], 'reason': 'guess'}]},
])
def test_hallucinated_or_invalid_references_are_rejected(exported, changes):
    result = check_proposal(load_evidence(exported).items[0], proposal(**changes))
    assert not result['valid_references'] and result['needs_review']


def test_overlap_and_uncovered_content_need_attention(exported):
    item = load_evidence(exported).items[0]
    value = proposal()
    value.regions.append(value.regions[0].model_copy(deep=True))
    assert not check_proposal(item, value)['valid_references']
    smaller = proposal(range='A1:B2')
    check = check_proposal(item, smaller)
    assert check['valid_references'] and check['uncovered_cell_count'] == 2 and check['needs_review']


def test_cannot_rewrite_values_in_response():
    value = proposal().model_dump()
    value['regions'][0]['values'] = {'B2': 1234}
    with pytest.raises(ValidationError):
        LayoutProposal.model_validate(value)


def test_sampling_is_explicit_and_always_requires_review(exported):
    item = load_evidence(exported, max_cells=4).items[0]
    assert item.payload['omitted_cells'] == 2
    assert any(c['ref'] == 'B3' for c in item.payload['cells'])
    check = check_proposal(item, proposal(evidence_cells=['A1']))
    assert check['valid_references'] and check['needs_review']


def test_uses_all_model_regions_even_when_layout_summary_omits_them(exported):
    model, path = read_model(exported)
    model['sheets'][0]['regions'].append({'id': 'R2', 'r0': 5, 'c0': 1, 'r1': 5, 'c1': 2})
    path.write_text(json.dumps(model))
    (exported / 'layout.json').write_text('{"omitted_regions": 99}')
    assert len(load_evidence(exported).items) == 2


def test_unassigned_cells_become_explicit_fallback(exported):
    model, path = read_model(exported)
    model['sheets'][0]['regions'] = []
    path.write_text(json.dumps(model))
    ex = load_evidence(exported)
    assert len(ex.items) == 1 and ex.items[0].payload['candidate']['id'] == 'unassigned'
    assert ex.warnings


def test_unassigned_picture_and_textbox_do_not_disappear(exported):
    model, path = read_model(exported)
    model['sheets'][0]['pictures'] = [{'id': 'p1', 'anchor': {'r0': 9, 'c0': 1, 'r1': 10, 'c1': 2}}]
    model['sheets'][0]['shapes'] = [{'id': 'x1', 'kind': 'textbox', 'text': 'Some engineering note',
                                   'anchor': {'r0': 9, 'c0': 1, 'r1': 10, 'c1': 2}}]
    path.write_text(json.dumps(model))
    ex = load_evidence(exported)
    item = ex.items[-1]
    assert len(ex.items) == 2 and item.payload['pictures'][0]['id'] == 'p1'
    check = check_proposal(item, proposal(range='A9:B10', kind='text', orientation='none', header_rows=[],
                           evidence_cells=[], evidence_pictures=['p1'], evidence_shapes=['x1']))
    assert check['valid_references'] and check['needs_review']  # picture association remains unknown


def test_large_candidate_does_not_dump_every_data_row_index(exported):
    model, path = read_model(exported)
    model['sheets'][0]['regions'][0]['data_rows'] = list(range(2, 20001))
    path.write_text(json.dumps(model))
    item = load_evidence(exported).items[0]
    assert item.payload['candidate']['data_row_count'] == 19999
    assert 'data_rows' not in item.payload['candidate']


def test_hidden_sheets_require_explicit_flag(exported):
    model, path = read_model(exported)
    model['sheets'][0]['state'] = 'hidden'
    path.write_text(json.dumps(model))
    assert not load_evidence(exported).items
    assert load_evidence(exported).skipped_sheets == ['Sheet']
    assert len(load_evidence(exported, include_hidden=True).items) == 1


def test_prepare_and_run_do_not_modify_source(exported, tmp_path):
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in exported.rglob('*') if p.is_file()}
    dry = tmp_path / 'dry'
    assert run(exported, dry, prepare_only=True) == 0
    assert json.loads((dry / 'analyst.json').read_text())['status'] == 'prepared'
    out = tmp_path / 'live'
    assert run(exported, out, provider=FakeProvider()) == 0
    report = json.loads((out / 'analyst.json').read_text())
    assert report['status'] == 'proposed' and report['usage']['successful_calls'] == 1
    assert report['usage']['input_tokens'] == 10
    assert before == {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in before}
    with pytest.raises(ValueError, match='new or empty'):
        run(exported, out, prepare_only=True)
    with pytest.raises(ValueError, match='separate output'):
        run(exported, exported / 'nested', prepare_only=True)


def test_failed_call_preserves_results_and_redacts_exception(exported, tmp_path):
    class FailedProvider:
        def analyse(self, item):
            raise RuntimeError('sensitive-request-body-or-key')
    out = tmp_path / 'failed'
    assert run(exported, out, provider=FailedProvider()) == 2
    text = (out / 'analyst.json').read_text()
    assert 'sensitive-request-body-or-key' not in text
    assert json.loads(text)['status'] == 'partial_failure'


def test_budget_preflight_and_oversize_metadata_fail_before_call(exported, tmp_path):
    with pytest.raises(ValueError, match='max-calls'):
        run(exported, tmp_path / 'out', max_calls=0, provider=FakeProvider())
    with pytest.raises(ValueError, match='Sheet not found'):
        load_evidence(exported, sheet='missing')
    model, path = read_model(exported)
    model['sheets'][0]['regions'][0]['evidence'] = ['x' * 5000]
    path.write_text(json.dumps(model))
    with pytest.raises(ValueError, match='metadata exceeds'):
        load_evidence(exported, max_chars=2000)


def test_changed_source_during_call_is_not_claimed_valid(exported, tmp_path):
    class ChangesSource(FakeProvider):
        def analyse(self, item):
            model, path = read_model(exported)
            model['warnings'] = ['source changed']
            path.write_text(json.dumps(model))
            return super().analyse(item)
    out = tmp_path / 'out'
    assert run(exported, out, provider=ChangesSource()) == 2
    assert json.loads((out / 'analyst.json').read_text())['status'] == 'source_changed'


def test_picture_association_checks_target_and_evidence(exported):
    model, path = read_model(exported)
    model['sheets'][0]['pictures'] = [{'id': 'p1', 'anchor': {'r0': 2, 'c0': 2, 'r1': 2, 'c1': 2}}]
    path.write_text(json.dumps(model))
    item = load_evidence(exported).items[0]
    link = {'picture_id': 'p1', 'target_range': 'A2:B2', 'evidence_cells': ['A2'], 'reason': 'Same record row'}
    assert check_proposal(item, proposal(picture_links=[link]))['valid_references']
    link['target_range'] = 'A3:B3'
    assert not check_proposal(item, proposal(picture_links=[link]))['valid_references']


def test_azure_structured_call_with_mock_http_transport(exported, monkeypatch):
    import httpx
    from langchain_openai import AzureChatOpenAI
    import app.llm
    requests = []

    def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        return httpx.Response(200, json={'id': 'test-response', 'object': 'chat.completion', 'created': 0,
            'model': 'test-model', 'choices': [{'index': 0, 'finish_reason': 'tool_calls', 'message': {
                'role': 'assistant', 'content': None, 'tool_calls': [{'id': 'call_test', 'type': 'function',
                'function': {'name': 'LayoutProposal', 'arguments': proposal().model_dump_json()}}]}}],
            'usage': {'prompt_tokens': 12, 'completion_tokens': 34, 'total_tokens': 46}})

    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        client = AzureChatOpenAI(azure_endpoint='https://example.test/', azure_deployment='test',
                                api_version='2024-10-21', api_key='test-only', http_client=http)
        monkeypatch.setattr(app.llm, 'get_chat_model', lambda: client)
        value, usage = AzureAnalyst().analyse(load_evidence(exported).items[0])
    assert value.regions[0].range == 'A1:B3'
    assert usage == {'input_tokens': 12, 'output_tokens': 34}
    assert requests[0].get('max_tokens', requests[0].get('max_completion_tokens')) == 6000
    assert requests[0]['messages'][0]['role'] == 'system'
    assert requests[0]['tools'][0]['function']['name'] == 'LayoutProposal'


def test_picture_must_sit_inside_its_claimed_target(exported):
    model, path = read_model(exported)
    model['sheets'][0]['pictures'] = [{'id': 'p1', 'anchor': {'r0': 3, 'c0': 2, 'r1': 3, 'c1': 2}}]
    path.write_text(json.dumps(model))
    item = load_evidence(exported).items[0]
    # evidence cells are inside the claimed row, but the picture is anchored in row 3, not row 2
    link = {'picture_id': 'p1', 'target_range': 'A2:B2', 'evidence_cells': ['A2'], 'reason': 'Same row'}
    result = check_proposal(item, proposal(picture_links=[link]))
    assert not result['valid_references'] and any('not located in its claimed target' in e for e in result['errors'])
