import sys
from types import SimpleNamespace

import numpy as np

from stat_agent.retrieval import SentenceEncoder


def test_shared_model_adapter_contract(monkeypatch):
    calls = []

    class Model:
        def __init__(self, name, **kwargs):
            calls.append(("init", name, kwargs))

        def encode_query(self, texts, **kwargs):
            calls.append(("query", texts))
            return np.array([[1., 0.]])

        def encode_document(self, texts, **kwargs):
            calls.append(("documents", texts))
            return np.array([[0., 1.] for _ in texts])

    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=Model))
    encoder = SentenceEncoder("test-model", "fixed-revision")
    query, docs = encoder.encode_pair("task", ["method 1", "method 2"])
    assert query.shape == (1, 2)
    assert docs.shape == (2, 2)
    assert calls[0][2] == {"revision": "fixed-revision", "trust_remote_code": False}
    assert [c[0] for c in calls] == ["init", "query", "documents"]
    docs[0, 0] = 99  # A consumer cannot corrupt the internal cached corpus.
    _, cached = encoder.encode_pair("another task", ["method 1", "method 2"])
    assert cached[0, 0] == 0
    assert [c[0] for c in calls].count("documents") == 1
    encoder.encode_pair("another task", ["method 2", "method 1"])
    assert [c[0] for c in calls].count("documents") == 2
