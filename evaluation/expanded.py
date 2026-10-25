"""Validation-only lambda selection and separate synthetic test reporting."""
import argparse
import hashlib
import json
import math
import time
from pathlib import Path

import numpy as np
import pandas as pd

from stat_agent.agents import KnowledgeAgent, ProfileValidationAgent, RelationsAgent, StructureAgent, TaskUnderstandingAgent
from stat_agent.retrieval import LexicalEncoder, pinned_encoder, retrieve
from stat_agent.schemas import SourceProfile

ROOT = Path(__file__).resolve().parents[1]


def fixture(case):
    rng = np.random.default_rng(case['seed'])
    n, p = case['n'], case['p']
    features = [f'x{i+1}' for i in range(p)]
    frame = pd.DataFrame(rng.normal(size=(n, p)), columns=features)
    if case['scenario'] == 'dependent':
        frame[features[-1]] = frame[features[0]] * 2
    targets, groups = [], []
    if case['task'] == 'regression':
        frame['y'] = frame[features[0]] * 3 + rng.normal(scale=.1, size=n)
        targets = ['y']
    if case['scenario'] in {'groups', 'manova'}:
        frame['group'] = ['a'] * (n // 2) + ['b'] * (n - n // 2)
        groups = ['group']
    if case['scenario'] == 'manova':
        frame['y1'], frame['y2'] = rng.normal(size=n), rng.normal(size=n)
        targets = ['y1', 'y2']
    if case['scenario'] == 'text':
        frame[features[0]] = ['a' if i % 2 else 'b' for i in range(n)]
    if case['scenario'] == 'infinite':
        frame.loc[0, features[0]] = np.inf
    raw = frame.to_csv(index=False, lineterminator='\n').encode('utf-8')
    source = SourceProfile(file_name=case['id']+'.csv', sha256=hashlib.sha256(raw).hexdigest(), format='csv',
                           extraction_method='Seeded synthetic generator; hash of canonical CSV')
    task = TaskUnderstandingAgent().run(case['goal'], task_type=case['task'], predictors=features, targets=targets, groups=groups)
    profile = ProfileValidationAgent().run(frame, source, task, StructureAgent().run(frame, source), RelationsAgent().run(frame, task))
    return frame, task, profile


def rerank(base, mode, penalty_lambda):
    candidates = [c.model_copy(deep=True) for c in base.ranked if mode == 'A' or not c.hard_failures]
    for c in candidates:
        c.score = c.cosine - (penalty_lambda * c.penalty_total if mode == 'C' else 0)
    return sorted(candidates, key=lambda c: (-c.score, c.knowledge_id))


def case_metrics(ranking, relevance, k=3):
    positive = {key for key, grade in relevance.items() if grade > 0}
    ids = [c.knowledge_id for c in ranking]
    if not positive:
        return {'recall_at_3': None, 'mrr': None, 'ndcg_at_3': None, 'selection_correct': not ids,
                'hard_violation': bool(ranking and ranking[0].hard_failures)}
    gains = [relevance.get(item, 0) for item in ids[:k]]
    ideal = sorted(relevance.values(), reverse=True)[:k]
    dcg = lambda values: sum((2**grade - 1) / math.log2(i+2) for i, grade in enumerate(values))
    ranks = [i+1 for i, item in enumerate(ids) if item in positive]
    return {'recall_at_3': len(set(ids[:k]) & positive)/len(positive), 'mrr': 1/min(ranks) if ranks else 0,
            'ndcg_at_3': dcg(gains)/dcg(ideal), 'selection_correct': bool(ids and ids[0] in positive),
            'hard_violation': bool(ranking and ranking[0].hard_failures)}


def summarize(rows):
    positive = [r for r in rows if r['metrics']['mrr'] is not None]
    summary = {key: sum(r['metrics'][key] for r in positive)/len(positive) if positive else None
               for key in ['recall_at_3', 'mrr', 'ndcg_at_3']}
    summary.update(selection_accuracy=sum(r['metrics']['selection_correct'] for r in rows)/len(rows),
                   hard_violation_rate=sum(r['metrics']['hard_violation'] for r in rows)/len(rows), case_count=len(rows))
    return summary


def evaluate(encoder, cases=None):
    cases_path = ROOT / 'evaluation/expanded_cases.json'
    cases = json.loads(cases_path.read_text(encoding='utf-8')) if cases is None else cases
    if len({c['id'] for c in cases}) != len(cases) or {c['split'] for c in cases} != {'validation', 'test'}:
        raise ValueError('Unique case IDs and distinct validation/test splits are required.')
    knowledge = KnowledgeAgent().run('expanded')
    prepared, hashes = [], {'validation': set(), 'test': set()}
    started = time.perf_counter()
    for case in cases:
        _, task, profile = fixture(case)
        hashes[case['split']].add(profile.source.sha256)
        base = retrieve(task, profile, knowledge, encoder, mode='A')
        prepared.append((case, base))
    if hashes['validation'] & hashes['test']:
        raise ValueError('Identical data leaked across validation and test splits.')

    def rows_for(split, mode, penalty_lambda):
        rows = []
        for case, base in prepared:
            if case['split'] == split:
                ranking = rerank(base, mode, penalty_lambda)
                rows.append({'case': case['id'], 'metrics': case_metrics(ranking, case['relevance']),
                             'ranked': [{'id': c.knowledge_id, 'cosine': c.cosine, 'penalty': c.penalty_total, 'score': c.score}
                                        for c in ranking]})
        return rows

    grid = [0., .1, .25, .5, 1.]
    validation = []
    for value in grid:
        summary = summarize(rows_for('validation', 'C', value))
        objective = summary['ndcg_at_3'] + summary['selection_accuracy'] - summary['hard_violation_rate']
        validation.append({'penalty_lambda': value, 'objective': objective, 'summary': summary})
    # Stable tie-breaking selects the smaller penalty. Test labels are never consulted here.
    selected = max(validation, key=lambda r: (r['objective'], -r['penalty_lambda']))['penalty_lambda']
    reports = {split: {mode: {'summary': summarize(rows_for(split, mode, selected)),
                            'cases': rows_for(split, mode, selected)} for mode in ['A', 'B', 'C']}
               for split in ['validation', 'test']}
    return {'scope': 'synthetic development diagnostic; human review pending; not a generalization benchmark',
            'encoder': encoder.name, 'knowledge_count': len(knowledge),
            'cases_sha256': hashlib.sha256(json.dumps(cases, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest(),
            'data_hashes': {k: sorted(v) for k, v in hashes.items()}, 'validation_grid': validation,
            'selected_penalty_lambda': selected, 'selection_rule': 'validation NDCG@3 + selection accuracy - hard violation rate; smaller lambda on ties',
            'elapsed_seconds': time.perf_counter()-started, 'reports': reports,
            'model_metadata': getattr(encoder, 'model_metadata', None),
            'limitations': ['Labels and relevance grades are developer-authored and not independently reviewed.',
                            'Test seeds/data differ; scenario families overlap. This is not an external dataset.',
                            'Task types/roles are supplied explicitly here; LLM extraction is evaluated separately.',
                            'Inference assumptions and ridge tuning remain unknown; ranking is not execution authorization.',
                            'Selected lambda is experimental and does not change application defaults.']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--embedding-config', type=Path)
    parser.add_argument('--out', type=Path, default=ROOT/'evaluation/results/expanded_lexical.json')
    args = parser.parse_args()
    encoder = pinned_encoder(args.embedding_config) if args.embedding_config else LexicalEncoder()
    result = evaluate(encoder)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    print(json.dumps({'lambda': result['selected_penalty_lambda'], 'test': {m: r['summary'] for m, r in result['reports']['test'].items()}}, indent=2))
