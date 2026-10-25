"""Reproducible microbenchmarks, not an end-to-end or model-quality claim."""
import argparse
import json
import platform
import statistics
import time
from pathlib import Path

import numpy as np
import pandas as pd

from stat_agent.agents import KnowledgeAgent
from stat_agent.profiling import missing_pattern_counts
from stat_agent.retrieval import LexicalEncoder, document_text


def measure(operation, repeats=5):
    samples = []
    for _ in range(repeats):
        start = time.perf_counter()
        operation()
        samples.append(time.perf_counter() - start)
    return {'median_seconds': statistics.median(samples), 'samples_seconds': samples}


def benchmark():
    masks = pd.DataFrame(np.random.default_rng(42).random((20_000, 12)) < .1,
                         columns=[f'x{i}' for i in range(12)])

    def previous_patterns():
        return masks.apply(lambda row: '|'.join(masks.columns[row]) or '<complete>', axis=1).value_counts().to_dict()

    old = previous_patterns()
    new = missing_pattern_counts(masks)
    assert {tuple(k.split('|')) if k != '<complete>' else (): int(v) for k, v in old.items()} == {
        tuple(json.loads(k)): v for k, v in new.items()}
    documents = [document_text(k) for k in KnowledgeAgent().run()]
    queries = ['PCA 主成分', 'linear regression 回归', 'kmeans 聚类'] * 7

    def uncached():
        for query in queries:
            LexicalEncoder().encode_pair(query, documents)

    def cached():
        encoder = LexicalEncoder()  # Includes the first corpus build in every sample.
        for query in queries:
            encoder.encode_pair(query, documents)

    encoder = LexicalEncoder()
    for query in queries:
        actual = encoder.encode_pair(query, documents)
        reference = LexicalEncoder().encode_pair(query, documents)
        for a, b in zip(actual, reference):
            np.testing.assert_allclose(a, b, rtol=0, atol=0)
    measurements = {
        'missing_patterns': {'before': measure(previous_patterns), 'after': measure(lambda: missing_pattern_counts(masks))},
        'repeated_lexical_queries': {'before': measure(uncached), 'after': measure(cached)},
    }
    for values in measurements.values():
        values['speedup_ratio'] = values['before']['median_seconds'] / values['after']['median_seconds']
    return {'scope': 'local microbenchmarks only; timing varies by host and workload',
            'python': platform.python_version(), 'platform': platform.system(), 'seed': 42,
            'rows': 20000, 'columns': 12, 'queries': 21, 'knowledge_documents': len(documents),
            'repeats': 5, 'output_equivalence_checked': True, 'measurements': measurements}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, default=Path('evaluation/results/optimization.json'))
    args = parser.parse_args()
    result = benchmark()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result['measurements'], indent=2))
