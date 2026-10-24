import numpy as np
import pytest

from stat_agent.agents import KnowledgeAgent
from stat_agent.retrieval import LexicalEncoder, normalize, retrieve
from conftest import make_profile


@pytest.mark.parametrize("vector", [[[0, 0]], [[float('nan'), 1]], [[float('inf'), 1]], [], [1, 2]])
def test_invalid_embeddings(vector):
    with pytest.raises(ValueError):
        normalize(np.array(vector))


def test_cosine_l2_and_large_finite():
    normalized = normalize(np.array([[3, 4], [1e300, 1e300]]))
    np.testing.assert_allclose(np.linalg.norm(normalized, axis=1), 1)
    assert normalized[0, 0] == pytest.approx(.6)


def test_hard_exclusion_unknown_and_explanations(pca_case):
    _, task, profile = pca_case
    knowledge = KnowledgeAgent().run()
    result = retrieve(task, profile, knowledge)
    assert [c.knowledge_id for c in result.ranked] == ["stats::prcomp"]
    assert len(result.excluded) == 4
    assert result.ranked[0].unknowns
    assert result.ranked[0].penalty_total == 0  # unknown assumptions are not penalties
    impossible = retrieve(task, profile, [k for k in knowledge if k.id != "stats::prcomp"])
    assert impossible.status == "no_compatible_method"
    assert impossible.ranked == []
    task.task_type = "unknown"
    assert retrieve(task, profile, knowledge).status == "needs_clarification"


def test_penalty_formula_and_ablations(pca_case):
    frame, _, profile = pca_case
    frame = frame.assign(y=frame.x1 * 2, x2=frame.x1 * 3)
    task, profile = make_profile(frame, profile.source, goal="回归", task_type="regression",
                                 targets=["y"], predictors=["x1", "x2"])
    knowledge = KnowledgeAgent().run()
    a = retrieve(task, profile, knowledge, mode="A")
    b = retrieve(task, profile, knowledge, mode="B")
    c = retrieve(task, profile, knowledge, mode="C", alpha=.8, penalty_lambda=.7)
    assert len(a.ranked) == 5
    assert len(b.ranked) == 1
    lm = c.ranked[0]
    assert lm.penalty_total == .5
    assert lm.score == pytest.approx(.8 * lm.cosine - .7 * lm.penalty_total)
    assert b.ranked[0].score == b.ranked[0].cosine


def test_invalid_dimensions_and_empty_profiles(pca_case):
    class Misaligned:
        name = "invalid"
        def encode_pair(self, query, docs):
            return np.ones((1, 2)), np.ones((len(docs), 3))
    _, task, profile = pca_case
    with pytest.raises(ValueError, match="aligned"):
        retrieve(task, profile, KnowledgeAgent().run(), Misaligned())
    with pytest.raises(ValueError, match="Empty"):
        LexicalEncoder().encode_pair("", ["pca"])


def test_selected_columns_control_constraints(pca_case):
    frame, _, profile = pca_case
    frame["unused"] = np.inf
    task, profile = make_profile(frame, profile.source, predictors=["x1", "x2"])
    assert retrieve(task, profile, KnowledgeAgent().run()).status == "ranked"
