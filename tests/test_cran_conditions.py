import copy
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from conftest import make_profile
from stat_agent.io import read_table
from stat_agent.kb_cli import main
from stat_agent.kb_rules import Parameters, Predicate, _and, compare, evaluate_conditions, validate_rule_set
from stat_agent.kb_store import KnowledgeDatabase
from stat_agent.retrieval import LexicalEncoder
from stat_agent.schemas import DataProfile

ROOT = Path(__file__).resolve().parents[1]
RECORDS = {r['metadata']['function_id']: r for r in json.loads((ROOT/'database/cran_profiles.json').read_text(encoding='utf-8'))['profiles']}


def profile(tmp_path, data, **roles):
    path = tmp_path/'input.csv'
    pd.DataFrame(data).to_csv(path, index=False)
    frame, source = read_table(path)
    return make_profile(frame, source, **roles)


def check(name, task, data, **params):
    return evaluate_conditions(RECORDS[name], task=task, profile=data, parameters=params)


def rule(result, name):
    return next(r for r in result['rules'] if r['id'] == name)


def test_audit_preserves_history_and_every_claim():
    assert len(RECORDS) == 8
    assert sum(len(r['semantic']['claims']) for r in RECORDS.values()) == 85
    assert sum(len(r['rules']['rules']) for r in RECORDS.values()) == 66
    for record in RECORDS.values():
        assert record['status'] == 'machine_checked'
        assert record['attempts'][-1]['reviewer'] == 'codex_source_audit'
        assert not record['runtime_verified']
        assert record['semantic_verification'] == 'llm_inference_not_human_verified'
        locations = {d['location'] for d in record['source_audit']['decisions']}
        assert all(f'claims[{i}]' in locations for i in range(len(record['semantic']['claims'])))
        validate_rule_set(record)
    for name in ['cluster::agnes', 'cluster::clara', 'psych::principal']:
        assert RECORDS[name]['attempts'][-2]['review']['accepted'] is False


def test_three_valued_logic_and_no_expression_execution():
    assert _and([True, None]) is None
    assert _and([False, None]) is False
    assert compare(Predicate(fact='param.k', op='gt', value=0), {}) is None
    assert compare(Predicate(fact='param.k', op='eq', value=1), {'param.k': True}) is False
    for value in [dict(fact='__import__("os")', op='eq', value=1),
                  dict(fact='param.k', op='eval', value='x'),
                  dict(fact='param.k', op='gt', value=1, other_fact='data.n')]:
        with pytest.raises(ValidationError):
            Predicate.model_validate(value)
    for value in [True, 2.3, '2']:
        with pytest.raises(ValidationError):
            Parameters(k=value)
    with pytest.raises(ValidationError):
        Parameters(code='print(1)')


def test_rule_source_and_semantic_binding():
    for field, mutation in [('semantic', lambda r: r['semantic']['unknowns'].append('drift')),
                            ('source', lambda r: r['source'].update(rd_sha256='f'*64)),
                            ('quote', lambda r: r['rules']['rules'][0]['evidence'][0].update(quote='fabricated source quotation'))]:
        record = copy.deepcopy(RECORDS['MASS::qda'])
        mutation(record)
        record.pop('revision')
        with pytest.raises(ValueError):
            KnowledgeDatabase.validate_record(record)


def test_unknown_dataset_and_missing_k_are_retained(tmp_path):
    result = evaluate_conditions(RECORDS['cluster::pam'])
    assert result['state'] == 'unknown' and not result['excluded']
    task, data = profile(tmp_path, {'x':[1, 2, 3], 'ignored':[None]*3}, goal='聚类', predictors=['x'])
    result = check('cluster::pam', task, data)
    assert rule(result, 'cluster_count')['state'] == 'unknown'
    assert rule(result, 'pairwise_overlap')['state'] == 'satisfied'
    assert not result['excluded']
    assert check('cluster::pam', task, data, k=2)['state'] == 'satisfied'
    assert check('cluster::pam', task, data, k=2)['facts']['param.sampsize'] is None
    for k in [0, 3, -1]:
        assert check('cluster::pam', task, data, k=k)['excluded']


