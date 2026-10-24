from pathlib import Path

import pytest

from stat_agent.agents import ProfileValidationAgent, RelationsAgent, StructureAgent, TaskUnderstandingAgent
from stat_agent.io import read_table


@pytest.fixture
def examples():
    return Path(__file__).resolve().parents[1] / "examples" / "data"


def make_profile(frame, source, **roles):
    task = TaskUnderstandingAgent().run(roles.pop("goal", "PCA 主成分"), **roles)
    validator = ProfileValidationAgent()
    validator.validate_roles(frame, task)
    variables = StructureAgent().run(frame, source)
    relations = RelationsAgent().run(frame, task)
    return task, validator.run(frame, source, task, variables, relations)


@pytest.fixture
def pca_case(examples):
    frame, source = read_table(examples / "pca.csv")
    task, profile = make_profile(frame, source, task_type="pca", predictors=["x1", "x2", "x3"])
    return frame, task, profile
