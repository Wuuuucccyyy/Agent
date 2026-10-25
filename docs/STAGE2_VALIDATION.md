# v0.2 真实模型与扩展检索验证

交付日期：2026-10-25（America/Los_Angeles）。本轮按工作手册第二、三阶段推进，并用已有第四阶段 PCA/OLS 模板验收完整链路。它是开发验收，不是独立研究结论。

## 已交付

- CC Switch 只读 DeepSeek 适配器：强制结构化工具输出、Schema/角色校验、未知条件保留、有限重试和脱敏回执。
- LLM 官方文档知识草稿提取；所有推断字段为未核验，草稿不自动进入知识库。
- 可选九条知识库：原五条加 princomp、lm.ridge、hclust、qda；默认五条保持兼容。
- 固定本地 multilingual-e5-small，同模型 query/passage 编码、L2 归一化、384 维、文件哈希记录。
- 25 字段画像检查、16 案例扩展检索诊断、仅验证集选 λ，以及两个真实端到端案例。
- TaskProfile schema 0.2.0 新增 requested_method；保留用户指定方法和额外约束，未支持的限制阻止模板执行。

## 本地验证

`python -m pytest -q`：**75 passed**。新增测试覆盖密钥隐藏、只读配置、非法或截断结构化响应、方法/变量冲突、每次运行独立 Token 计数、有限重试、E5 前缀、显式方法过滤、QDA 小组样本约束、用户限制阻止、知识草稿隔离、跨划分数据重复、测试标签不影响 λ 选择，以及画像错误/虚构设计条件的检测。

`python -m compileall -q src evaluation scripts` 和 Schema 导出通过。CI 增加词法扩展诊断与画像检查；CI 不持有用户 API 密钥，也不下载大模型。远端是否成功以对应提交的 GitHub Actions 状态为准。

## DeepSeek 真实调用

用户配置为 `deepseek-v4-pro[1m]`，请求时仅移除 CC Switch 的上下文后缀；服务返回 `deepseek-v4-pro`。使用官方 Anthropic 兼容端点，temperature=0、thinking disabled。该模型名是服务端别名，不能锁定权重；日志明确记录 immutable_model_version=false。

| 留存运行 | 结果 | 请求数 | Token 总数 |
|---|---|---:|---:|
| 六例初次任务验收 | 5/6 | 6 | 6,941 |
| 明确判别分析角色映射后复测 | 6/6 | 6 | 7,185 |
| prcomp 文档草稿提取 | 生成符合 Schema 的未核验草稿 | 1 | 2,922 |
| PCA 完整链路 | success，数值验证通过 | 1 | 1,206 |
| OLS 完整链路 | success，数值验证通过 | 1 | 1,202 |

Token 按服务返回的非缓存输入、缓存输入、输出分别记录后求和；这些留存运行重试均为 0。表格不代表本轮所有开发探测或账户账单，货币成本未估算。请求只含目标、列名与角色；文档提取只发送官方参考摘录。API 密钥和原始表格单元格不进入请求/响应日志或仓库。

首轮失败为判别分析将类别列映射到 target_variables，而系统约定类别列属于 group_variables。修正提示中的角色约定后复测通过；这是针对已观察失败的开发修正，不能当作独立测试准确率。保留 [初次结果](../evaluation/results/deepseek_tasks_initial.json) 和 [复测结果](../evaluation/results/deepseek_tasks.json)。

[完整链路结果](../evaluation/results/live_pipeline.json) 含模型回执、任务画像、检索依据、执行数值、节点耗时与数据哈希；使用仓库合成数据，且用户目标明确指定 prcomp / lm，因此验证的是执行连通性，不是自由方法选择能力。PCA 方差/重构与 OLS 已知系数均通过固定模板的数值校验。

## 本地 Embedding 与检索

