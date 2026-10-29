import pytest
from pathlib import Path

from stat_agent.kb_review import json_text, read_json
from stat_agent.llm import LLMError
from stat_agent.profile_experiment import (case_path, load_experiment, review_material,
    run_experiment, summarize)
from test_knowledge_database import Client, document


class ExperimentClient(Client):
    max_output_tokens = 4000
    max_retries = 1
    timeout = 60


def test_shared_initial_draft_and_actual_cost_not_double_counted(tmp_path):
    client = ExperimentClient()
    report = run_experiment([document()], client, tmp_path)
    plan, _, cases = load_experiment(tmp_path)
    assert report['arms']['single']['accounted_usage']['api_calls'] == 1
    assert report['arms']['cooperative']['accounted_usage']['api_calls'] == 2
    assert report['realized_usage']['api_calls'] == 2  # Not 1+2.
    assert cases[0]['single']['semantic'] == cases[0]['cooperative']['semantic']
    assert cases[0]['phases'][0]['output'] == cases[0]['single']['semantic']
    assert report['arms']['single']['field_accuracy'] is None
    assert report['api_cost_usd'] is None
    assert summarize(plan, cases) == report


def test_correction_is_bounded_and_initial_output_preserved(tmp_path):
    client = ExperimentClient(always_reject=True)
    report = run_experiment([document()], client, tmp_path)
    _, _, cases = load_experiment(tmp_path)
    assert report['realized_usage']['api_calls'] == 4
    assert len(cases[0]['phases']) == 4
    assert cases[0]['cooperative']['status'] == 'needs_review'
    assert cases[0]['single']['semantic'] == cases[0]['phases'][0]['output']


def test_schema_failure_stays_in_both_denominators_and_resume_never_retries(tmp_path):
    class Broken(ExperimentClient):
        def structured(self, *args, **kwargs):
            self.usage['api_calls'] += 1
            raise LLMError('Synthetic schema failure; no provider details.')
    client = Broken()
    report = run_experiment([document()], client, tmp_path)
    assert report['arms']['single']['planned_functions'] == 1
    assert report['arms']['single']['candidates_available'] == 0
    assert report['arms']['cooperative']['completed_functions'] == 1
    again = Broken()
    assert run_experiment([document()], again, tmp_path) == report
    assert again.usage['api_calls'] == 0
    with pytest.raises(ValueError, match='denominator'):
        review_material(tmp_path, 'single')


def test_success_resume_is_zero_call_and_setting_changes_rejected(tmp_path):
    run_experiment([document()], ExperimentClient(), tmp_path)
    cached = ExperimentClient()
    run_experiment([document()], cached, tmp_path)
    assert cached.usage['api_calls'] == 0
    changed = ExperimentClient()
    changed.max_output_tokens = 3999
    with pytest.raises(ValueError, match='configuration changed'):
        run_experiment([document()], changed, tmp_path)
    assert changed.usage['api_calls'] == 0


def test_interruption_is_not_silently_replayed(tmp_path):
    class Interrupted(ExperimentClient):
        def structured(self, *args, **kwargs):
            raise KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        run_experiment([document()], Interrupted(), tmp_path)
    client = ExperimentClient()
    with pytest.raises(ValueError, match='uncertain call completion'):
        run_experiment([document()], client, tmp_path)
    assert client.usage['api_calls'] == 0
    assert load_experiment(tmp_path)[2][0]['pending_phase'] == 'initial_extraction'


def test_tampered_plan_sources_cases_and_prompts_fail(tmp_path):
    run_experiment([document()], ExperimentClient(), tmp_path)
    for path in [tmp_path/'plan.json', tmp_path/'sources.json', tmp_path/'prompts.json', case_path(tmp_path,'Example::demo')]:
        original = path.read_text(encoding='utf-8')
        changed = read_json(path)
        changed['tampered'] = True
        path.write_text(json_text(changed), encoding='utf-8')
        with pytest.raises(ValueError):
            load_experiment(tmp_path)
        path.write_text(original, encoding='utf-8')


def test_review_error_keeps_initial_candidate_and_usage(tmp_path):
    class FailedReview(ExperimentClient):
        def structured(self, *args, **kwargs):
            if kwargs['tool_name'] == 'emit_review':
                self.usage['api_calls'] += 1
                raise LLMError('Synthetic review failure.')
            return super().structured(*args, **kwargs)
    report = run_experiment([document()], FailedReview(), tmp_path)
    assert report['arms']['single']['candidates_available'] == 1
    assert report['arms']['cooperative']['status_counts'] == {'review_error':1}
    assert report['realized_usage']['api_calls'] == 2
    assert load_experiment(tmp_path)[2][0]['phases'][-1]['error'] == 'Synthetic review failure.'


def test_review_material_has_no_production_rules_or_model_review_feedback(tmp_path):
    run_experiment([document()], ExperimentClient(), tmp_path)
    manifest, sources, items = review_material(tmp_path, 'single')
    assert manifest['arm'] == 'single'
    assert all(i['category'] not in {'rule', 'rule_configuration'} for i in items)
    assert all('review' not in i['payload'] for i in items if isinstance(i['payload'], dict))
    assert sources == {'Example::demo':document()}
    assert {i['category'] for i in items} == {'task','summary','claim','unknowns'}


def test_same_frozen_reference_can_score_both_arms_but_annotations_cannot_cross(tmp_path):
    from stat_agent.kb_review import (ReferenceDraft, FunctionReference, freeze_reference,
                                     comparison_form, score_review)
    from test_kb_review import synthetic_reference
    run_experiment([document()], ExperimentClient(), tmp_path)
    single, sources, items = review_material(tmp_path, 'single')
    draft = ReferenceDraft(source_set_id=single['source_set_id'], functions=[
        FunctionReference(function_id='Example::demo', source_rd_sha256='b'*64)]).model_dump()
    frozen = freeze_reference(synthetic_reference(single, sources, draft), single, sources)
    _, annotations = comparison_form(frozen, single, sources, items)
    assert score_review(frozen, annotations, single, sources, items)['metrics'] is None
    cooperative, _, cooperative_items = review_material(tmp_path, 'cooperative')
    comparison_form(frozen, cooperative, sources, cooperative_items)
    with pytest.raises(ValueError, match='different packet'):
        score_review(frozen, annotations, cooperative, sources, cooperative_items)


def test_recorded_live_experiment_is_complete_and_recomputes_offline():
    folder = Path(__file__).resolve().parents[1]/'evaluation/experiments/cran-paired-2026-10-28'
    plan, sources, cases = load_experiment(folder)
    assert len(sources) == len(cases) == 8
    report = summarize(plan, cases)
    assert report == read_json(folder/'summary.json')
    assert report['execution_status'] == 'completed'
    assert report['arms']['single']['field_accuracy'] is None
    for arm in ['single','cooperative']:
        manifest, _, items = review_material(folder, arm)
        assert manifest['source_set_id'] == plan['source_set_id']
        assert len({i['function_id'] for i in items}) == 8
