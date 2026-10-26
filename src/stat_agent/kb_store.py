"""Versioned candidate profiles and persistent semantic vectors in SQLite."""
import hashlib
import json
import sqlite3
from pathlib import Path

import numpy as np

from .kb_agents import SemanticProfile, validate_evidence
from .retrieval import normalize


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def checksum(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


class KnowledgeDatabase:
    def __init__(self, path, *, create=True):
        self.path = Path(path)
        if not create and not self.path.exists():
            raise ValueError('Knowledge database is missing; build or restore it first.')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS profiles (
                    revision TEXT PRIMARY KEY, function_id TEXT NOT NULL, fingerprint TEXT NOT NULL,
                    status TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS profile_fingerprint ON profiles(fingerprint);
                CREATE TABLE IF NOT EXISTS snapshots (snapshot_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS builds (build_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS vectors (
                    revision TEXT NOT NULL REFERENCES profiles(revision), model TEXT NOT NULL,
                    text_hash TEXT NOT NULL, dimensions INTEGER NOT NULL, vector TEXT NOT NULL,
                    PRIMARY KEY (revision,model));
            ''')

    def connect(self):
        db = sqlite3.connect(self.path)
        db.execute('PRAGMA foreign_keys=ON')
        return db

    def cached(self, fingerprint, *, include_needs_review=False):
        with self.connect() as db:
            row = db.execute("SELECT payload FROM profiles WHERE fingerprint=? AND (status='machine_checked' OR ?) ORDER BY rowid DESC LIMIT 1",
                             (fingerprint, int(include_needs_review))).fetchone()
        return json.loads(row[0]) if row else None

    @staticmethod
    def validate_record(record):
        payload = {k: v for k, v in record.items() if k != 'revision'}
        if 'revision' in record and record['revision'] != checksum(payload):
            raise ValueError('Profile revision does not match its content.')
        draft = SemanticProfile.model_validate(record['semantic'])
        if any(record['source'].get(key) != value for key, value in record['metadata'].items()):
            raise ValueError('Source and function metadata differ.')
        if record['status'] not in {'machine_checked', 'needs_review'}:
            raise ValueError('Unsupported profile status.')
        if record['status'] == 'machine_checked':
            if validate_evidence(record['source'], draft):
                raise ValueError('A checked profile has invalid source quotations.')
            review = record['attempts'][-1]['review']
            if not review['accepted'] or review['issues']:
                raise ValueError('A checked profile has a failing review.')
        expected_text = '\n'.join([record['metadata']['function_id'], ' '.join(draft.task_types),
            draft.suitability_text, *[c.category+': '+c.statement for c in draft.claims]])
        if record['retrieval_text'] != expected_text:
            raise ValueError('Retrieval text differs from the validated semantic profile.')
        from .kb_rules import validate_rule_set
        validate_rule_set(record)
        return dict(payload, revision=checksum(payload))

    def save_profile(self, record):
        record = self.validate_record(record)
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO profiles VALUES (?,?,?,?,?)',
                       (record['revision'], record['metadata']['function_id'], record['build_fingerprint'],
                        record['status'], canonical(record)))
        return record

    def save_build(self, build):
        with self.connect() as db:
            db.execute('INSERT INTO builds VALUES (?,?)', (build['build_id'], canonical(build)))

    def publish(self, records, source_lock_hash):
        """Publish one immutable batch snapshot, without merging stale prior versions."""
        ids = [r['metadata']['function_id'] for r in records]
        if len(ids) != len(set(ids)) or not records:
            raise ValueError('A snapshot requires distinct nonempty function identities.')
        snapshot = {'schema_version': '1.0', 'source_lock_sha256': source_lock_hash,
                    'revisions': sorted(r['revision'] for r in records)}
        snapshot['snapshot_id'] = checksum(snapshot)
        with self.connect() as db:
            for revision in snapshot['revisions']:
                if not db.execute('SELECT 1 FROM profiles WHERE revision=?', (revision,)).fetchone():
                    raise ValueError('Snapshot refers to a missing profile.')
            db.execute('INSERT OR IGNORE INTO snapshots VALUES (?,?)', (snapshot['snapshot_id'], canonical(snapshot)))
            db.execute("INSERT OR REPLACE INTO settings VALUES ('active_snapshot',?)", (snapshot['snapshot_id'],))
        return snapshot

    def snapshot(self, snapshot_id=None):
        with self.connect() as db:
            if snapshot_id is None:
                row = db.execute("SELECT value FROM settings WHERE key='active_snapshot'").fetchone()
                if not row:
                    raise ValueError('No complete published snapshot is available.')
                snapshot_id = row[0]
            row = db.execute('SELECT payload FROM snapshots WHERE snapshot_id=?', (snapshot_id,)).fetchone()
        if not row:
            raise ValueError('Unknown knowledge snapshot.')
        return json.loads(row[0])

    def records(self, *, snapshot_id=None, include_needs_review=False):
        snapshot = self.snapshot(snapshot_id)
        with self.connect() as db:
            result = [json.loads(db.execute('SELECT payload FROM profiles WHERE revision=?', (r,)).fetchone()[0])
                      for r in snapshot['revisions']]
        return sorted((r for r in result if include_needs_review or r['status'] == 'machine_checked'),
                      key=lambda r: r['metadata']['function_id'])

    def export(self, path):
        snapshot = self.snapshot()
        bundle = {'format': 'stat-agent-knowledge-export-1', 'snapshot': snapshot,
                  'profiles': self.records(include_needs_review=True),
                  'notice': 'Machine-reviewed LLM profiles; not human-verified or executed in R. Source licenses remain applicable.'}
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(bundle, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
        Path(path).with_suffix('.md').write_text(render_catalog(bundle), encoding='utf-8')
        return bundle

    def restore(self, path):
        bundle = json.loads(Path(path).read_text(encoding='utf-8'))
        if bundle['format'] != 'stat-agent-knowledge-export-1':
            raise ValueError('Unknown export format.')
        records = [self.validate_record(r) for r in bundle['profiles']]
        snapshot = bundle['snapshot']
        body = {k: v for k, v in snapshot.items() if k != 'snapshot_id'}
        if snapshot['snapshot_id'] != checksum(body) or sorted(r['revision'] for r in records) != snapshot['revisions']:
            raise ValueError('Export snapshot integrity check failed.')
        if len({r['metadata']['function_id'] for r in records}) != len(records):
            raise ValueError('Duplicate function identity in export.')
        for record in records:
            self.save_profile(record)
        return self.publish(records, snapshot['source_lock_sha256'])

    def index(self, encoder):
        if not hasattr(encoder, 'model_metadata'):
            raise ValueError('Persistent indexing requires a pinned semantic model.')
        records = self.records()
        missing = []
        with self.connect() as db:
            for record in records:
                row = db.execute('SELECT text_hash FROM vectors WHERE revision=? AND model=?',
                                 (record['revision'], encoder.name)).fetchone()
                if not row or row[0] != checksum(record['retrieval_text']):
                    missing.append(record)
        if missing:
            _, matrix = encoder.encode_pair('CRAN candidate index', [r['retrieval_text'] for r in missing])
            matrix = normalize(matrix)
            if matrix.shape[0] != len(missing):
                raise ValueError('Model returned the wrong document count.')
            with self.connect() as db:
                for record, vector in zip(missing, matrix):
                    db.execute('INSERT OR REPLACE INTO vectors VALUES (?,?,?,?,?)',
                        (record['revision'], encoder.name, checksum(record['retrieval_text']), len(vector), canonical(vector.tolist())))
        return {'model': encoder.name, 'total': len(records), 'encoded': len(missing), 'reused': len(records)-len(missing)}

    def search(self, query, encoder, top_k=5, *, profile=None, task=None, parameters=None, include_excluded=False):
        if not query.strip() or not 1 <= top_k <= 100:
            raise ValueError('Nonempty query and top_k between 1 and 100 required.')
        records = self.records()
        if not records:
            return []
        if hasattr(encoder, 'model_metadata'):
            self.index(encoder)
            query_vector = normalize(encoder.model.encode_query([query], convert_to_numpy=True, **encoder.query_options))
            with self.connect() as db:
                matrix = np.array([json.loads(db.execute('SELECT vector FROM vectors WHERE revision=? AND model=?',
                    (r['revision'], encoder.name)).fetchone()[0]) for r in records])
            matrix = normalize(matrix)
        else:
            query_vector, matrix = encoder.encode_pair(query, [r['retrieval_text'] for r in records])
            query_vector, matrix = normalize(query_vector), normalize(matrix)
        scores = np.clip((query_vector @ matrix.T)[0], -1, 1)
        from .kb_rules import evaluate_conditions
        parameters = parameters or {}
        if set(parameters) - {'*', *[r['metadata']['function_id'] for r in records]}:
            raise ValueError('Parameters name an unknown function.')
        verdicts = {r['revision']: evaluate_conditions(r, profile=profile, task=task,
            parameters={**parameters.get('*', {}), **parameters.get(r['metadata']['function_id'], {})}) for r in records}
        ranked = sorted(zip(records, scores), key=lambda pair: (-pair[1], pair[0]['metadata']['function_id']))
        if not include_excluded:
            ranked = [(r, score) for r, score in ranked if not verdicts[r['revision']]['excluded']][:top_k]
        # Diagnostic callers need every exclusion before applying their eligible top-k.
        return [{'function_id': r['metadata']['function_id'], 'package_version': r['metadata']['package_version'],
                 'revision': r['revision'], 'cosine': float(score), 'suitability_text': r['semantic']['suitability_text'],
                 'claims': r['semantic']['claims'], 'unknowns': r['semantic']['unknowns'],
                 'status': r['status'], 'semantic_verification': r['semantic_verification'],
                 'conditions': verdicts[r['revision']],
                 'source_url': r['metadata']['source_url'], 'execution_authorized': False} for r, score in ranked]


def render_catalog(bundle):
    lines = ['# CRAN 函数画像目录', '', '由数据库快照自动导出。语义内容为模型推断，未经过独立人工审核或 R 运行验证。', '',
             'machine_checked 进入候选搜索；needs_review 保留待复核并从默认搜索排除。', '',
             '来源文档及改编部分沿用对应 CRAN 许可，见同目录 README 与许可证。', '',
             '快照：`'+bundle['snapshot']['snapshot_id']+'`', '']
    for record in bundle['profiles']:
        meta, semantic = record['metadata'], record['semantic']
        lines += ['## '+meta['function_id'], '',
                  f"版本：{meta['package_version']}；状态：**{record['status']}**。", '',
                  semantic['suitability_text'], '', '### 函数接口', '', '```r', meta['usage_rd'], '```', '',
                  '参数：'+', '.join(p['name'] for p in meta['parameters']), '', '### 适用条件与输出', '']
        for claim in semantic['claims']:
            lines.append('- **'+claim['category']+'**：'+claim['statement'])
        if record.get('source_audit'):
            lines += ['', '### 来源复核与可计算条件', '',
                      'Codex 对锁定版本原文逐项复核；保留原始模型复核记录，仍未经过独立人工审核或 R 运行。', '']
            lines += ['- '+d['decision']+'：'+d['reason'] for d in record['source_audit']['decisions']]
            lines += ['', '规则（满足 / 不满足 / 未知；明确违反硬条件才排除）：', '']
            lines += ['- `'+r['id']+'`（'+r['severity']+'，'+r['origin']+'）：'+r['description'] for r in record['rules']['rules']]
        lines += ['', '### 未知与待复核', '']
        lines += ['- '+item for item in semantic['unknowns']]
        lines += ['- 复核意见：'+item for item in record['attempts'][-1]['review']['issues']]
        lines += ['', f"[官方源码包]({meta['source_url']})；文档 `{meta['rd_path']}`。", '',
                  '画像版本：`'+record['revision']+'`。逐条原文证据和参数说明见同名 JSON。', '']
    return '\n'.join(lines)
