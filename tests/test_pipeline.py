import json

import pytest

from stat_agent.cli import main
from stat_agent.pipeline import run_pipeline
from stat_agent.storage import read_run


def test_end_to_end_and_sqlite(examples, tmp_path):
    folder = run_pipeline(examples / "pca.csv", "主成分分析", tmp_path, predictors=["x1", "x2", "x3"])
    payload = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    assert payload["status"] == "success"
    assert len(payload["events"]) == 8
    assert all(e["status"] == "success" for e in payload["events"])
    assert payload["usage"]["api_calls"] == 0
    assert read_run(tmp_path / "profiles.sqlite3", folder.name) == payload
    assert (folder / "report.md").exists()


def test_failed_runs_are_logged(examples, tmp_path):
    with pytest.raises(ValueError):
        run_pipeline(examples / "pca.csv", "回归", tmp_path, targets=["absent"])
    run = next(tmp_path.glob("*/run.json"))
    payload = json.loads(run.read_text(encoding="utf-8"))
    assert payload["status"] == "error"
    assert payload["events"][-1]["status"] == "error"


def test_unknown_goal_cli_returns_nonzero(examples, tmp_path):
    assert main(["analyze", str(examples / "pca.csv"), "--goal", "请分析", "--out", str(tmp_path)]) == 2