def test_pairwise_overlap_is_pairwise_not_per_row(tmp_path):
    task, data = profile(tmp_path, {'x':[1, None, 2], 'y':[None, 1, 2]}, goal='聚类', predictors=['x','y'])
    assert data.applicability.pairwise_observed_overlap is False
    assert rule(check('cluster::pam', task, data, k=1), 'pairwise_overlap')['state'] == 'violated'
    task, data = profile(tmp_path, {'x':[1, 2, 3], 'y':[None, 1, 2]}, goal='聚类', predictors=['x','y'])
    result = check('cluster::pam', task, data, k=1)
    assert rule(result, 'pairwise_overlap')['state'] == 'satisfied'
    assert not result['excluded']  # Raw NA is allowed when each pair shares a variable.


def test_qda_sample_bound_and_advisory_rank(tmp_path):
    task, data = profile(tmp_path, {'x':[1,2,3,4], 'y':[1,3,2,4], 'g':['a','a','b','b']},
                         goal='判别分析', predictors=['x','y'], groups=['g'])
    result = check('MASS::qda', task, data)
    assert rule(result, 'group_size_rank_bound')['state'] == 'violated'
    assert result['excluded']
    task, data = profile(tmp_path, {'x':[1,2,3,4,5,6], 'y':[2,4,6,8,10,12], 'g':['a']*3+['b']*3},
                         goal='判别分析', predictors=['x','y'], groups=['g'])
    result = check('MASS::qda', task, data)
    assert rule(result, 'group_size_rank_bound')['state'] == 'satisfied'
    assert rule(result, 'observed_group_rank')['state'] == 'violated'
    assert result['state'] == 'unknown' and not result['excluded']


def test_old_profiles_and_changed_group_roles_cannot_reuse_group_facts(tmp_path):
    task, data = profile(tmp_path, {'x':[1,2,3,4], 'g':['a','a','b','b'], 'h':['a','b','c','d']},
                         goal='判别分析', predictors=['x'], groups=['g'])
    assert rule(check('MASS::qda', task, data), 'group_size_rank_bound')['state'] == 'satisfied'
    changed = task.model_copy(update={'group_variables':['h']})
    assert rule(check('MASS::qda', changed, data), 'group_size_rank_bound')['state'] == 'unknown'
    old = data.model_dump()
    old.pop('applicability')
    assert rule(check('MASS::qda', task, DataProfile.model_validate(old)), 'observed_group_rank')['state'] == 'unknown'


def test_declared_omission_does_not_pretend_rows_were_deleted(tmp_path):
    task, data = profile(tmp_path, {'x':[1,None,3,4], 'g':['a','a','b','b']},
                         goal='判别分析', predictors=['x'], groups=['g'])
    assert check('MASS::qda', task, data)['excluded']
    result = check('MASS::qda', task, data, na_action='omit')
    assert rule(result, 'missing_fail')['applicable'] is False
    assert rule(result, 'group_size_rank_bound')['state'] == 'unknown'
    assert rule(result, 'preprocessing_observed')['state'] == 'unknown'
    assert not result['excluded']
    assert data.structure.n == 4 and data.variables[0].missing_count == 1


def test_distance_forms_and_ignored_metric(tmp_path):
    task, data = profile(tmp_path, {'a':[0,1,2], 'b':[1,0,3], 'c':[2,3,0]}, goal='聚类', predictors=['a','b','c'])
    result = check('cluster::pam', task, data, k=1, input_kind='dissimilarity', metric='ignored')
    assert result['state'] == 'satisfied'
    assert rule(result, 'metric')['applicable'] is False
    task, data = profile(tmp_path, {'distance':[1,2,3]}, goal='聚类', predictors=['distance'])
    result = check('cluster::pam', task, data, k=2, input_kind='dissimilarity_condensed')
    assert result['facts']['data.n'] == 3 and not result['excluded']
    task, data = profile(tmp_path, {'distance':[1,2,3,4]}, goal='聚类', predictors=['distance'])
    assert check('cluster::pam', task, data, k=2, input_kind='dissimilarity_condensed')['excluded']


def test_principal_shape_does_not_infer_input_kind(tmp_path):
    task, data = profile(tmp_path, {'a':[1,2], 'b':[3,4]}, goal='PCA', predictors=['a','b'])
    result = check('psych::principal', task, data)
    assert rule(result, 'pca_matrix')['applicable'] is False
    assert check('psych::principal', task, data, input_kind='correlation')['excluded']
    assert check('psych::principal', task, data, nfactors=3)['excluded']


