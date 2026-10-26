"""Reproduce the Codex source audit against hash-locked local CRAN documents (no LLM calls)."""
import copy
import argparse
import json
from pathlib import Path

from stat_agent.cran import collect_locked
from stat_agent.cran_rules import make_rules, source_span
from stat_agent.kb_store import KnowledgeDatabase

AUDIT_VERSION = 'codex-cran-source-audit-1'
APPROVED_REVISIONS = {
    'MASS::lda': 'cd7e0e24b80a623113e9251c15b5cf94316cc44f2dfcda8b984bdd57152fcf01',
    'MASS::lm.ridge': '531aa23cbb48846084c7768a0a3536f9233e8529c855afedd1ef4df1e27c4ec1',
    'MASS::qda': '4e4f1b4e77ebf85c5b1e359acf60905a4f36da0a3f5317b2752e1b7ca00bdac0',
    'cluster::agnes': 'a270a1ad1a30e23bfb6cf8e9b28b35e1f1debd209aa7017aecf4fbc055bfb62a',
    'cluster::clara': 'd1fd90818704a9643c0878ad50c210d70c189054005ec5ec6b57f36346512ff1',
    'cluster::diana': 'f26327a7d6970c03ea92ed535fb5eb3749780ebca9dea991cbf4666d3df180c8',
    'cluster::pam': 'db3589d99baed8a32dcfef47c06df3d2cce8804b124dbabbfbc5b037758a00c9',
    'psych::principal': '813e43d235e0d26c3bb71936986a9b69a3dff11379477401c2c1518a42bb015b',
}


