import copy
import io
import json
import tarfile
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from stat_agent.cran import arguments, collect_locked, digest, group, sections, plain
from stat_agent.kb_agents import SemanticProfile, profile_document, validate_evidence
from stat_agent.kb_build import build_database
from stat_agent.kb_store import KnowledgeDatabase
from stat_agent.retrieval import LexicalEncoder


def document(name='demo'):
    return {'function_id': 'Example::'+name, 'package': 'Example', 'package_version': '1.0',
            'function_name': name, 'license': 'GPL-2', 'source_url': 'https://cran.r-project.org/src/contrib/Example_1.0.tar.gz',
            'package_sha256': 'a'*64, 'rd_sha256': 'b'*64, 'rd_path': 'Example/man/demo.Rd',
            'collected_at': '2026-10-25', 'parser_version': 'test', 'aliases': [name],
            'usage_rd': name+'(x, k=2)', 'parameters': [{'name':'x','description':'Numeric matrix.'}],
            'sections': {'arguments': 'Numeric matrix. k is the number of clusters.',
                         'value': 'Returns cluster labels.', 'description': 'Clustering of observations.'}}


def semantic():
    return {'task_types': ['clustering'], 'suitability_text': '适用于观测数据的聚类分析，输入数值矩阵，输出聚类标签。',
            'claims': [
                {'category': 'input', 'statement': '输入数值矩阵', 'evidence': [{'section':'arguments','quote':'Numeric matrix.'}]},
                {'category': 'parameter', 'statement': 'k 指定簇数', 'evidence': [{'section':'arguments','quote':'k is the number of clusters.'}]},
                {'category': 'output', 'statement': '输出类别标签', 'evidence': [{'section':'value','quote':'Returns cluster labels.'}]}
            ], 'unknowns': ['研究设计未知']}


class Client:
    def __init__(self, reject_first=False, always_reject=False):
        self.config = SimpleNamespace(request_model='mock-model')
        self.usage = {'api_calls':0, 'tokens':0}
        self.receipts = []
        self.reviews = 0
        self.reject_first, self.always_reject = reject_first, always_reject
    def structured(self, system, payload, schema, *, tool_name):
        self.usage['api_calls'] += 1
        self.usage['tokens'] += 10
        self.receipts.append({'request_sha256': str(self.usage['api_calls'])})
        if tool_name == 'emit_applicability':
            draft = semantic()
            for claim in draft['claims']:
                claim['evidence_ids'] = [next(key for key, unit in payload['evidence_units'].items()
                    if span['quote'] in unit['quote'] and span['section'] == unit['section']) for span in claim.pop('evidence')]
            return draft
        self.reviews += 1
        rejected = self.always_reject or (self.reject_first and self.reviews == 1)
        return {'accepted': not rejected, 'issues': ['Check input qualifier'] if rejected else [], 'explanation':'Evidence review'}
    def metadata(self):
        return {'requested_model': 'mock-model', 'receipts': list(self.receipts), 'immutable_model_version':False}


def checked(db, name='demo', **client_options):
    return db.save_profile(profile_document(document(name), Client(**client_options)))


def test_nested_rd_signatures_and_arguments():
    source = r'''% comment
\name{demo}\alias{demo}\usage{demo(x = list(a = {1 + 2}))}
\arguments{\item{x}{A \code{numeric} matrix with \emph{nested} markup.}}
'''
    parsed = sections(source)
    assert parsed['usage'] == ['demo(x = list(a = {1 + 2}))']
    assert arguments(parsed['arguments'][0]) == [{'name':'x','description':'A numeric matrix with nested markup.'}]
    with pytest.raises(ValueError, match='Unbalanced'):
        group('{unfinished', 0)
    assert plain('x = 1, %% internal note\n\\dots') == 'x = 1, ...'


def test_source_archive_read_only_hash_and_identity(tmp_path):
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode='w:gz') as tar:
        for name, content in [('Example/DESCRIPTION', b'Package: Example\nVersion: 1.0\nLicense: GPL-2\n'),
                              ('Example/man/demo.Rd', br'\name{demo}\alias{demo}\usage{demo(x)}\arguments{\item{x}{Numeric matrix.}}'),
                              ('../../escaped.txt', b'Never extracted')]:
            info = tarfile.TarInfo(name)
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
    payload = raw.getvalue()
    archive = tmp_path/(digest(payload)+'.tar.gz')
    archive.write_bytes(payload)
    lock = {'repository': 'https://cran.r-project.org', 'collected_at':'test', 'packages': [{
        'name':'Example','version':'1.0','functions':['demo'],'sha256':digest(payload),
        'url':'https://cran.r-project.org/src/contrib/Example_1.0.tar.gz'}]}
    path = tmp_path/'lock.json'
    path.write_text(json.dumps(lock))
    docs = collect_locked(path, tmp_path, fetch=lambda _: pytest.fail('Network should not be used'))
    assert docs[0]['function_id'] == 'Example::demo'
    assert docs[0]['parameters'][0]['name'] == 'x'
    assert not (tmp_path.parent/'escaped.txt').exists()
    archive.write_bytes(payload+b'corruption')
    with pytest.raises(ValueError, match='hash'):
        collect_locked(path, tmp_path)


def test_fabricated_evidence_rejected_and_missing_sections_unknown():
    draft = SemanticProfile.model_validate(semantic())
    draft.claims[0].evidence[0].quote = 'Requires a million observations.'
    assert validate_evidence(document(), draft)
    draft.claims[0].evidence[0].section = 'invented'
    assert validate_evidence(document(), draft)


