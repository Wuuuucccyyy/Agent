"""Source-first human reference workflow; no generated labels or automatic trust promotion."""
import argparse
import json
import re
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from .kb_agents import EvidenceSpan
from .kb_store import KnowledgeDatabase, checksum

CATEGORIES = ['task', 'input', 'roles', 'parameters', 'conditions', 'output', 'unknowns']
POLICY = 'source-first-human-reference-1'


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, str_strip_whitespace=True)


class Reviewer(StrictModel):
    reviewer_id: str = ''
    kind: Literal['unassigned', 'human', 'ai', 'developer_fixture'] = 'unassigned'
    independent_of_generation: StrictBool = False
    reviewed_on: str = ''


class ReferenceFact(StrictModel):
    id: str = Field(pattern=r'^[a-zA-Z0-9_-]+$', min_length=1, max_length=80)
    category: Literal['task', 'input', 'roles', 'parameters', 'conditions', 'output', 'unknowns']
    statement: str = Field(min_length=1, max_length=1500)
    status: Literal['documented', 'derived', 'not_established']
    required: StrictBool = True
    evidence: list[EvidenceSpan] = Field(default_factory=list, max_length=12)
    rationale: str = Field(min_length=1, max_length=2000)

    @model_validator(mode='after')
    def supported_facts_need_quotes(self):
        if self.status != 'not_established' and not self.evidence:
            raise ValueError('Documented and derived reference facts require source evidence.')
        return self


class FunctionReference(StrictModel):
    function_id: str
    source_rd_sha256: str
    scope_complete: StrictBool = False
    facts: list[ReferenceFact] = Field(default_factory=list, max_length=200)


class ReferenceDraft(StrictModel):
    schema_version: Literal['1.0'] = '1.0'
    source_set_id: str
    reviewer: Reviewer = Field(default_factory=Reviewer)
    authored_from_sources_before_viewing_candidates: StrictBool = False
    functions: list[FunctionReference]


class ItemJudgment(StrictModel):
    item_id: str
    verdict: Literal['unreviewed', 'supported', 'contradicted', 'unsupported', 'uncertain'] = 'unreviewed'
    reference_fact_ids: list[str] = Field(default_factory=list)
    rationale: str = ''


class CoverageJudgment(StrictModel):
    fact_id: str
    verdict: Literal['unreviewed', 'covered', 'missing', 'uncertain'] = 'unreviewed'
    candidate_item_ids: list[str] = Field(default_factory=list)
    rationale: str = ''


class ReviewAnnotations(StrictModel):
    schema_version: Literal['1.0'] = '1.0'
    packet_id: str
    reference_id: str
    reviewer: Reviewer = Field(default_factory=Reviewer)
    items: list[ItemJudgment]
    coverage: list[CoverageJudgment]


def human_declaration(reviewer):
    from datetime import date
    if reviewer.kind != 'human' or not reviewer.reviewer_id or not reviewer.independent_of_generation:
        raise ValueError('A named human reviewer independent of generation must make the declaration.')
    try:
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', reviewer.reviewed_on):
            raise ValueError('Invalid date format')
        date.fromisoformat(reviewer.reviewed_on)
    except ValueError as exc:
        raise ValueError('Human review requires reviewed_on in YYYY-MM-DD format.') from exc


def candidate_items(records):
    items = []
    for record in records:
        function = record['metadata']['function_id']

        def add(key, category, payload):
            items.append(dict(item_id=function+'#'+key, function_id=function, category=category,
                              profile_revision=record['revision'], payload=payload))

        semantic = record['semantic']
        add('task_types', 'task', semantic['task_types'])
        add('suitability_text', 'summary', semantic['suitability_text'])
        for i, claim in enumerate(semantic['claims']):
            add(f'claim:{i}', 'claim', claim)
        for i, unknown in enumerate(semantic['unknowns']):
            add(f'unknown:{i}', 'unknowns', unknown)
        if 'rules' in record:
            for rule in record['rules']['rules']:
                add('rule:'+rule['id'], 'rule', rule)
            add('rule_configuration', 'rule_configuration', {
                'defaults': record['rules']['defaults'], 'coverage_notes': record['rules']['coverage_notes']})
    return items


