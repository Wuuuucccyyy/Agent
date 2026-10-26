"""Reviewed rules for the eight locked CRAN seed functions, never inferred from an LLM at runtime."""
from .kb_rules import RuleSet
from .kb_store import checksum


def source_span(record, section, text):
    source = record['source']['sections'][section]
    if text not in source:
        raise ValueError(f'Missing source evidence for {record["metadata"]["function_id"]}: {text}')
    return {'section': section, 'quote': text}


def make_rules(record):
    name = record['metadata']['function_name']
    source = record['source']['sections']
    rules, defaults = [], {}
    notes = ['只检查已实现的必要条件；满足这些条件不等于统计适用性成立，也不授权执行。',
             '没有观测到的研究设计、独立性、分布假设和参数条件保留未知；不根据边缘分布替代多元假设检验。',
             '输入形式必须声明；默认按观测表处理，不根据方阵形状猜测相关矩阵。没有自动删行、插补或类别编码。']

    def pred(fact, op, value=None, other=None):
        return dict(fact=fact, op=op, **({'other_fact': other} if other else {'value': value}))

    def ev(section, text):
        return source_span(record, section, text)

    def claim(i):
        return record['semantic']['claims'][i]['evidence']

    def add(id, text, conditions, evidence, *, when=None, origin='official_document', derivation='', severity='hard'):
        rules.append(dict(id=id, description=text, conditions=conditions, evidence=evidence,
                          when=when or [], origin=origin, derivation=derivation, severity=severity))

    obs = [pred('input.kind', 'eq', 'observations')]
    distance = [pred('input.kind', 'in', ['dissimilarity', 'dissimilarity_condensed'])]
    matrix = [pred('input.kind', 'eq', 'dissimilarity')]
    task = record['semantic']['task_types']
    add('task_match', '用户任务类型须落在该函数画像覆盖的任务范围内；未确定任务时未知。',
        [pred('task.type', 'in', task)], [ev('description', source['description'][:min(350, len(source['description']))])],
        origin='derived', derivation='将显式指定并由 Codex 对原文核对的任务标签用作本检索流程的范围约束，非 R 函数运行参数。')
    kinds = ['observations']
    if name in {'agnes', 'diana', 'pam'}:
        kinds += ['dissimilarity', 'dissimilarity_condensed']
    if name == 'principal':
        kinds += ['correlation', 'covariance']
    add('input_kind', '声明的输入形式须在当前画像支持范围内。', [pred('input.kind', 'in', kinds)],
        [ev('arguments', source['arguments'][:350])], origin='input_contract',
        derivation='将官方输入形式映射到工作流的显式输入标签；暂不支持其他适配器。')
    add('nonempty_features', '至少提供一列待分析变量。', [pred('features.count', 'gt', 0)], claim(0),
        origin='input_contract', derivation='当前表格画像适配器要求非空分析列。')

    if name in {'agnes', 'diana', 'pam', 'clara', 'lda', 'qda'}:
        fact = 'features.numeric' if name in {'agnes', 'diana'} else 'features.numeric_or_boolean'
        add('feature_types', '所选分析列须为数值类型'+('（允许逻辑类型）' if fact.endswith('boolean') else '')+'。',
            [pred(fact, 'eq', True)], claim(1 if name in {'agnes', 'clara'} else 0), when=obs,
            origin='input_contract' if name in {'lda', 'qda'} else 'official_document',
            derivation='当前判别分析适配器使用直接数值矩阵，不进行公式展开或类别编码。' if name in {'lda', 'qda'} else '')

    if name in {'agnes', 'diana', 'pam', 'clara'}:
        defaults['metric'] = 'euclidean'
        metrics = ['euclidean', 'manhattan'] + (['jaccard'] if name == 'clara' else [])
        # The full allowed-list quotation is selected directly, avoiding reliance on claim ordering.
        start = source['arguments'].index('The currently available options')
        quote = source['arguments'][start:source['arguments'].index('.', start)+1]
        add('metric', '原始观测输入的距离度量须为官方支持的取值。', [pred('param.metric', 'in', metrics)],
            [ev('arguments', quote)], when=obs)
        notes.append('距离输入时不检查 metric；stand、初始化、随机种子及其他未建模参数需后续核查。')

    if name in {'agnes', 'diana', 'pam'}:
        missing = 'Missing values ( NA s) are not allowed.' if name == 'pam' else 'Missing values (NAs) are not allowed.'
        add('distance_missing', '不相似度输入不得包含缺失值。', [pred('features.missing', 'eq', 0)],
            [ev('arguments', missing)], when=distance)
        add('distance_matrix', '声明为完整不相似度矩阵时须方阵、对称、零对角线且非负。',
            [pred('matrix.'+f, 'eq', True) for f in ['square', 'symmetric', 'diagonal_zero', 'nonnegative']],
            claim(1 if name == 'pam' else 0), when=matrix, origin='input_contract',
            derivation='采用完整距离矩阵的规范化输入契约；R 对象或仅下三角编码应先显式转换，不能当作完整矩阵传入。')
        add('distance_vector', '压缩不相似度向量须为单列且长度等于 n(n-1)/2。',
            [pred('matrix.condensed_valid', 'eq', True)],
            [ev('arguments', 'n*(n-1)/2')], when=[pred('input.kind', 'eq', 'dissimilarity_condensed')])

    if name in {'pam', 'clara'}:
        evidence = claim(3 if name == 'pam' else 2)
        add('cluster_count', '簇数 k 须为正整数且小于观测数；未提供 k 时未知。',
            [pred('param.k', 'gt', 0), pred('param.k', 'lt', other='data.n')], evidence)
    if name == 'pam':
        add('pairwise_overlap', '每对观测必须至少共享一个非缺失变量。',
            [pred('features.pairwise_overlap', 'eq', True)], claim(2), when=obs)
        add('sample_cap', '当前锁定版本的观测数不能超过 65536。', [pred('data.n', 'le', 65536)], claim(10))
    if name == 'clara':
        add('sample_size', '抽样大小须大于 k 且不超过 n；未指定时按 min(n,40+2k) 计算。',
            [pred('param.sampsize', 'gt', other='param.k'), pred('param.sampsize', 'le', other='data.n')], claim(5))
        notes.append('缺失值被允许；correct.d 警告与抽样得到的实际可用数据仍需 R 运行核查。')
    if name == 'agnes':
        defaults['method'] = 'average'
        add('linkage', '聚合方法须为官方列出的七种方法之一。',
            [pred('param.method', 'in', ['average', 'single', 'complete', 'ward', 'weighted', 'flexible', 'gaverage'])], claim(6))
        notes.append('flexible/gaverage 的 par.method 数学取值范围未自动化；不得把清洗后的公式文本直接编译成规则。')

    if name in {'lda', 'qda'}:
        defaults.update(na_action='fail', method='moment')
        add('group_role', '必须明确提供一个分组变量；未声明时未知。', [pred('groups.provided', 'eq', True)], claim(1))
        add('group_labels', '分组标签不能缺失。', [pred('groups.no_missing', 'eq', True)], claim(1),
            when=[pred('param.na_action', 'eq', 'fail')], origin='input_contract', derivation='本流程要求每条训练观测具有已知类别。')
        add('missing_fail', 'na.action=fail 时，判别变量不得含缺失值。', [pred('features.missing', 'eq', 0)],
            [ev('arguments', 'The default action is for the procedure to fail.')], when=[pred('param.na_action', 'eq', 'fail')])
        add('preprocessing_observed', '只有完整有限数据才具备当前规则需要的预处理完成证据；声明 na.omit 不等于已删行。',
            [pred('processing.complete', 'eq', True)], claim(1), origin='input_contract',
            derivation='本步骤不执行预处理；缺失或无限值存在时保留未知。')
        methods = ['moment', 'mle', 't'] + (['mve'] if name == 'lda' else [])
        parameter = next(p['description'] for p in record['metadata']['parameters'] if p['name'] == 'method')
        add('estimation_method', '估计方法须为当前文档列出的取值。', [pred('param.method', 'in', methods)],
            [ev('arguments', parameter[:400])])
        if name == 'qda':
            evidence = [ev('details', 'Uses a QR decomposition which will give an error message if the within-group variance is singular for any group.')]
            add('group_size_rank_bound', '每组样本数必须严格大于判别变量数，这是组内协方差满秩的必要条件。',
                [pred('groups.min_size', 'gt', other='features.count')], evidence, origin='derived',
                derivation='组内中心化矩阵秩至多为 n_g-1；若 n_g<=p，p 维组内协方差必奇异。通过此界不保证满秩。')
            add('observed_group_rank', 'NumPy 检查各组中心化矩阵是否列满秩；仅作数值诊断。',
                [pred('groups.full_rank', 'eq', True)], evidence, origin='derived', severity='advisory',
                derivation='NumPy SVD 与 R QR 的容差和计算路径不同，因此数值秩诊断不单独触发硬排除。')
        else:
            add('within_group_variance', '判别变量的合并组内方差须非零。',
                [pred('groups.within_variance_nonzero', 'eq', True)], claim(6), origin='derived',
                derivation='组内方差为零必低于正 tol 的平方；这里只检查必要的非零条件，不声称完成实际 tol 或线性组合检查。')
        notes.append('暂未建模 prior、tol、nu、CV 等参数；留一交叉验证对训练子集的条件未检查。')
    if name == 'lm.ridge':
        add('response_role', '岭回归须明确一个数值响应变量；未声明时未知。',
            [pred('response.provided', 'eq', True), pred('response.numeric', 'eq', True)], claim(0),
            origin='derived', derivation='线性回归的响应角色映射到本流程的数值目标列；不限制可由公式编码的因子预测变量。')
        notes.append('lambda 默认 0；尚未计算公式设计矩阵、lambda=0 的秩条件、因子对比或 GCV 调参，不据此承诺可运行。')
    if name == 'principal':
        defaults['nfactors'] = 1
        add('component_count', '成分数须为正整数且不能超过输入变量数；默认 1。',
            [pred('param.nfactors', 'gt', 0), pred('param.nfactors', 'le', other='features.count')],
            claim(2)+[ev('usage', 'nfactors = 1')], origin='derived',
            derivation='p 维矩阵至多有 p 个特征向量；整数类型由受约束参数模式验证。')
        add('pca_matrix', '声明为相关或协方差矩阵时须方阵且对称。',
            [pred('matrix.square', 'eq', True), pred('matrix.symmetric', 'eq', True)], claim(0),
            when=[pred('input.kind', 'in', ['correlation', 'covariance'])], origin='input_contract',
            derivation='完整相关/协方差矩阵的基础输入契约；没有替代正半定性或缺失数据处理。')
        add('correlation_matrix', '相关矩阵的对角线须为 1，元素绝对值不超过 1。',
            [pred('matrix.diagonal_one', 'eq', True), pred('matrix.correlation_bounds', 'eq', True)], claim(0),
            when=[pred('input.kind', 'eq', 'correlation')], origin='input_contract',
            derivation='相关矩阵的必要定义条件；使用画像中公开的数值容差。')
        notes.append('cor/covar、旋转、scores、missing、oblique.scores 等未建模；不对所有相关系数选项统一施加数值列限制。')
    result = dict(function_id=record['metadata']['function_id'], source_rd_sha256=record['source']['rd_sha256'],
                  semantic_sha256=checksum(record['semantic']), defaults=defaults, rules=rules, coverage_notes=notes)
    return RuleSet.model_validate(result).model_dump(mode='json')
