import copy
import importlib.util
import json
from pathlib import Path

import pytest

from stat_agent.knowledge_drafts import extract_draft
from stat_agent.retrieval import LexicalEncoder
from stat_agent.agents import KnowledgeAgent

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT/f'evaluation/{name}.py')
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_test_labels_cannot_change_selected_lambda():
    evaluator = module('expanded')
    cases = json.loads((ROOT/'evaluation/expanded_cases.json').read_text(encoding='utf-8'))
    original = evaluator.evaluate(LexicalEncoder(), cases)
    changed = copy.deepcopy(cases)
    for case in changed:
        if case['split'] == 'test':
            case['relevance'] = {'stats::kmeans': 2, 'MASS::qda': 1}
    altered = evaluator.evaluate(LexicalEncoder(), changed)
    assert original['validation_grid'] == altered['validation_grid']
    assert original['selected_penalty_lambda'] == altered['selected_penalty_lambda']
    assert original['reports']['test'] != altered['reports']['test']
    assert original['cases_sha256'] != altered['cases_sha256']


def test_duplicate_data_across_splits_rejected():
    evaluator = module('expanded')
    case = json.loads((ROOT/'evaluation/expanded_cases.json').read_text(encoding='utf-8'))[0]
    duplicate = dict(case, id='different-name', split='test')
    with pytest.raises(ValueError, match='leaked'):
        evaluator.evaluate(LexicalEncoder(), [case, duplicate])


def test_profile_audit_detects_wrong_numbers_and_invented_design(pca_case):
    evaluator = module('profile_quality')
    _, _, profile = pca_case
    reference = json.loads((ROOT/'evaluation/profile_reference.json').read_text(encoding='utf-8'))
    assert evaluator.assess(profile, reference)['field_accuracy'] == 1
    profile.variables[0].mean = 999
    # model_copy allows injecting an intentionally invalid assertion into the audit.
    profile.design = profile.design.model_copy(update={'independence': 'independent'})
    result = evaluator.assess(profile, reference)
    assert result['field_accuracy'] == pytest.approx(23/25)
    assert result['unsupported_assertion_count'] == 1


def test_knowledge_draft_stays_unverified_and_outside_library():
    class Client:
        class config:
            request_model = 'mock-model'
        def structured(self, system, payload, schema, **kwargs):
            assert kwargs['tool_name'] == 'emit_knowledge'
            return dict(task_types=['pca'], summary='PCA', input_types=['numeric matrix'],
                        input_constraints=[], output_types=['scores'], assumptions=['unknown'],
                        missing_data_handling='unknown', failure_conditions=[], alternatives=[])
    before = [k.model_dump() for k in KnowledgeAgent().run('expanded')]
    draft = extract_draft(Client(), 'Official source excerpt', package='stats', function_name='prcomp',
                          source_url='https://example.invalid/reference', package_version='test', retrieved_on='2026-10-24')
    assert draft.verification_status == 'unverified'
    assert all(e.origin == 'llm_inference' and e.status == 'unverified' for e in draft.evidence.values())
    assert [k.model_dump() for k in KnowledgeAgent().run('expanded')] == before
