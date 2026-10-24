import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("evaluation_run", Path(__file__).resolve().parents[1] / "evaluation/run.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_metrics_with_known_rank_positions():
    result = module.metrics(["wrong", "right", "other"], ["right"], 3)
    assert result["recall_at_k"] == 1
    assert result["mrr"] == .5
    assert result["ndcg_at_k"] == pytest.approx(1 / __import__('math').log2(3))
    assert result["top1_correct"] is False
    assert module.metrics([], [], 3)["top1_correct"] is True
