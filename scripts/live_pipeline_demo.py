"""Explicit opt-in: two real API calls on synthetic repository data only."""
import json
from pathlib import Path

from stat_agent.llm import DeepSeekClient, DeepSeekTaskAgent, load_ccswitch
from stat_agent.pipeline import run_pipeline
from stat_agent.retrieval import pinned_encoder

ROOT = Path(__file__).resolve().parents[1]


if __name__ == '__main__':
    encoder = pinned_encoder(ROOT / 'configs/embedding.json')
    agent = DeepSeekTaskAgent(DeepSeekClient(load_ccswitch()))
    cases = [
        ('pca', '使用 stats::prcomp 对 x1、x2、x3 做主成分分析。'),
        ('regression', '使用 stats::lm，以 y 为目标变量，x1 和 x2 为解释变量做线性回归。'),
    ]
    records = []
    for name, goal in cases:
        folder = run_pipeline(ROOT/f'examples/data/{name}.csv', goal, ROOT/'runs/live',
                              encoder=encoder, task_agent=agent, knowledge_library='expanded')
        run = json.loads((folder/'run.json').read_text(encoding='utf-8'))
        # Full artifacts contain synthetic values only and remain ignored under runs/.
        records.append({key: run[key] for key in [
            'application_version', 'started_at', 'status', 'configuration', 'task', 'execution',
            'usage', 'llm', 'knowledge_sha256', 'elapsed_seconds', 'events']})
        records[-1]['case'] = name
        records[-1]['source_sha256'] = run['profile']['source']['sha256']
        records[-1]['retrieval'] = run['retrieval']
    result = {'scope': 'Two synthetic end-to-end acceptance examples; not an accuracy benchmark.',
              'embedding_model': encoder.model_metadata, 'runs': records}
    destination = ROOT/'evaluation/results/live_pipeline.json'
    if destination.exists():
        # Keep previous API acceptance evidence instead of silently overwriting it.
        backup = destination.with_name('live_pipeline_previous.json')
        if backup.exists():
            raise SystemExit('Archive the existing previous report before another live rerun.')
        backup.write_bytes(destination.read_bytes())
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    print(json.dumps([{'case': r['case'], 'status': r['status'], 'validated': r['execution']['validation_passed'],
                       'api_calls': r['usage']['api_calls']} for r in records]))
    raise SystemExit(0 if all(r['status'] == 'success' and r['execution']['validation_passed'] for r in records) else 1)
