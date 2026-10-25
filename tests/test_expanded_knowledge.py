import numpy as np
import pandas as pd

from conftest import make_profile
from stat_agent.agents import KnowledgeAgent
from stat_agent.retrieval import retrieve


def test_library_is_opt_in_and_has_same_task_alternatives():
    assert len(KnowledgeAgent().run()) == 5
    expanded = KnowledgeAgent().run('expanded')
    assert len(expanded) == 9
    assert sum('pca' in p.task_types for p in expanded) == 2
    assert sum('regression' in p.task_types for p in expanded) == 2


def test_wide_pca_excludes_covariance_interface(pca_case):
    _, _, original = pca_case
    frame = pd.DataFrame(np.random.default_rng(7).normal(size=(4, 8)))
    frame.columns = [f'x{i}' for i in range(8)]
    task, profile = make_profile(frame, original.source, task_type='pca')
    ranking = retrieve(task, profile, KnowledgeAgent().run('expanded'))
    assert [c.knowledge_id for c in ranking.ranked] == ['stats::prcomp']
    assert any(c.knowledge_id == 'stats::princomp' and c.hard_failures for c in ranking.excluded)


def test_explicit_method_is_not_replaced(pca_case):
    _, task, profile = pca_case
    task.requested_method = 'stats::princomp'
    result = retrieve(task, profile, KnowledgeAgent().run('expanded'))
    assert [c.knowledge_id for c in result.ranked] == ['stats::princomp']


def test_small_groups_exclude_qda(pca_case):
    _, _, original = pca_case
    frame = pd.DataFrame(np.random.default_rng(10).normal(size=(12, 7)), columns=[f'x{i}' for i in range(7)])
    frame['group'] = ['a'] * 6 + ['b'] * 6
    task, profile = make_profile(frame, original.source, task_type='discriminant', groups=['group'])
    result = retrieve(task, profile, KnowledgeAgent().run('expanded'))
    assert any(c.knowledge_id == 'MASS::qda' and c.hard_failures for c in result.excluded)


def test_user_constraints_block_template(pca_case):
    from stat_agent.execution import execute
    frame, task, profile = pca_case
    task.constraints = ['Do not scale the variables']
    assert execute(frame, task, retrieve(task, profile, KnowledgeAgent().run())).status == 'blocked'