def test_cooperation_correction_is_bounded_and_logged():
    client = Client(reject_first=True)
    result = profile_document(document(), client)
    assert result['status'] == 'machine_checked'
    assert len(result['attempts']) == 2 and result['usage']['api_calls'] == 4
    assert result['semantic_verification'] == 'llm_inference_not_human_verified'
    assert not result['runtime_verified']


def test_rejected_profiles_stored_but_not_searchable(tmp_path):
    db = KnowledgeDatabase(tmp_path/'knowledge.sqlite3')
    bad = checked(db, always_reject=True)
    db.publish([bad], 'lock')
    assert len(bad['attempts']) == 2 and bad['status'] == 'needs_review'
    assert db.records() == []
    assert len(db.records(include_needs_review=True)) == 1
    assert db.search('clustering', LexicalEncoder()) == []


def test_snapshot_roundtrip_and_tamper_detection(tmp_path):
    db = KnowledgeDatabase(tmp_path/'a.sqlite3')
    record = checked(db)
    original = db.publish([record], 'lock')
    export = tmp_path/'export.json'
    bundle = db.export(export)
    restored = KnowledgeDatabase(tmp_path/'b.sqlite3')
    assert restored.restore(export) == original
    assert restored.records() == db.records()
    bundle['profiles'][0]['semantic']['suitability_text'] = 'tampered'
    export.write_text(json.dumps(bundle), encoding='utf-8')
    with pytest.raises(ValueError, match='revision'):
        restored.restore(export)
    assert restored.snapshot() == original


def test_snapshot_changes_do_not_mix_old_and_new_versions(tmp_path):
    db = KnowledgeDatabase(tmp_path/'db.sqlite3')
    one, two = checked(db, 'first'), checked(db, 'second')
    previous = db.publish([one, two], 'lock1')
    db.publish([two], 'lock2')
    assert [r['metadata']['function_id'] for r in db.records()] == ['Example::second']
    assert len(db.records(snapshot_id=previous['snapshot_id'])) == 2
    with pytest.raises(ValueError, match='distinct'):
        db.publish([one, one], 'lock')


def test_search_provenance_and_no_execution(tmp_path):
    db = KnowledgeDatabase(tmp_path/'db.sqlite3')
    db.publish([checked(db)], 'lock')
    result = db.search('clustering Numeric matrix', LexicalEncoder())
    assert result[0]['function_id'] == 'Example::demo'
    assert result[0]['source_url'].startswith('https://cran.r-project.org/')
    assert result[0]['execution_authorized'] is False


def test_resume_avoids_model_calls_and_failure_preserves_snapshot(tmp_path, monkeypatch):
    db = KnowledgeDatabase(tmp_path/'db.sqlite3')
    lock = tmp_path/'lock.json'
    lock.write_text('{}')
    monkeypatch.setattr('stat_agent.kb_build.collect_locked', lambda *a: [document()])
    initial = build_database(db, lock, tmp_path, Client())
    cached_client = Client()
    second = build_database(db, lock, tmp_path, cached_client)
    assert second['usage']['api_calls'] == 0 and second['events'][0]['cached']
    assert second['snapshot'] == initial['snapshot']
    def broken(*args):
        raise ValueError('Synthetic failure')
    monkeypatch.setattr('stat_agent.kb_build.profile_document', broken)
    failed = build_database(db, lock, tmp_path, Client(), refresh=True)
    assert failed['errors'] == 1 and failed['snapshot'] is None
    assert db.snapshot() == initial['snapshot']


def test_persistent_vectors_reuse_and_model_invalidation(tmp_path):
    class Encoder:
        name = 'fixed-model-v1'
        model_metadata = {'revision':'fixed'}
        calls = 0
        def encode_pair(self, query, docs):
            self.calls += 1
            return np.array([[1.,0.]]), np.array([[1.,0.] for _ in docs])
    db = KnowledgeDatabase(tmp_path/'db.sqlite3')
    db.publish([checked(db)], 'lock')
    encoder = Encoder()
    assert db.index(encoder)['encoded'] == 1
    assert db.index(encoder)['reused'] == 1
    assert encoder.calls == 1
    encoder.name = 'fixed-model-v2'
    assert db.index(encoder)['encoded'] == 1


def test_bundled_cran_snapshot_restores_and_matches_source_lock(tmp_path):
    from stat_agent.kb_store import checksum
    root = Path(__file__).resolve().parents[1]
    db = KnowledgeDatabase(tmp_path/'restored.sqlite3')
    snapshot = db.restore(root/'database/cran_profiles.json')
    source_lock = json.loads((root/'configs/cran_sources.lock.json').read_text(encoding='utf-8'))
    assert snapshot['source_lock_sha256'] == checksum(source_lock)
    records = db.records(include_needs_review=True)
    assert len(records) == sum(len(p['functions']) for p in source_lock['packages'])
    assert db.records()
    assert all(r['semantic_verification'] == 'llm_inference_not_human_verified' for r in records)


def test_generated_retrieval_text_cannot_drift_from_profile(tmp_path):
    db = KnowledgeDatabase(tmp_path/'db.sqlite3')
    record = profile_document(document(), Client())
    record['retrieval_text'] += '\nunsupported claims'
    with pytest.raises(ValueError, match='Retrieval text'):
        db.save_profile(record)
