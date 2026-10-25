"""Explicit live extraction of a public R reference into an unverified draft."""
import hashlib
import json
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

from stat_agent.knowledge_drafts import extract_draft
from stat_agent.llm import DeepSeekClient, load_ccswitch


class Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
    def handle_data(self, data):
        if data.strip():
            self.parts.append(data.strip())


root = Path(__file__).resolve().parents[1]
url = 'https://stat.ethz.ch/R-manual/R-devel/library/stats/html/prcomp.html'
with urllib.request.urlopen(url, timeout=30) as response:
    raw = response.read(100_001)
if len(raw) > 100000:
    raise ValueError('Reference too large for this demonstration.')
folder = root / '.cache/sources'
folder.mkdir(parents=True, exist_ok=True)
(folder / 'prcomp.html').write_bytes(raw)
parser = Text()
parser.feed(raw.decode('utf-8'))
client = DeepSeekClient(load_ccswitch())
draft = extract_draft(client, '\n'.join(parser.parts), package='stats', function_name='prcomp',
                      source_url=url, package_version='R-devel reference; runtime not installed', retrieved_on='2026-10-24')
result = {'scope': 'unverified LLM draft, not automatically imported into the curated library',
          'source_url': url, 'source_sha256': hashlib.sha256(raw).hexdigest(),
          'draft': draft.model_dump(mode='json'), 'usage': client.usage, 'model': client.metadata()}
out = root / 'evaluation/results/knowledge_draft.json'
out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'id': draft.id, 'verification': draft.verification_status, 'usage': client.usage}))
