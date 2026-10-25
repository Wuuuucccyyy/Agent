"""Explicit live DeepSeek acceptance: synthetic requests only, actual token receipts."""
import json
from pathlib import Path

from stat_agent.llm import DeepSeekClient, DeepSeekTaskAgent, load_ccswitch

root = Path(__file__).resolve().parents[1]
cases = json.loads((root / 'evaluation/task_cases.json').read_text(encoding='utf-8'))
client = DeepSeekClient(load_ccswitch())
agent = DeepSeekTaskAgent(client)
results = []
for case in cases:
    profile = agent.run(case['goal'], columns=case['columns'])
    actual = profile.model_dump(mode='json')
    checks = {k: (set(actual[k]) == set(v) if isinstance(v, list) else actual[k] == v) for k, v in case['expected'].items()}
    results.append({'id': case['id'], 'checks': checks, 'passed': all(checks.values()), 'profile': actual})
    print(json.dumps({'case': case['id'], 'passed': all(checks.values())}), flush=True)
result = {'scope': 'developer-authored synthetic acceptance, not independent human annotation',
          'human_review_status': 'pending', 'model': client.metadata(), 'usage': client.usage,
          'cases_passed': sum(r['passed'] for r in results), 'cases_total': len(results), 'results': results}
out = root / 'evaluation/results/deepseek_tasks.json'
out.parent.mkdir(exist_ok=True)
if out.exists():
    # Preserve the initial failure record when iterating on these development acceptance cases.
    initial = out.with_name('deepseek_tasks_initial.json')
    if not initial.exists():
        initial.write_bytes(out.read_bytes())
out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
if not all(r['passed'] for r in results):
    raise SystemExit(2)
