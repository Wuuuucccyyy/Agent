"""Regression cases found during the second baseline review."""
import hashlib
import json

import numpy as np
import pandas as pd
import pytest

from conftest import make_profile
from stat_agent.agents import KnowledgeAgent
from stat_agent.agents import TaskUnderstandingAgent
from stat_agent.execution import execute
from stat_agent.io import read_table
from stat_agent.retrieval import LexicalEncoder, query_text, retrieve


def test_intercept_named_predictor_does_not_overwrite_fitted_intercept(pca_case):
    frame, _, original = pca_case
    frame = pd.DataFrame({'intercept': np.arange(8.), 'y': 2 + 3 * np.arange(8.)})
    task, profile = make_profile(frame, original.source, task_type='regression',
                                 predictors=['intercept'], targets=['y'])
    result = execute(frame, task, retrieve(task, profile, KnowledgeAgent().run()))
    assert result.metrics['intercept'] == pytest.approx(2)
    assert result.metrics['coefficients'] == pytest.approx({'intercept': 3})


def test_missing_patterns_cannot_collide_with_column_names(pca_case):
    _, _, original = pca_case
    frame = pd.DataFrame({'a|b': [np.nan, 1., 2., 3.], 'a': [1., np.nan, 2., 3.],
                          'b': [1., np.nan, 2., 3.], '<complete>': [1., 2., np.nan, 3.]})
    _, profile = make_profile(frame, original.source)
    patterns = {tuple(json.loads(k)): v for k, v in profile.quality.missing_patterns.items()}
    assert patterns == {('a|b',): 1, ('a', 'b'): 1, ('<complete>',): 1, (): 1}


def test_unused_columns_do_not_change_query_or_ranking(pca_case):
    frame, task, profile = pca_case
    expanded = frame.assign(unused=np.nan)
    task2, profile2 = make_profile(expanded, profile.source, task_type='pca', predictors=task.predictor_variables)
    # Identical semantic goal and roles; only the unused dataset column differs.
    task2.research_goal = task.research_goal
    assert query_text(task, profile) == query_text(task2, profile2)
    a = retrieve(task, profile, KnowledgeAgent().run())
    b = retrieve(task2, profile2, KnowledgeAgent().run())
    assert a == b


def test_regression_penalty_uses_joint_complete_rows(pca_case):
    frame, _, original = pca_case
    frame = frame.assign(y=[1., 2., np.nan, np.nan, np.nan, np.nan, np.nan, np.nan])
    task, profile = make_profile(frame, original.source, task_type='regression', predictors=['x1', 'x2'], targets=['y'])
    assert profile.relations.complete_rows == 8
    assert profile.relations.analysis_complete_rows == 2
    result = retrieve(task, profile, KnowledgeAgent().run())
    assert 'residual_df' in [p.name for p in result.ranked[0].penalties]


def test_ingestion_hash_matches_parsed_snapshot_even_if_path_changes(tmp_path, monkeypatch):
    path = tmp_path / 'changing.csv'
    original = b'x\n1\n2\n'
    path.write_bytes(original)
    reader = pd.read_csv

    def mutate_after_read(*args, **kwargs):
        result = reader(*args, **kwargs)
        path.write_bytes(b'x\n100\n200\n')
        return result

    monkeypatch.setattr(pd, 'read_csv', mutate_after_read)
    frame, source = read_table(path)
    assert frame.x.tolist() == [1, 2]
    assert source.sha256 == hashlib.sha256(original).hexdigest()


def test_lexical_documents_are_reused_and_invalidated(monkeypatch):
    import stat_agent.retrieval as module
    real = module.TfidfVectorizer.fit_transform
    fitted = []

    def counted(self, docs, *args, **kwargs):
        fitted.append(tuple(docs))
        return real(self, docs, *args, **kwargs)

    monkeypatch.setattr(module.TfidfVectorizer, 'fit_transform', counted)
    encoder = LexicalEncoder()
    docs = ['PCA principal components', 'linear regression']
    query1, matrix1 = encoder.encode_pair('PCA', docs)
    _, matrix2 = encoder.encode_pair('regression', docs)
    assert len(fitted) == 1
    np.testing.assert_array_equal(matrix1, matrix2)
    encoder.encode_pair('PCA', docs[::-1])
    assert len(fitted) == 2


def test_svd_is_not_repeated_to_compute_rank(pca_case, monkeypatch):
    from stat_agent.profiling import describe_relations
    frame, task, _ = pca_case
    real = np.linalg.svd
    calls = []

    def counted(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(np.linalg, 'svd', counted)
    def no_second_decomposition(*args, **kwargs):
        raise AssertionError('Do not run matrix_rank after already computing singular values')
    monkeypatch.setattr(np.linalg, 'matrix_rank', no_second_decomposition)
    result = describe_relations(frame, task)
    assert result.centered_rank == 3
    assert len(calls) == 1


@pytest.mark.parametrize('shape', [(20, 4), (4, 20), (8, 1)])
def test_reused_svd_rank_matches_numpy(shape):
    from stat_agent.profiling import rank_from_singular_values
    x = np.random.default_rng(42).normal(size=shape)
    if shape[1] > 1:
        x[:, -1] = x[:, 0]
    x -= x.mean(axis=0)
    assert rank_from_singular_values(np.linalg.svd(x, compute_uv=False), x.shape) == np.linalg.matrix_rank(x)


def test_missing_patterns_match_independent_row_counts():
    from collections import Counter
    from stat_agent.profiling import missing_pattern_counts
    rng = np.random.default_rng(42)
    masks = pd.DataFrame(rng.random((1000, 13)) < .15, columns=[f'c{i}' for i in range(13)])
    expected = Counter(tuple(masks.columns[row]) for row in masks.to_numpy())
    actual = {tuple(json.loads(k)): v for k, v in missing_pattern_counts(masks).items()}
    assert actual == expected


def test_report_preview_preserves_full_metrics():
    from stat_agent.pipeline import report_preview
    metrics = {'scores': [[float(i)] for i in range(1000)]}
    preview = report_preview(metrics)
    assert preview['scores']['total_items'] == 1000
    assert len(preview['scores']['preview']) == 10
    assert len(metrics['scores']) == 1000
    assert len(json.dumps(preview)) < 1000


@pytest.mark.parametrize('goal', ['logistic regression', '逻辑回归', '岭回归', 'Poisson regression',
                                  '不标准化主成分分析', '组间比较', '降维', 'upcase'])
def test_unsupported_or_underspecified_requests_are_not_silently_substituted(goal):
    assert TaskUnderstandingAgent().run(goal).task_type == 'unknown'


def test_explicit_category_does_not_override_specific_unsupported_method(examples, tmp_path):
    from stat_agent.pipeline import run_pipeline
    folder = run_pipeline(examples / 'regression.csv', 'logistic regression', tmp_path,
                          task_type='regression', targets=['y'], predictors=['x1', 'x2'])
    payload = json.loads((folder / 'run.json').read_text(encoding='utf-8'))
    assert payload['status'] == 'blocked'
    assert payload['retrieval']['status'] == 'needs_clarification'
    assert payload['execution']['metrics'] == {}
    assert payload['events'][-1]['outcome'] == 'blocked'


def test_unscaled_ols_is_supported():
    assert TaskUnderstandingAgent().run('不标准化线性回归').task_type == 'regression'
