"""Synthetic reviewer declarations test mechanics only; they are not human reference labels."""
import copy
import json
from pathlib import Path

import pytest

from stat_agent.kb_review import (CATEGORIES, candidate_items, comparison_form, freeze_reference,
    json_text, load_packet, load_reference, main, package, pending_status, prepare, score_review, write_new)
from stat_agent.kb_store import KnowledgeDatabase

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def database(tmp_path):
    db = KnowledgeDatabase(tmp_path/'kb.sqlite3')
    db.restore(ROOT/'database/cran_profiles.json')
    return db


def synthetic_reference(manifest, sources, draft):
    """Deliberately artificial statements; never save these as project review results."""
    draft = copy.deepcopy(draft)
    draft['reviewer'] = dict(reviewer_id='test-only-not-a-real-reviewer', kind='human',
                             independent_of_generation=True, reviewed_on='2026-10-28')
    draft['authored_from_sources_before_viewing_candidates'] = True
    for i, function in enumerate(draft['functions']):
        source = sources[function['function_id']]
        quote = source['sections']['description'][:100]
        function['scope_complete'] = True
        function['facts'] = [dict(id=f'f{i}_{category}', category=category,
            statement='Synthetic test fact, not an actual expert conclusion.', status='derived', required=True,
            evidence=[{'section':'description','quote':quote}], rationale='Test fixture only.') for category in CATEGORIES]
    return draft


def review_fixture(db):
    manifest, sources, items, draft = package(db)
    reference = synthetic_reference(manifest, sources, draft)
    frozen = freeze_reference(reference, manifest, sources)
    _, annotations = comparison_form(frozen, manifest, sources, items)
    return manifest, sources, items, frozen, annotations


def fill_fixture(annotations, frozen, items):
    annotations = copy.deepcopy(annotations)
    annotations['reviewer'] = dict(reviewer_id='test-only-comparator', kind='human',
                                 independent_of_generation=True, reviewed_on='2026-10-28')
    facts_by_function = {f['function_id']:[v['id'] for v in f['facts']] for f in frozen['reference']['functions']}
    item_map = {i['item_id']:i for i in items}
    for item in annotations['items']:
        item.update(verdict='supported', reference_fact_ids=facts_by_function[item_map[item['item_id']]['function_id']],
                    rationale='Synthetic test decision.')
    for coverage in annotations['coverage']:
        function = next(k for k, ids in facts_by_function.items() if coverage['fact_id'] in ids)
        item_id = next(i['item_id'] for i in items if i['function_id'] == function)
        coverage.update(verdict='covered', candidate_item_ids=[item_id], rationale='Synthetic test coverage.')
    return annotations


def test_prepare_is_source_only_and_preserves_reviewer_edits(database, tmp_path):
    packet = tmp_path/'packet'
    manifest = prepare(database, packet)
    assert prepare(database, packet) == manifest
    assert set(p.name for p in packet.iterdir()) == {'manifest.json','sources.json','reference.template.json','README.md'}
    assert all(not f['facts'] and not f['scope_complete'] for f in json.loads((packet/'reference.template.json').read_text())['functions'])
    sources_text = (packet/'sources.json').read_text(encoding='utf-8')
    assert 'semantic_verification' not in sources_text and 'source_audit' not in sources_text
    for record in database.records():
        assert record['semantic']['suitability_text'] not in sources_text
    edited = (packet/'reference.template.json').read_text()+'\n'
    (packet/'reference.template.json').write_text(edited)
    with pytest.raises(ValueError, match='overwrite'):
        prepare(database, packet)
    assert (packet/'reference.template.json').read_text() == edited


def test_empty_reference_has_no_quality_score_and_cannot_freeze(database):
    manifest, sources, _, draft = package(database)
    status = pending_status(manifest)
    assert status['metrics'] is None and not status['independent_human_review_complete']
    with pytest.raises(ValueError, match='human reviewer'):
        freeze_reference(draft, manifest, sources)


@pytest.mark.parametrize('kind', ['ai','developer_fixture','unassigned'])
def test_model_or_developer_fixture_cannot_become_human_reference(database, kind):
    manifest, sources, _, draft = package(database)
    draft = synthetic_reference(manifest, sources, draft)
    draft['reviewer']['kind'] = kind
    with pytest.raises(ValueError, match='human reviewer'):
        freeze_reference(draft, manifest, sources)


def test_reference_requires_source_first_complete_scope_and_exact_quotes(database):
    manifest, sources, _, draft = package(database)
    original = synthetic_reference(manifest, sources, draft)
    mutations = [lambda d:d.update(authored_from_sources_before_viewing_candidates=False),
        lambda d:d.update(source_set_id='0'*64),
        lambda d:d['functions'].pop(),
        lambda d:d['functions'][0]['facts'].pop(),
        lambda d:d['functions'][0]['facts'][0]['evidence'][0].update(quote='This does not occur in the actual source.'),
        lambda d:d['functions'][0]['facts'][0]['evidence'][0].update(quote='        '),
        lambda d:d['functions'][1]['facts'][0].update(id=d['functions'][0]['facts'][0]['id']),
        lambda d:d['reviewer'].update(reviewed_on='2026-02-30')]
    for mutate in mutations:
        draft = copy.deepcopy(original)
        mutate(draft)
        with pytest.raises(ValueError):
            freeze_reference(draft, manifest, sources)


