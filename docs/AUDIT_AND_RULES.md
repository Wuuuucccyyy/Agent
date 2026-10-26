# v0.4 来源复核与数据条件检索

完成日期：2026-10-26。对应本轮约定的第一步（首批画像复核）和第二步（适用条件规则化）。

## 来源复核

对 MASS 7.3-66、cluster 2.1.8.3、psych 2.6.9 的 8 个函数、85 条声明逐项核对。缓存源码先校验包 SHA256，再重新解析 Rd，与画像保存的来源逐项比较。复核者标记为 `codex_source_audit`，不是独立人工审核，也没有执行 R。

| 函数 | 主要处理 |
|---|---|
| MASS::lda | 区分拟合对象与 CV 输出；将 prior 行为归为参数 |
| MASS::lm.ridge | 修正“默认 lambda 未知”的矛盾，明确默认 0；截距惩罚归为参数行为 |
| MASS::qda | 明确普通拟合输出的非 CV 前提 |
| cluster::agnes | 驳回 flexible 与 weighted 关系的误报；补充 gaverage 默认参数 |
| cluster::clara | 补齐“小 k”等复杂度前提，澄清 correct.d 警告触发条件 |
| cluster::diana | 距离对象来源不是仅限 daisy/dist；输出行为重新分类 |
| cluster::pam | 说明 medoids 默认值受 variant 等设置影响；区分实现上限和样本充分性 |
| psych::principal | 明确 Yuleb 名称及 oblique.scores=FALSE 的例外；裁决复核中的术语误报 |

8 条现均为 `machine_checked`，默认可参与候选检索。`semantic_verification=llm_inference_not_human_verified`、`runtime_verified=false` 保留。每条记录保存原始语义、原版本、旧模型尝试及本次逐项裁决。不能以通过数量推断独立质量水平。

复核记录：[cran_source_audit.json](../evaluation/results/cran_source_audit.json)。可读目录：[cran_profiles.md](../database/cran_profiles.md)。在相同源码缓存下运行 `python scripts/audit_cran_profiles.py` 可复现发布，已复核记录不会重复追加审核。

## 可计算条件

新增 `RuleSet` Schema 和 66 条规则，包含适用分支、硬条件或提示条件、比较字段、原文引文及来源/语义哈希。规则由显式维护的映射生成；不执行文档或 LLM 生成的 Python 表达式。来源、语义或引用不匹配时拒绝恢复或使用规则。

每条条件返回：

- `satisfied`：现有事实满足该项已实现条件。
- `violated`：现有事实与该项条件冲突。
- `unknown`：缺参数、变量角色、观测证据，或该分支无法确定。`applicable=false` 表示分支未启用，不参加总判定。

总结果只在硬条件明确违反时排除候选。提示条件违反时总状态为未知，并保留具体提示。先检查全体候选，再取合格候选的 Top-K；结果同时返回排除项、观察值、预期值和引文。全部必要条件满足，也不代表推断假设成立或允许执行。

典型规则包括 PAM 的每对观测共同非缺失变量、k<n 和 n<=65536；CLARA 的 k 与 sampsize 范围；QDA 的每组 n_g>p 必要秩界；PCA 成分数与矩阵输入契约。QDA 的 NumPy 数值秩只作提示，因为它与 R QR 容差不同。LDA 非零组内方差也不能替代完整的 tol 检查。

`DataProfile` 升至 0.3.0，新增 `applicability` 观测块，记录所选列、分组角色、缺失重叠、组大小、组内秩和矩阵形状等。旧画像仍可读；缺少这些事实时返回未知。切换变量或分组角色后不会复用不匹配的事实。最多检查 512 种缺失模式的两两重叠，超过时记为未知并说明资源边界。

## 使用

```powershell
python -m stat_agent kb restore
python -m stat_agent kb search --goal "聚类" --task clustering --input examples/data/pca.csv --predictors x1 x2 x3 --parameters configs/cran_parameters.example.json --out runs/conditions-search.json
python evaluation/cran_conditions.py
```

参数文件按函数名指定参数，也可用 `"*"` 提供共有值，函数级值覆盖共有值。例如距离矩阵用 `{"*":{"input_kind":"dissimilarity"},"cluster::pam":{"k":2}}`。支持 `input_kind`、`k`、`nfactors`、`sampsize`、`metric`、`method`、`na_action`；其他字段拒绝，整数不接受布尔值或字符串。

默认 `input_kind=observations`。相关/协方差矩阵、完整不相似度矩阵、单列压缩距离向量必须显式声明；方阵不会自动被识别为相关矩阵。完整距离矩阵契约检查方阵、对称、零对角和非负；仅下三角编码需要先转换。输入参数用于条件检查，不会触发实际函数调用。

## 验证与边界

- 全量自动测试：105 通过，其中新增 16 项条件、来源绑定、未知状态、CLI、恢复和缓存回归测试。
- [条件诊断](../evaluation/results/cran_conditions.json)：12/12，覆盖 8 个函数的满足、不满足与未知情况。
- [词法检索](../evaluation/results/cran_search_audited_lexical.json)：8 个开发查询，Top-1 为 6/8，Hit@3 为 8/8。
- [固定本地 e5 语义检索](../evaluation/results/cran_search_audited_semantic.json)：8 个开发查询，Top-1 和 Hit@3 均 8/8；8 个向量全部复用。开发查询及合成条件例都不是独立金标准。
- [恢复后构建复用](../evaluation/results/cran_audited_resume.json)：8/8 画像命中缓存，零 API 调用，快照不变。

原始 v0.3 构建和检索报告保持为历史记录。普通建库继续复用同一提取指纹的最新复核版本；显式刷新或更换来源/提取配置将生成新草稿，不能自动继承本次规则核验。复核脚本锁定这 8 个已审查原始画像的版本哈希；新版本必须重新审查，不能套用旧裁决。

本轮没有补齐所有 R 参数、正半定性检查、分布/研究设计假设或 R 运行验证；未实现项明确列在各规则集的 `coverage_notes` 与画像 `unknowns`。没有自动插补、删行或类别编码。独立专家参考集及更多 CRAN 函数仍是后续工作。
