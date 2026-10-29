# v0.5 独立参考与画像质量评估入口

日期：2026-10-28。对应工作手册第 8.1 节：先建立人工审核参考，再比较画像质量。当前已完成材料、Schema、导入校验和评分工具；**独立人工参考尚未填写，质量指标为空**。

## 交付材料与覆盖范围

第一阶段材料在 [evaluation/review/cran-v04](../evaluation/review/cran-v04/README.md)。`cran-v04` 指待评估的 v0.4 数据库快照，工具版本为 v0.5。

- `sources.json`：8 个函数锁定版本官方文档的静态清洗文本、函数接口和来源信息，不含模型摘要、模型结论或旧复核意见。
- `reference.template.json`：空白参考答案。复核人、独立性声明、事实清单均未填写。
- `manifest.json`：来源、数据库快照和候选内容哈希，固定后续评估范围。
- [当前状态报告](../evaluation/results/cran_independent_review_status.json)：`awaiting_independent_reference`，`metrics=null`。

候选对照范围共 199 个单元：85 条声明、66 条规则、8 项规则配置、8 段适用摘要、8 项任务类型和 24 条未知说明。待复核画像也纳入范围，不允许为提高分数移除困难条目。

静态清洗文本不是完整 Rd 的独立转录；复杂公式可能丢失排版信息。涉及公式或源码细节时，复核者应按 source_url、rd_path 和哈希回溯官方源码包；当前材料不足以建立的结论应保留未知，补充来源后再形成新版本参考。

## 第一阶段：只看来源，编写参考

复核者应未参与候选画像生成，先阅读材料中的官方来源，再在模板副本中独立填写参考。不要先阅读本仓库的候选画像、源码中的规则映射或旧模型复核意见。

每个函数显式覆盖七类字段：`task`、`input`、`roles`、`parameters`、`conditions`、`output`、`unknowns`。同一类可以有多个事实；每条事实包含：

| 字段 | 填写要求 |
|---|---|
| `id` | 全库唯一，使用英文字母、数字、下划线或连字符 |
| `statement` | 参考结论，保留条件和例外 |
| `status` | `documented` 原文明示；`derived` 推导；`not_established` 在该来源范围内未建立 |
| `required` | 是否属于完整率所要求覆盖的事实，必须在查看候选之前确定 |
| `evidence` | 原文章节和短引文；documented/derived 必填，程序检查其在对应函数原文中存在 |
| `rationale` | 解释结论、推导或为何未建立，不能把文档没有提到等同于统计上不存在 |

每个函数至少有一个 required 事实，完成后设置 `scope_complete=true`。缺少文档依据的研究设计、分布假设等应保留未知，不为凑齐字段发明条件。

填写真实 `reviewer_id`、`kind=human`、`independent_of_generation=true`、`reviewed_on=YYYY-MM-DD`；仅在符合实际时设置 `authored_from_sources_before_viewing_candidates=true`。AI 或开发测试夹具不能作为独立人工参考导入。

```powershell
python -m stat_agent kb restore
python -m stat_agent kb review prepare --packet evaluation/review/cran-v04
# 将已填写的模板副本保存为 runs/review/reference-filled.json，然后固定内容哈希。
python -m stat_agent kb review freeze --reference runs/review/reference-filled.json --out runs/review/reference-frozen.json
```

这些声明由复核者负责。程序能够校验格式、版本和引用位置，无法鉴别人的身份、验证其实际独立性或证明阅读顺序，不能把格式通过宣传为独立专家认证。

## 第二阶段：候选对照与完整性检查

只有参考通过检查并固定哈希后，工具才生成候选内容及对照表。参考编写者或另一位未参与画像生成的复核者可以进行对照，并分别记录身份。

```powershell
python -m stat_agent kb review form --reference runs/review/reference-frozen.json --out runs/review/comparison
# 阅读 comparison/candidates.json，另存填写后的 annotations.template.json 副本。
python -m stat_agent kb review score --reference runs/review/reference-frozen.json --annotations runs/review/annotations-filled.json --out runs/review/quality-report.json
```

候选每项判为 `supported`、`contradicted`、`unsupported` 或 `uncertain`；未判断保持 `unreviewed`。必须说明理由并关联同一函数的参考事实。复合陈述只有全部关键条件和例外都正确时才能标 supported。原文引用存在并不自动意味着语义正确。

对每个 required 参考事实，另判 `covered`、`missing` 或 `uncertain`。covered 必须指向已标 supported 且反向引用该事实的候选单元；missing 不得同时指定覆盖项。这一步用于发现候选完全没提到的内容，不能只检查已有声明就宣称画像完整。

## 指标与状态

所有候选单元以及所有 required 事实必须完成判断，且没有 uncertain，才生成以下指标：

| 指标 | 计算范围 |
|---|---|
| 字段准确率 | supported / 固定候选单元总数 |
| 无依据推断率 | unsupported / 固定候选单元总数 |
| 矛盾率 | contradicted / 固定候选单元总数 |
| 字段完整率 | covered / 固定参考中的 required 事实总数 |

不同单元等权计数；复合声明不是逐个原子命题计数。完整率仅相对于这份冻结参考，并非整个 R 文档的绝对覆盖率。指标来自人的对照标签，程序不通过中文字符串匹配判断语义真伪。

部分完成时状态为 `awaiting_annotation`，争议未解时为 `needs_adjudication`，两者质量指标均为空，只显示标注进度和计数。`annotation_complete` 仅表示标签完成，低分仍可出现，不等于画像合格、研究设计适用或 R 运行通过。

```powershell
# 未提供参考时只报告材料就绪、参考待填。
python -m stat_agent kb review status --out runs/review/pending.json
# 提供固定参考和标注时，校验并报告这组文件的实际状态。
python -m stat_agent kb review status --reference runs/review/reference-frozen.json --annotations runs/review/annotations-filled.json --out runs/review/current-status.json
```

所有写入均保护已有不同内容的文件；更改结果请使用新文件名。更新数据库后，旧材料仍绑定旧快照，不能挪用到新画像。该流程不修改数据库的 machine_checked、人工核验或 R 执行状态；后续采纳人工修订需要单独形成可追溯的新画像版本。

## 验证与下一步

新增测试覆盖空白模板、AI 标签拒绝、引用与版本校验、固定分母、漏标/重复/跨函数关联、争议与部分标注、指标计算、不覆盖人工文件，以及完整 CLI 流程。测试使用明确标注的虚构复核身份，只验证软件，不作为项目参考数据。

本地全量回归结果：**118 passed**，其中新增 13 个复核工作流用例。CI 增加材料生成和待复核状态导出检查，不要求也不伪造人工参考答案。

当前没有接收真实独立人工参考，因此没有开展基于独立参考的单 Agent / 多 Agent 对照，也没有据此扩充 CRAN 或 MANOVA 覆盖。下一项需要真实独立复核者填写参考；材料与工具已经可直接使用。现有 8 个函数、66 条规则及原有检索功能可照常使用。

来源资料沿用对应 CRAN 许可，见 [LICENSE-CRAN-DERIVED.txt](../database/LICENSE-CRAN-DERIVED.txt)。
