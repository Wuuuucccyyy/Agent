"""Small source-library search acceptance; labels are development checks, not a research benchmark."""
import argparse
import json
from pathlib import Path

from stat_agent.kb_store import KnowledgeDatabase
from stat_agent.retrieval import LexicalEncoder, pinned_encoder

CASES = [
    ('MASS::lda', '使用线性判别分析，根据数值解释变量预测类别分组'),
    ('MASS::qda', '对具有类别标签的数值观测进行二次判别分析'),
    ('MASS::lm.ridge', '对回归模型使用岭常数 lambda，拟合岭回归并比较 GCV'),
    ('cluster::pam', '采用围绕中心对象 medoid 的划分聚类，输入距离或观测矩阵'),
    ('cluster::clara', '对大型观测数据通过重复抽样执行中心对象聚类'),
    ('cluster::agnes', '对观测或相异度数据做凝聚型层次聚类'),
    ('cluster::diana', '对观测或相异度数据做分裂型层次聚类'),
    ('psych::principal', '对相关矩阵或原始变量做主成分分析，支持旋转与成分得分'),
]


def evaluate(database, encoder):
    active = {r['metadata']['function_id'] for r in database.records()}
    rows = []
    for expected, query in CASES:
        candidates = database.search(query, encoder, 3)
        ids = [c['function_id'] for c in candidates]
        rows.append({'query': query, 'expected': expected, 'expected_is_searchable': expected in active,
                     'top1_correct': bool(ids and ids[0] == expected), 'hit_at_3': expected in ids,
                     'ranking': [{'id': c['function_id'], 'cosine': c['cosine']} for c in candidates]})
    return {'scope': 'Eight developer-authored source-library acceptance queries; not independent annotation.',
            'snapshot_id': database.snapshot()['snapshot_id'], 'encoder': encoder.name,
            'total_cases': len(rows), 'searchable_profiles': len(active),
            'top1_accuracy_all_cases': sum(r['top1_correct'] for r in rows)/len(rows),
            'hit_at_3_all_cases': sum(r['hit_at_3'] for r in rows)/len(rows), 'cases': rows,
            'model_metadata': getattr(encoder, 'model_metadata', None),
            'limitations': ['Unreviewed candidates are not silently removed from the evaluation denominator.',
                           'No statistical compatibility or code execution is validated by these queries.']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', type=Path, default=Path('database/knowledge.sqlite3'))
    parser.add_argument('--embedding-config', type=Path)
    parser.add_argument('--out', type=Path, default=Path('evaluation/results/cran_search_lexical.json'))
    args = parser.parse_args()
    database = KnowledgeDatabase(args.db, create=False)
    encoder = pinned_encoder(args.embedding_config) if args.embedding_config else LexicalEncoder()
    result = evaluate(database, encoder)
    if args.embedding_config:
        result['index_reuse_check'] = database.index(encoder)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in {'cases','model_metadata'}}, ensure_ascii=False))