def test_clara_defaults_and_factor_predictors_for_ridge(tmp_path):
    task, data = profile(tmp_path, {'x':[1,2,3]}, goal='聚类', predictors=['x'])
    result = check('cluster::clara', task, data, k=1)
    assert result['facts']['param.sampsize'] == 3 and not result['excluded']
    assert check('cluster::clara', task, data, k=1, sampsize=1)['excluded']
    task, data = profile(tmp_path, {'x':['a','b','a'], 'y':[1,2,3]}, goal='回归', predictors=['x'], targets=['y'])
    assert not check('MASS::lm.ridge', task, data)['excluded']


def test_hard_filter_precedes_top_k_and_unknowns_survive(tmp_path):
    db = KnowledgeDatabase(tmp_path/'kb.sqlite3')
    db.restore(ROOT/'database/cran_profiles.json')
    task, data = profile(tmp_path, {'x':[1,2,3]}, goal='聚类', predictors=['x'])
    query = RECORDS['cluster::pam']['retrieval_text']
    results = db.search(query, LexicalEncoder(), top_k=1, task=task, profile=data,
                        parameters={'cluster::pam':{'k':100}})
    assert len(results) == 1 and results[0]['function_id'] != 'cluster::pam'
    assert results[0]['execution_authorized'] is False
    all_matches = db.search(query, LexicalEncoder(), 100, task=task, profile=data, include_excluded=True)
    pam = next(r for r in all_matches if r['function_id'] == 'cluster::pam')
    assert pam['conditions']['state'] == 'unknown' and not pam['conditions']['excluded']


def test_cli_emits_exclusions_and_rejects_parameter_typos(tmp_path, capsys):
    path = tmp_path/'kb.sqlite3'
    KnowledgeDatabase(path).restore(ROOT/'database/cran_profiles.json')
    profile(tmp_path, {'x':[1,2,3]}, goal='聚类', predictors=['x'])
    parameters = tmp_path/'parameters.json'
    parameters.write_text(json.dumps({'cluster::pam': {'k':3}}))
    out = tmp_path/'search.json'
    args = ['search','--db',str(path),'--goal','聚类','--task','clustering', '--input',str(tmp_path/'input.csv'),
            '--parameters',str(parameters),'--out',str(out)]
    assert main(args) == 0
    result = json.loads(out.read_text(encoding='utf-8'))
    assert any(r['function_id']=='cluster::pam' for r in result['excluded'])
    assert all(not r['conditions']['excluded'] for r in result['candidates'])
    parameters.write_text('{"typo::pam":{"k":2}}')
    assert main(args) == 1
    assert 'unknown function' in capsys.readouterr().err


def test_audit_script_is_idempotent_and_export_roundtrips(tmp_path):
    spec = importlib.util.spec_from_file_location('audit_cran_profiles', ROOT/'scripts/audit_cran_profiles.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for record in RECORDS.values():
        assert module.audit_record(record) == record
    changed = copy.deepcopy(RECORDS['cluster::pam'])
    changed.pop('revision')
    changed.pop('source_audit')
    changed = KnowledgeDatabase.validate_record(changed)
    with pytest.raises(ValueError, match='new source audit'):
        module.audit_record(changed)
    db = KnowledgeDatabase(tmp_path/'db.sqlite3')
    db.restore(ROOT/'database/cran_profiles.json')
    output = tmp_path/'export.json'
    db.export(output)
    restored = KnowledgeDatabase(tmp_path/'other.sqlite3')
    restored.restore(output)
    assert restored.records() == db.records()
    for record in restored.records():
        assert restored.cached(record['build_fingerprint'])['revision'] == record['revision']


def test_overlap_resource_limit_returns_unknown():
    from stat_agent.applicability_facts import describe_applicability
    from stat_agent.schemas import TaskProfile
    masks = np.array([[(i >> j) & 1 for j in range(10)] for i in range(513)], dtype=bool)
    values = np.where(masks, 1.0, np.nan)
    frame = pd.DataFrame(values, columns=[f'x{i}' for i in range(10)])
    frame['shared'] = 1.0
    task = TaskProfile(research_goal='聚类', task_type='clustering', predictor_variables=list(frame.columns))
    facts = describe_applicability(frame, task, list(frame.columns))
    assert facts.pairwise_observed_overlap is None
    assert any('512' in note for note in facts.notes)


def test_changed_target_role_recomputes_selected_features(tmp_path):
    task, data = profile(tmp_path, {'x':[1,2,3], 'y':[3,4,5]}, goal='PCA')
    changed = task.model_copy(update={'task_type':'regression', 'target_variables':['y']})
    result = check('MASS::lm.ridge', changed, data)
    assert result['facts']['features.count'] == 1
    assert result['facts']['response.numeric'] is True