模型固定为 `intfloat/multilingual-e5-small`，revision `614241f622f53c4eeff9890bdc4f31cfecc418b3`；配置见 [embedding.json](../configs/embedding.json)。模型本地 CPU 加载，query/passage 前缀遵循模型卡，输出 384 维，模型默认截断长度 512 token。下载九个指定文件并记录 SHA256，模型权重与 tokenizer 留在忽略目录；结果内留存清单，未把模型文件提交 Git。

扩展集为 **8 个验证案例 + 8 个测试案例**，同任务存在替代候选。每个案例固定种子并记录生成数据哈希；禁止跨划分使用相同数据。场景族仍重叠，任务类型/变量角色显式给定，标签由开发者编写、待独立复核；不能称为外部泛化基准。

仅在验证集从 `[0, 0.1, 0.25, 0.5, 1]` 选 λ，目标为 `NDCG@3 + 选择准确率 - 首选硬约束违规率`，并列选择较小值。两种编码器均选 **λ=0**。以下为未用于选参的 8 例测试数据结果；7 个有相关候选案例计入 Recall/MRR/NDCG，全部 8 例计入选择和违规率。

| 编码器/方案 | Recall@3 | MRR | NDCG@3 | 选择/拒绝准确率 | 首选硬约束违规率 |
|---|---:|---:|---:|---:|---:|
| TF-IDF / A 余弦 | 0.9286 | 0.7381 | 0.7630 | 0.5000 | 0.5000 |
| TF-IDF / B 硬过滤 | 1.0000 | 1.0000 | 0.9710 | 1.0000 | 0.0000 |
| TF-IDF / C 验证集 λ | 1.0000 | 1.0000 | 0.9710 | 1.0000 | 0.0000 |
| e5 / A 余弦 | 0.7857 | 0.7109 | 0.6698 | 0.5000 | 0.5000 |
| e5 / B 硬过滤 | 1.0000 | 1.0000 | 0.9710 | 1.0000 | 0.0000 |
| e5 / C 验证集 λ | 1.0000 | 1.0000 | 0.9710 | 1.0000 | 0.0000 |

选择准确率允许首选命中任何正相关候选，NDCG 才区分相关等级；硬约束违规率只统计代码已实现的约束，不等于完整统计适用性。结果表明这个构造集上的硬过滤有用，**未显示软惩罚增益，也未显示 e5 优于词法基线**。应用默认 λ=0.5 仍是历史演示配置；本次实验不自动修改应用参数。

逐案例排名、验证网格和模型清单见 [词法结果](../evaluation/results/expanded_lexical.json) 与 [语义结果](../evaluation/results/expanded_semantic.json)。

## 画像质量与知识核验

对 PCA 合成数据的 25 个预先给定解析事实检查：字段准确率 1.0、完整率 1.0、证据记录覆盖率 1.0、这组字段内的错误确定性断言 0。检查包含均值、样本方差、样本数与明确应为 unknown 的研究设计项。参考事实见 [profile_reference.json](../evaluation/profile_reference.json)，结果见 [profile_quality.json](../evaluation/results/profile_quality.json)。

这仅覆盖一个已知合成画像；证据记录存在不表示证据充分或经过专家审查。人工审核状态为 pending，没有单 Agent/多 Agent 对照，不能据此报告整体画像准确率或总体幻觉率。

知识草稿见 [knowledge_draft.json](../evaluation/results/knowledge_draft.json)，带官方来源哈希和 LLM 推断标记。九条检索库与它分开维护；新增 R 方法尚未实际运行。R-devel 文档是可变来源，正式实验仍需固定 R/包版本与审阅快照。

## 复现与下一步

完整命令在 [README](../README.md)。基础测试和词法评估无需 API；语义评估需要本地模型及 requirements.semantic.lock.txt 中记录的 Windows/Python 3.11 依赖。真实任务/知识/链路脚本需要本机 CC Switch DeepSeek 配置；不把凭据传到 CI。

下一步优先建立独立人工参考与外部数据划分，补齐组内协方差、残差和缺失策略诊断，再增加 R/其他方法执行。独立标注、正式多 Agent 对照、DARE、生成代码隔离与图片/PDF 均未完成。