def test_packet_and_frozen_reference_tampering_rejected(database, tmp_path):
    packet = tmp_path/'packet'
    prepare(database, packet)
    manifest, sources, items = load_packet(database, packet)
    data = json.loads((packet/'sources.json').read_text(encoding='utf-8'))
    data[next(iter(data))]['sections']['description'] += ' corruption'
    (packet/'sources.json').write_text(json_text(data), encoding='utf-8')
    with pytest.raises(ValueError, match='differs'):
        load_packet(database, packet)
    _, _, _, frozen, _ = review_fixture(database)
    frozen['reference']['reviewer']['reviewer_id'] = 'changed'
    with pytest.raises(ValueError, match='integrity'):
        load_reference(frozen, manifest, sources)


def test_pending_partial_and_uncertain_never_produce_accuracy(database):
    manifest, sources, items, frozen, blank = review_fixture(database)
    assert score_review(frozen, blank, manifest, sources, items)['metrics'] is None
    full = fill_fixture(blank, frozen, items)
    full['items'][-1]['verdict'] = 'unreviewed'
    result = score_review(frozen, full, manifest, sources, items)
    assert result['status'] == 'awaiting_annotation' and result['metrics'] is None
    full['items'][-1]['verdict'] = 'uncertain'
    result = score_review(frozen, full, manifest, sources, items)
    assert result['status'] == 'needs_adjudication' and result['metrics'] is None


def test_full_metrics_use_fixed_denominators_and_do_not_promote_database(database):
    manifest, sources, items, frozen, blank = review_fixture(database)
    before = database.records()
    full = fill_fixture(blank, frozen, items)
    # Last item is not used by the synthetic coverage mappings.
    full['items'][-1]['verdict'] = 'unsupported'
    full['items'][-2]['verdict'] = 'contradicted'
    full['coverage'][-1].update(verdict='missing', candidate_item_ids=[])
    report = score_review(frozen, full, manifest, sources, items)
    assert report['status'] == 'annotation_complete'
    assert report['metrics']['field_accuracy'] == (len(items)-2)/len(items)
    assert report['metrics']['unsupported_inference_rate'] == 1/len(items)
    assert report['metrics']['field_completeness'] == (len(full['coverage'])-1)/len(full['coverage'])
    assert not report['independent_identity_authenticated'] and not report['changes_database_trust']
    assert database.records() == before


def test_missing_duplicate_cross_function_and_stale_labels_rejected(database):
    manifest, sources, items, frozen, blank = review_fixture(database)
    full = fill_fixture(blank, frozen, items)
    other_fact = frozen['reference']['functions'][1]['facts'][0]['id']
    mutations = [lambda a:a['items'].pop(), lambda a:a['items'].append(a['items'][0]),
        lambda a:a['coverage'].pop(), lambda a:a.update(packet_id='stale'),
        lambda a:a.update(reference_id='stale'),
        lambda a:a['items'][0].update(reference_fact_ids=[other_fact]),
        lambda a:a['coverage'][0].update(candidate_item_ids=[items[-1]['item_id']]),
        lambda a:a['items'][0].update(verdict='unsupported'),
        lambda a:a['reviewer'].update(independent_of_generation=False)]
    for mutate in mutations:
        annotations = copy.deepcopy(full)
        mutate(annotations)
        with pytest.raises(ValueError):
            score_review(frozen, annotations, manifest, sources, items)


def test_snapshot_change_keeps_old_packet_bound(database, tmp_path):
    packet = tmp_path/'packet'
    old = prepare(database, packet)
    records = database.records()
    record = copy.deepcopy(records[0])
    record.pop('revision')
    record['semantic_verification'] = 'new-test-review-state'
    record = database.save_profile(record)
    database.publish([record]+records[1:], old['snapshot']['source_lock_sha256'])
    loaded, _, _ = load_packet(database, packet)
    assert loaded == old
    assert package(database)[0]['packet_id'] != old['packet_id']


def test_cli_full_workflow_and_overwrite_guard(database, tmp_path, capsys):
    common = ['--db',str(database.path),'--packet',str(tmp_path/'packet')]
    assert main(['prepare',*common]) == 0
    assert main(['status',*common,'--out',str(tmp_path/'status.json')]) == 0
    manifest, sources, _, draft = package(database)
    path = tmp_path/'reference.json'
    write_new(path, json_text(synthetic_reference(manifest, sources, draft)))
    frozen = tmp_path/'frozen.json'
    assert main(['freeze',*common,'--reference',str(path),'--out',str(frozen)]) == 0
    assert main(['status',*common,'--reference',str(frozen),'--out',str(tmp_path/'frozen-status.json')]) == 0
    assert json.loads((tmp_path/'frozen-status.json').read_text())['status'] == 'awaiting_annotation'
    form = tmp_path/'form'
    assert main(['form',*common,'--reference',str(frozen),'--out',str(form)]) == 0
    report = tmp_path/'report.json'
    assert main(['score',*common,'--reference',str(frozen),'--annotations',str(form/'annotations.template.json'),'--out',str(report)]) == 0
    assert json.loads(report.read_text())['metrics'] is None
    with pytest.raises(ValueError, match='overwrite'):
        write_new(report, '{}')
    capsys.readouterr()


def test_bundled_packet_matches_locked_snapshot(database):
    manifest, _, items = load_packet(database, ROOT/'evaluation/review/cran-v04')
    assert manifest['function_count'] == 8
    assert len(items) == manifest['item_count']
    draft = json.loads((ROOT/'evaluation/review/cran-v04/reference.template.json').read_text(encoding='utf-8'))
    assert draft['reviewer']['kind'] == 'unassigned'
    assert all(not f['facts'] for f in draft['functions'])
