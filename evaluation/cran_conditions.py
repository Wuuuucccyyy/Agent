"""Deterministic condition diagnostics; expected labels are developer authored, not independent gold."""
import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from stat_agent.agents import ProfileValidationAgent, StructureAgent, RelationsAgent
from stat_agent.kb_rules import evaluate_conditions
from stat_agent.kb_store import KnowledgeDatabase
from stat_agent.schemas import SourceProfile, TaskProfile


def evaluate(database):
    records = {r['metadata']['function_id']: r for r in database.records()}
    cases = [
        ('lda_variance_zero', 'MASS::lda', 'discriminant', {'x':[1,1,2,2], 'g':['a','a','b','b']}, ['x'], ['g'], [], {}, 'violated'),
        ('qda_insufficient_group', 'MASS::qda', 'discriminant', {'x':[1,2,3,4], 'y':[2,3,1,4], 'g':['a','a','b','b']}, ['x','y'], ['g'], [], {}, 'violated'),
        ('qda_unknown_group', 'MASS::qda', 'discriminant', {'x':[1,2,3,4]}, ['x'], [], [], {}, 'unknown'),
        ('ridge_numeric_response', 'MASS::lm.ridge', 'regression', {'x':['a','b','a'], 'y':[1,2,3]}, ['x'], [], ['y'], {}, 'satisfied'),
        ('agnes_metric_invalid', 'cluster::agnes', 'clustering', {'x':[1,2,3]}, ['x'], [], [], {'metric':'cosine'}, 'violated'),
        ('diana_distance_valid', 'cluster::diana', 'clustering', {'a':[0,1,2], 'b':[1,0,3], 'c':[2,3,0]}, ['a','b','c'], [], [], {'input_kind':'dissimilarity'}, 'satisfied'),
        ('pam_missing_k', 'cluster::pam', 'clustering', {'x':[1,2,3]}, ['x'], [], [], {}, 'unknown'),
        ('pam_disjoint_missing', 'cluster::pam', 'clustering', {'x':[1,None,3], 'y':[None,2,3]}, ['x','y'], [], [], {'k':1}, 'violated'),
        ('pam_shared_observation', 'cluster::pam', 'clustering', {'x':[1,2,3], 'y':[None,2,3]}, ['x','y'], [], [], {'k':1}, 'satisfied'),
        ('clara_sample_invalid', 'cluster::clara', 'clustering', {'x':[1,2,3]}, ['x'], [], [], {'k':1,'sampsize':1}, 'violated'),
        ('principal_components_invalid', 'psych::principal', 'pca', {'x':[1,2,3]}, ['x'], [], [], {'nfactors':2}, 'violated'),
        ('principal_correlation_valid', 'psych::principal', 'pca', {'a':[1,.5], 'b':[.5,1]}, ['a','b'], [], [], {'input_kind':'correlation'}, 'satisfied'),
    ]
    rows = []
    for id, function, kind, data, predictors, groups, targets, params, expected in cases:
        frame = pd.DataFrame(data)
        source = SourceProfile(file_name=id+'.csv', sha256=hashlib.sha256(frame.to_csv(index=False).encode()).hexdigest(),
                               format='csv', extraction_method='Developer-authored synthetic diagnostic')
        task = TaskProfile(research_goal=id, task_type=kind, predictor_variables=predictors,
                           group_variables=groups, target_variables=targets)
        profile = ProfileValidationAgent().run(frame, source, task, StructureAgent().run(frame, source), RelationsAgent().run(frame, task))
        result = evaluate_conditions(records[function], task=task, profile=profile, parameters=params)
        rows.append(dict(id=id, function_id=function, input=data, parameters=params, expected=expected,
                         passed=result['state']==expected, result=result))
    return dict(snapshot_id=database.snapshot()['snapshot_id'], total=len(rows), passed=sum(r['passed'] for r in rows),
                scope='Developer-authored necessary-condition diagnostics, not independent statistical validity evaluation.', cases=rows)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', type=Path, default=Path('database/knowledge.sqlite3'))
    parser.add_argument('--out', type=Path, default=Path('evaluation/results/cran_conditions.json'))
    args = parser.parse_args()
    report = evaluate(KnowledgeDatabase(args.db, create=False))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k != 'cases'}))
    raise SystemExit(0 if report['passed'] == report['total'] else 1)