def package(database, snapshot_id=None):
    snapshot = database.snapshot(snapshot_id)
    records = database.records(snapshot_id=snapshot['snapshot_id'], include_needs_review=True)
    for record in records:
        KnowledgeDatabase.validate_record(record)
    sources = {r['metadata']['function_id']: r['source'] for r in records}
    source_set_id = checksum(sources)
    items = candidate_items(records)
    manifest = dict(policy=POLICY, snapshot=snapshot, source_set_id=source_set_id,
                    candidate_items_sha256=checksum(items), function_count=len(records), item_count=len(items),
                    category_counts={k: sum(i['category'] == k for i in items) for k in sorted({i['category'] for i in items})})
    manifest['packet_id'] = checksum(manifest)
    draft = ReferenceDraft(source_set_id=source_set_id, functions=[
        FunctionReference(function_id=k, source_rd_sha256=v['rd_sha256']) for k, v in sources.items()])
    return manifest, sources, items, draft.model_dump(mode='json')


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def json_text(value):
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n'


def write_new(path, content):
    """Never overwrite a reviewer's work, including files written by another invocation."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_text(encoding='utf-8') == content:
            return
        raise ValueError(f'Refusing to overwrite existing review artifact: {path}')
    with path.open('x', encoding='utf-8', newline='\n') as handle:
        handle.write(content)


def prepare(database, folder):
    manifest, sources, _, draft = package(database)
    instructions = '''# 独立来源参考：第一阶段

请先只阅读 sources.json，在 reference.template.json 的副本中编写参考事实。
不要先看候选画像、旧复核意见或 candidate_items。当前目录不包含候选内容。
每个函数覆盖 task、input、roles、parameters、conditions、output、unknowns 七个方面；
没有在文档建立的事实写为 not_established，说明范围和理由，不补造假设。
documented / derived 必须引用本包对应函数原文；derived 还应解释推导。
事实的 required 字段决定后续完整率分母，必须在看候选之前确定。
完成后填写真实复核身份、日期、独立性与 source-only 声明，设置 scope_complete=true。

用 kb review freeze 固定参考后，再用 kb review form 获取候选对照表。
原文继承对应 CRAN 许可，见仓库 database/LICENSE-CRAN-DERIVED.txt。
此材料由程序整理，所有答案留空；本目录的存在不表示人工复核已经完成。
'''
    artifacts = {'manifest.json': json_text(manifest), 'sources.json': json_text(sources),
                 'reference.template.json': json_text(draft), 'README.md': instructions}
    folder = Path(folder)
    # Validate all existing files before writing anything, preserving filled templates.
    for name, content in artifacts.items():
        path = folder/name
        if path.exists() and path.read_text(encoding='utf-8') != content:
            raise ValueError(f'Refusing to overwrite existing review artifact: {path}')
    for name, content in artifacts.items():
        write_new(folder/name, content)
    return manifest


def load_packet(database, folder):
    manifest = read_json(Path(folder)/'manifest.json')
    expected, sources, items, _ = package(database, manifest['snapshot']['snapshot_id'])
    if manifest != expected or read_json(Path(folder)/'sources.json') != sources:
        raise ValueError('Review packet differs from its immutable database snapshot or source documents.')
    return manifest, sources, items


def validate_reference(draft, manifest, sources):
    draft = ReferenceDraft.model_validate(draft)
    human_declaration(draft.reviewer)
    if not draft.authored_from_sources_before_viewing_candidates:
        raise ValueError('Reference must be authored from sources before viewing candidates.')
    if draft.source_set_id != manifest['source_set_id']:
        raise ValueError('Reference source version mismatch.')
    identities = [f.function_id for f in draft.functions]
    if len(identities) != len(set(identities)) or set(identities) != set(sources):
        raise ValueError('Reference must contain exactly one entry for every source function.')
    all_ids = set()
    for function in draft.functions:
        source = sources[function.function_id]
        if function.source_rd_sha256 != source['rd_sha256']:
            raise ValueError('Reference Rd version mismatch.')
        if not function.scope_complete or {f.category for f in function.facts} != set(CATEGORIES):
            raise ValueError('Each reference must explicitly cover all seven field categories.')
        if not any(f.required for f in function.facts):
            raise ValueError('Each function needs required facts for the completeness denominator.')
        for fact in function.facts:
            if fact.id in all_ids:
                raise ValueError('Reference fact IDs must be globally unique.')
            all_ids.add(fact.id)
            for evidence in fact.evidence:
                normalized = lambda s: re.sub(r'\s+', ' ', s).strip()
                if not normalized(evidence.quote) or normalized(evidence.quote) not in normalized(source['sections'].get(evidence.section, '')):
                    raise ValueError('Reference quotation is absent from the locked function source.')
    return draft


def freeze_reference(draft, manifest, sources):
    validated = validate_reference(draft, manifest, sources).model_dump(mode='json')
    body = dict(policy=POLICY, reference=validated,
                verification='Reviewer identity, independence and source-first order are declarations; not authenticated by software.')
    return dict(body, reference_id=checksum(body))


def load_reference(frozen, manifest, sources):
    body = {k: v for k, v in frozen.items() if k != 'reference_id'}
    if frozen.get('policy') != POLICY or frozen.get('reference_id') != checksum(body):
        raise ValueError('Frozen reference integrity check failed.')
    expected = freeze_reference(frozen['reference'], manifest, sources)
    if expected != frozen:
        raise ValueError('Frozen reference format differs from the supported policy.')
    return ReferenceDraft.model_validate(frozen['reference'])


def comparison_form(frozen, manifest, sources, items):
    reference = load_reference(frozen, manifest, sources)
    annotations = ReviewAnnotations(packet_id=manifest['packet_id'], reference_id=frozen['reference_id'],
        items=[ItemJudgment(item_id=i['item_id']) for i in items],
        coverage=[CoverageJudgment(fact_id=f.id) for function in reference.functions for f in function.facts if f.required])
    return dict(packet_id=manifest['packet_id'], reference_id=frozen['reference_id'], candidate_items=items), annotations.model_dump(mode='json')


def score_review(frozen, annotations, manifest, sources, items):
    reference = load_reference(frozen, manifest, sources)
    annotations = ReviewAnnotations.model_validate(annotations)
    if annotations.packet_id != manifest['packet_id'] or annotations.reference_id != frozen['reference_id']:
        raise ValueError('Annotations belong to a different packet or frozen reference.')
    item_map = {i['item_id']: i for i in items}
    fact_map = {f.id: (function.function_id, f) for function in reference.functions for f in function.facts}
    required = {k for k, (_, f) in fact_map.items() if f.required}
    annotated_ids = [a.item_id for a in annotations.items]
    coverage_ids = [a.fact_id for a in annotations.coverage]
    if len(annotated_ids) != len(set(annotated_ids)) or set(annotated_ids) != set(item_map):
        raise ValueError('Annotations must include every candidate item exactly once; denominator cannot shrink.')
    if len(coverage_ids) != len(set(coverage_ids)) or set(coverage_ids) != required:
        raise ValueError('Coverage must include every required reference fact exactly once.')
    filled = any(a.verdict != 'unreviewed' for a in annotations.items+annotations.coverage)
    if filled:
        human_declaration(annotations.reviewer)
    for judgment in annotations.items:
        if judgment.verdict != 'unreviewed' and (not judgment.rationale or not judgment.reference_fact_ids):
            raise ValueError('Each reviewed candidate needs a rationale and reference fact links.')
        for fact_id in judgment.reference_fact_ids:
            if fact_id not in fact_map or fact_map[fact_id][0] != item_map[judgment.item_id]['function_id']:
                raise ValueError('Candidate reference links must point to facts for the same function.')
    judgments = {j.item_id: j for j in annotations.items}
    for coverage in annotations.coverage:
        if coverage.verdict != 'unreviewed' and not coverage.rationale:
            raise ValueError('Each reviewed coverage decision needs a rationale.')
        if coverage.verdict == 'covered' and not coverage.candidate_item_ids:
            raise ValueError('Covered facts require candidate item links.')
        if coverage.verdict == 'missing' and coverage.candidate_item_ids:
            raise ValueError('Missing facts cannot also claim candidate coverage.')
        for item_id in coverage.candidate_item_ids:
            if item_id not in item_map or item_map[item_id]['function_id'] != fact_map[coverage.fact_id][0]:
                raise ValueError('Coverage links must point to candidates for the same function.')
            if coverage.verdict == 'covered' and (judgments[item_id].verdict != 'supported' or
                                                coverage.fact_id not in judgments[item_id].reference_fact_ids):
                raise ValueError('Covered facts must link back to supported candidate judgments.')
    counts = {k: sum(a.verdict == k for a in annotations.items)
              for k in ['unreviewed', 'supported', 'contradicted', 'unsupported', 'uncertain']}
    coverage_counts = {k: sum(a.verdict == k for a in annotations.coverage)
                       for k in ['unreviewed', 'covered', 'missing', 'uncertain']}
    status = ('awaiting_annotation' if counts['unreviewed'] or coverage_counts['unreviewed'] else
              'needs_adjudication' if counts['uncertain'] or coverage_counts['uncertain'] else 'annotation_complete')
    metrics = None
    if status == 'annotation_complete':
        n = len(items)
        metrics = dict(field_accuracy=counts['supported']/n, unsupported_inference_rate=counts['unsupported']/n,
                       contradiction_rate=counts['contradicted']/n, field_completeness=coverage_counts['covered']/len(required))
    return dict(policy=POLICY, packet_id=manifest['packet_id'], reference_id=frozen['reference_id'],
                status=status, item_count=len(items), required_fact_count=len(required), counts=counts,
                coverage_counts=coverage_counts, annotation_completion=1-counts['unreviewed']/len(items),
                coverage_completion=1-coverage_counts['unreviewed']/len(required), metrics=metrics,
                reference_reviewer=reference.reviewer.model_dump(), annotation_reviewer=annotations.reviewer.model_dump(),
                annotations_sha256=checksum(annotations.model_dump(mode='json')),
                scope='Human-declared reference comparison; completeness is relative to frozen required facts. No runtime or scientific validity certification.',
                independent_identity_authenticated=False, changes_database_trust=False)


def pending_status(manifest):
    return dict(policy=POLICY, packet_id=manifest['packet_id'], snapshot_id=manifest['snapshot']['snapshot_id'],
                function_count=manifest['function_count'], item_count=manifest['item_count'],
                status='awaiting_independent_reference', metrics=None, independent_human_review_complete=False,
                reason='Source material and empty templates are prepared; no frozen independent reference was supplied to this report.')


def main(argv=None):
    parser = argparse.ArgumentParser(description='Source-first independent human reference workflow')
    commands = parser.add_subparsers(dest='command', required=True)
    for command in ['prepare', 'freeze', 'form', 'score', 'status']:
        sub = commands.add_parser(command)
        sub.add_argument('--db', type=Path, default=Path('database/knowledge.sqlite3'))
        sub.add_argument('--packet', type=Path, default=Path('evaluation/review/cran-v04'))
        if command in {'freeze', 'form', 'score'}:
            sub.add_argument('--reference', type=Path, required=True,
                             help='Filled draft for freeze; frozen reference for form/score')
        if command == 'score':
            sub.add_argument('--annotations', type=Path, required=True)
        if command == 'status':
            sub.add_argument('--reference', type=Path)
            sub.add_argument('--annotations', type=Path)
        if command in {'freeze', 'form', 'score', 'status'}:
            sub.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        db = KnowledgeDatabase(args.db, create=False)
        if args.command == 'prepare':
            manifest = prepare(db, args.packet)
            result = pending_status(manifest)
        else:
            manifest, sources, items = load_packet(db, args.packet)
            if args.command == 'freeze':
                result = freeze_reference(read_json(args.reference), manifest, sources)
            elif args.command == 'form':
                candidates, annotations = comparison_form(read_json(args.reference), manifest, sources, items)
                write_new(args.out/'candidates.json', json_text(candidates))
                write_new(args.out/'annotations.template.json', json_text(annotations))
                result = dict(status='awaiting_annotation', packet_id=manifest['packet_id'], item_count=len(items))
            elif args.command == 'score':
                result = score_review(read_json(args.reference), read_json(args.annotations), manifest, sources, items)
            else:
                if args.annotations and not args.reference:
                    raise ValueError('Status with annotations also requires a frozen reference.')
                if args.reference:
                    frozen = read_json(args.reference)
                    annotations = (read_json(args.annotations) if args.annotations else
                                   comparison_form(frozen, manifest, sources, items)[1])
                    result = score_review(frozen, annotations, manifest, sources, items)
                else:
                    result = pending_status(manifest)
            if args.command != 'form':
                write_new(args.out, json_text(result))
        print(json.dumps({k:v for k,v in result.items() if k not in {'reference', 'snapshot'}}, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f'stat-agent kb review: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
