"""Field-level analytic fixture audit; not an independent multi-agent comparison."""
import json
import math
from pathlib import Path

from stat_agent.agents import ProfileValidationAgent, RelationsAgent, StructureAgent, TaskUnderstandingAgent
from stat_agent.io import read_table

ROOT = Path(__file__).resolve().parents[1]


def lookup(data, path):
    for key in path.split('.'):
        data = data[int(key)] if isinstance(data, list) else data[key]
    return data


def assess(profile, reference):
    data = profile.model_dump(mode='json')
    fields = []
    for path, expected in reference['fields'].items():
        try:
            actual = lookup(data, path)
            present = True
        except (KeyError, IndexError, TypeError):
            actual, present = None, False
        correct = (math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-10)
                   if isinstance(expected, (float, int)) and isinstance(actual, (float, int))
                   else actual == expected) if present else False
        evidence = (profile.variables[int(path.split('.')[1])].evidence if path.startswith('variables.')
                    else profile.evidence.get(path.split('.')[0]))
        fields.append({'path': path, 'expected': expected, 'actual': actual, 'present': present,
                       'correct': correct, 'has_evidence_record': evidence is not None,
                       'unsupported_assertion': expected == 'unknown' and present and actual != 'unknown'})
    n = len(fields)
    return {'scope': '25 analytic fixture fields only; not a multi-agent superiority experiment',
            'human_review_status': reference['human_review_status'], 'field_count': n,
            'field_accuracy': sum(f['correct'] for f in fields)/n,
            'field_completeness': sum(f['present'] for f in fields)/n,
            'evidence_record_coverage': sum(f['has_evidence_record'] for f in fields)/n,
            'unsupported_assertion_count': sum(f['unsupported_assertion'] for f in fields), 'fields': fields}


if __name__ == '__main__':
    reference = json.loads((ROOT/'evaluation/profile_reference.json').read_text(encoding='utf-8'))
    frame, source = read_table(ROOT/reference['file'])
    task = TaskUnderstandingAgent().run('PCA', task_type=reference['task'], predictors=reference['predictors'])
    profile = ProfileValidationAgent().run(frame, source, task, StructureAgent().run(frame, source), RelationsAgent().run(frame, task))
    result = assess(profile, reference)
    (ROOT/'evaluation/results/profile_quality.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k != 'fields'}, indent=2))
