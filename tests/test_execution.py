import numpy as np
import pytest
from sklearn.decomposition import PCA

from stat_agent.agents import KnowledgeAgent
from stat_agent.execution import execute
from stat_agent.io import read_table
from stat_agent.retrieval import retrieve
from conftest import make_profile


def test_pca_matches_independent_library(pca_case):
    frame, task, profile = pca_case
    result = execute(frame, task, retrieve(task, profile, KnowledgeAgent().run()))
    x = frame.to_numpy(dtype=float)
    reference = PCA(svd_solver="full").fit((x - x.mean(axis=0)) / x.std(axis=0, ddof=1))
    np.testing.assert_allclose(result.metrics["explained_variance"], reference.explained_variance_, rtol=1e-10)
    assert result.validation_passed


def test_ols_known_coefficients(examples):
    frame, source = read_table(examples / "regression.csv")
    task, profile = make_profile(frame, source, goal="回归", task_type="regression", targets=["y"], predictors=["x1", "x2"])
    result = execute(frame, task, retrieve(task, profile, KnowledgeAgent().run()))
    assert result.metrics["intercept"] == pytest.approx(2)
    assert result.metrics["coefficients"] == pytest.approx({"x1": 3, "x2": -1})
    assert result.metrics["r_squared"] == pytest.approx(1)
    assert result.validation_passed


@pytest.mark.parametrize("mutation", ["missing", "constant", "infinite"])
def test_pca_blocks_unapproved_preprocessing(pca_case, mutation):
    frame, task, profile = pca_case
    frame = frame.astype(float)
    if mutation == "constant":
        frame["x1"] = 1.
    else:
        frame.loc[0, "x1"] = np.nan if mutation == "missing" else np.inf
    task, profile = make_profile(frame, profile.source, task_type="pca", predictors=["x1", "x2"])
    result = execute(frame, task, retrieve(task, profile, KnowledgeAgent().run()))
    assert result.status == "blocked"
    assert not result.validation_passed


def test_singular_ols_and_missing_target_blocked(pca_case):
    frame, _, profile = pca_case
    frame = frame.assign(y=frame.x1 * 2, x2=frame.x1 * 3)
    for targets in [["y"], []]:
        task, data = make_profile(frame, profile.source, goal="回归", task_type="regression", targets=targets, predictors=["x1", "x2"])
        result = execute(frame, task, retrieve(task, data, KnowledgeAgent().run()))
        assert result.status == "blocked"
