"""Download only the pinned safetensors model and tokenizer into the local ignored cache."""
import hashlib
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
config = json.loads((ROOT / 'configs/embedding.json').read_text(encoding='utf-8'))
folder = ROOT / '.cache/models' / config['revision']
folder.mkdir(parents=True, exist_ok=True)
manifest = {'model_id': config['model_id'], 'revision': config['revision'], 'files': {}}
for name in config['files']:
    path = folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        url = f"https://huggingface.co/{config['model_id']}/resolve/{config['revision']}/{name}"
        print('Downloading ' + name, flush=True)
        temporary = path.with_suffix(path.suffix + '.partial')
        with urllib.request.urlopen(url, timeout=60) as response, temporary.open('wb') as target:
            while chunk := response.read(1024 * 1024):
                target.write(chunk)
        temporary.replace(path)
    with path.open('rb') as handle:
        digest = hashlib.file_digest(handle, 'sha256').hexdigest()
    manifest['files'][name] = {'sha256': digest, 'bytes': path.stat().st_size}
(folder / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'folder': str(folder), 'revision': config['revision'], 'file_count': len(manifest['files'])}))