def audit_record(original):
    KnowledgeDatabase.validate_record(original)
    identity = original['metadata']['function_id']
    audited = original.get('source_audit', {})
    revision = audited.get('original_revision') if audited else original['revision']
    if APPROVED_REVISIONS.get(identity) != revision:
        raise ValueError('This profile revision needs a new source audit; approved edits cannot be reused.')
    if original.get('source_audit', {}).get('version') == AUDIT_VERSION:
        return original
    record = copy.deepcopy(original)
    record.pop('revision', None)
    semantic = record['semantic']
    name = record['metadata']['function_name']
    decisions = []

    def change(index, statement=None, category=None, reason='', extra=None):
        claim = semantic['claims'][index]
        if statement:
            claim['statement'] = statement
        if category:
            claim['category'] = category
        if extra and extra not in claim['evidence']:
            claim['evidence'].append(extra)
        decisions.append(dict(location=f'claims[{index}]', decision='corrected', reason=reason))

    def note(location, decision, reason):
        decisions.append(dict(location=location, decision=decision, reason=reason))

    if name == 'lda':
        semantic['suitability_text'] = '用于以分组因子为响应、非因子变量为判别变量的线性判别分析。支持公式或矩阵加分组因子。常规拟合返回 lda 对象；CV=TRUE 时返回留一交叉验证的类别与后验概率，常规预测需 predict.lda。支持先验概率、估计方法和缺失值策略；组内方差过小会报错。'
        note('suitability_text', 'corrected', '区分常规拟合对象和 CV=TRUE 的类别/后验概率输出。')
        change(8, category='parameter', reason='prior 影响分类和旋转属于参数行为，并非分布假设。')
    elif name == 'lm.ridge':
        change(2, statement='lambda 可为标量或向量，表示一个或多个岭常数；默认 lambda=0。',
               extra=source_span(record, 'usage', 'lambda = 0'), reason='补入 usage 明确提供的默认值。')
        change(5, category='parameter', reason='截距不惩罚是算法参数行为，不能当作统计假设。')
        semantic['unknowns'][-1] = 'lambda 默认值为 0；文档提供 GCV、HKB、L-W 等信息，但不能据此确定某个用户数据集的合适 lambda 或预测表现。'
        note('unknowns[2]', 'corrected', '删除“默认值未知（默认0）”自相矛盾表述，不否认文档中的选择辅助信息。')
    elif name == 'qda':
        change(7, statement='非 CV 拟合返回 qda 对象，包含 prior、means、scaling、ldet、lev 和 call 等；CV=TRUE 的类别与后验概率输出另见对应说明。',
               reason='为普通拟合对象补上非 CV 的前提，避免与留一交叉验证混淆。')
    elif name == 'agnes':
        note('prior_review.issues[0]', 'false_positive', '原文明确称 flexible 为 weighted 的推广；weighted 是 flexible 的特例，二者不矛盾。')
        change(7, statement=semantic['claims'][7]['statement']+' method="gaverage" 且未指定 par.method 时，默认值为 -0.1。',
               extra=source_span(record, 'details', 'if par.method is not specified, a default value of -0.1 is used'),
               reason='补全有助于使用的默认参数信息；此前省略并非与原文矛盾。')
    elif name == 'clara':
        change(6, category='parameter', statement='当簇数 k 较小，且变量数 p、抽样大小 j=sampsize 与抽样次数 N=samples 固定时，时间与存储随 n 线性增长；存储约 O(n*p)+O(j^2)，CPU 时间约 O(n*p*j^2*N)。',
               extra=source_span(record, 'note', 'The storage requirement of clara computation (for small k )'),
               reason='确认旧复核指出的实质遗漏，补上小 k 和固定维度的复杂度前提。')
        change(8, statement='数据存在 NA 时，除非用户显式指定 correct.d，否则会发出警告；默认 correct.d=TRUE，控制是否使用正确的距离计算。',
               reason='警告取决于是否显式提供参数，原说明已含此条件；调整语序消除歧义。')
        note('prior_review.issues[0]', 'false_positive', '旧复核一边承认该描述与原文一致、一边判为错误；不是实质错误，现进一步澄清。')
    elif name == 'diana':
        semantic['suitability_text'] = semantic['suitability_text'].replace('由 daisy/dist 生成', '通常由 daisy/dist 生成')
        note('suitability_text', 'clarified', 'daisy/dist 是距离对象的常见来源，不是独占来源限制。')
        change(10, category='output', reason='data 分量可用性和保存对象大小属于输出行为，不是运行失败条件。')
    elif name == 'pam':
        change(7, statement='通常 medoids=NULL 时使用 build 算法；也可用长度 k、取值在 1:n 的整数向量指定初始中心。medoids="random" 时由 nstart 指定随机启动次数；variant="faster" 会采用随机中心的默认设置。',
               reason='默认 medoids 与 variant/nstart 有条件关系，不能无条件声称总为 NULL。',
               extra=semantic['claims'][8]['evidence'][0])
        semantic['unknowns'][0] = '除文档的 n<=65536 实现上限之外，未确定针对特定用户数据集的样本充分性或适用性；正态性、独立性等推断假设未在此文档建立。'
        note('unknowns[0]', 'corrected', '区分已知实现上限与未知的研究样本充分性。')
    elif name == 'principal':
        change(4, statement='cor 可选 Pearson("cor")、协方差("cov")、tetrachoric("tet")、polychoric("poly")、mixed(mixedCor)；Yuleb 对应 Yulebonett，Yuleq、YuleY 对应相应的 Yule 系数。',
               reason='细化 Yuleb 的具体名称；其余可选相关类型保留。')
        change(9, statement='scores=TRUE 时可返回成分得分。默认 oblique.scores=TRUE 时回归权重基于结构矩阵；设为 FALSE 时基于模式矩阵。',
               extra=source_span(record, 'arguments', 'oblique.scores If TRUE (default), then the component scores are based upon the structure matrix. If FALSE, upon the pattern matrix.'),
               reason='原声明已提结构矩阵，但还需补上 oblique.scores=FALSE 的例外，避免把默认设置当作所有设置。')
        change(11, category='output', reason='旋转后成分的解释边界不是运行失败条件。')
        note('prior_review.issues[2:4]', 'false_positive', '旧复核自行确认 fit/fit.off 释义可接受；Phi 的成分间/因子间术语偏好不构成实质错误。')
    else:
        raise ValueError('Audit has no approved edits for '+name)

    touched = {d['location'] for d in decisions}
    for i in range(len(semantic['claims'])):
        if f'claims[{i}]' not in touched:
            note(f'claims[{i}]', 'confirmed', '已与锁定版本原文及逐条引用核对，保留原声明。')
    record['source_audit'] = dict(version=AUDIT_VERSION, reviewer='codex_source_audit', date='2026-10-25',
        original_revision=original['revision'], source_rd_sha256=record['source']['rd_sha256'],
        original_semantic=original['semantic'], decisions=decisions,
        reviewed_fields=['task_types', 'suitability_text', 'claims', 'unknowns'],
        scope='AI source adjudication; not independent human verification or R runtime validation.')
    record['attempts'].append({'reviewer': 'codex_source_audit', 'draft': copy.deepcopy(semantic),
        'review': {'accepted': True, 'issues': [], 'explanation': '已按锁定官方源码逐项核对，修订真实遗漏并裁决复核误报；详细理由见 source_audit。'}})
    record['status'] = 'machine_checked'
    # Same extraction inputs; the audit changes the revision, not the cache key.
    # A normal build can therefore reuse the latest audited profile.
    record['retrieval_text'] = '\n'.join([record['metadata']['function_id'], ' '.join(semantic['task_types']),
        semantic['suitability_text'], *[c['category']+': '+c['statement'] for c in semantic['claims']]])
    record['rules'] = make_rules(record)
    return KnowledgeDatabase.validate_record(record)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, default=Path('database/cran_profiles.json'))
    args = parser.parse_args()
    path = Path('database/cran_profiles.json')
    bundle = json.loads(args.input.read_text(encoding='utf-8'))
    documents = {d['function_id']: d for d in collect_locked('configs/cran_sources.lock.json', '.cache/cran')}
    for record in bundle['profiles']:
        if record['source'] != documents[record['metadata']['function_id']]:
            raise ValueError('Saved document differs from the locked source.')
    records = [audit_record(r) for r in bundle['profiles']]
    db = KnowledgeDatabase('database/knowledge.sqlite3')
    # Preserve the original snapshot and records in SQLite before publishing a new immutable snapshot.
    db.restore(args.input)
    records = [db.save_profile(r) for r in records]
    snapshot = db.publish(records, bundle['snapshot']['source_lock_sha256'])
    db.export(path)
    report = dict(audit_version=AUDIT_VERSION, reviewer='codex_source_audit', snapshot=snapshot,
        source_documents_verified=len(documents), machine_checked=len(records), needs_review=0,
        claims_reviewed=sum(len(r['semantic']['claims']) for r in records),
        rules=sum(len(r['rules']['rules']) for r in records),
        functions=[dict(function_id=r['metadata']['function_id'], original_revision=r['source_audit']['original_revision'],
            revision=r['revision'], decisions=r['source_audit']['decisions'], rules=len(r['rules']['rules'])) for r in records],
        runtime_verified=False, human_verified=False)
    Path('evaluation/results/cran_source_audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in {'functions','snapshot'}}, ensure_ascii=False))


if __name__ == '__main__':
    main()
