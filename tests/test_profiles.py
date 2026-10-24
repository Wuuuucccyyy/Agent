import numpy as np
import pandas as pd
import pytest

from stat_agent.agents import TaskUnderstandingAgent
from stat_agent.io import read_table
from stat_agent.schemas import DataProfile
from conftest import make_profile


def test_exact_statistics_and_unknown_design(pca_case):
    frame, task, profile = pca_case
    first = profile.variables[0]
    assert first.mean == 4.5
    assert first.variance == 6.0
    assert first.missing_rate == 0
    assert profile.structure.n == 8
    assert profile.relations.centered_rank == 3
    assert profile.design.independence == "unknown"
    assert first.measurement_scale == "unknown"
    assert first.evidence.origin == "computed"
    assert DataProfile.model_validate_json(profile.model_dump_json()) == profile


def test_missing_nonfinite_constant_and_categorical(tmp_path):
    path = tmp_path / "dirty.csv"
    path.write_text("a,b,c,d\n1,7,A,\n2,7,B,\n,7,A,\ninf,7,A,\n", encoding="utf-8")
    frame, source = read_table(path)
    task, profile = make_profile(frame, source, predictors=["a", "b"])
    a = profile.variables[0]
    assert a.missing_count == 1
    assert a.nonfinite_count == 1
    assert a.mean == 1.5
    assert profile.quality.constant_columns == ["b"]
    assert profile.quality.all_missing_columns == ["d"]
    assert profile.relations.complete_rows == 2
    assert profile.relations.singular is True
    assert 'NaN' not in profile.model_dump_json()
    assert 'Infinity' not in profile.model_dump_json()


def test_excel_csv_equivalence(examples, tmp_path):
    frame, csv_source = read_table(examples / "pca.csv")
    excel = tmp_path / "input.xlsx"
    with pd.ExcelWriter(excel) as writer:
        frame.to_excel(writer, sheet_name="测量", index=False)
    copy, excel_source = read_table(excel, "测量")
    np.testing.assert_array_equal(frame.to_numpy(), copy.to_numpy())
    _, profile = make_profile(copy, excel_source)
    assert profile.variables[0].mean == 4.5
    assert excel_source.sheet == "测量"


@pytest.mark.parametrize("content", ["a,a\n1,2\n", "a,\n1,2\n", "a,b\n", "a,b\n1,2,3\n", "a,b\n1\n"])
def test_reject_bad_table(content, tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text(content)
    with pytest.raises(ValueError):
        read_table(path)


def test_ambiguous_request_and_bad_roles(pca_case):
    assert TaskUnderstandingAgent().run("分析一下").task_type == "unknown"
    assert TaskUnderstandingAgent().run("先 PCA 再回归").task_type == "unknown"
    frame, _, profile = pca_case
    with pytest.raises(ValueError, match="Unknown variables"):
        make_profile(frame, profile.source, targets=["not_a_column"])
    with pytest.raises(ValueError, match="non-overlapping"):
        make_profile(frame, profile.source, targets=["x1"], predictors=["x1"])
