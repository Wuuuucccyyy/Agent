# 架构与接口

版本 0.1.0。设计依据为用户工作手册，优先交付可运行且能追溯来源的基线。LLM 和更多模态保留为后续接入点。

实现更新至 0.1.1，结构仍遵循首轮设计。差异：输入采用单次字节快照；完整行统计区分解释变量子集和分析所选全部变量；SVD 结果用于复算秩；缺失模式采用打包掩码计数及 JSON 数组键；编码器按完整、有序候选文本缓存一个知识库；查询摘要仅引用所选变量。输出格式迁移见 [BASELINE_REVIEW](BASELINE_REVIEW.md)。

```mermaid
flowchart TD
    A[自然语言目标与 CSV/XLSX] --> B[本地表格读取与输入检查]
    B --> C[Agent 1 任务理解]
    C --> D[Agent 2 结构与变量画像]
    D --> E[Agent 3 分布质量与多元关系]
    E --> F[Agent 5 整合与验证]
    K[官方 R 文档人工核对] --> L[Agent 4 离线知识画像导入]
    L --> M[版本化知识库]
    M --> G[共享空间编码与余弦相似度]
    F --> G
    G --> H[硬约束过滤与软约束惩罚]
    H --> I{候选与执行条件}
    I -->|满足| J[Python PCA/OLS 固定模板]
    I -->|未知或不支持| N[可解释阻止或待实现状态]
    J --> O[数值一致性验证]
    O --> P[Markdown JSON SQLite 与日志]
    N --> P
```

总控是 `pipeline.build_graph` / `run_pipeline`，使用 LangGraph 的共享 `AgentState`。v0.1 为固定顺序；条件处理在检索/执行节点中产生显式状态，尚无重试、并行分支或断点恢复。SQLite 保存最终快照及失败记录，不是 LangGraph checkpoint。

## 五个画像组件

| 组件 | 输入 | 输出 | 调用条件与边界 |
|---|---|---|---|
| TaskUnderstandingAgent | 目标文本、显式任务及变量角色 | TaskProfile | 每次在线任务；规则识别不确定时保留 unknown；未来通过 TaskInterpreter 协议接 LLM |
| StructureAgent | DataFrame、来源 | VariableProfile 列表 | 表格读取成功后；数值计算只使用有限观测，缺失和无穷值分别计数 |
| RelationsAgent | DataFrame、TaskProfile | RelationsProfile | 角色校验后；仅计算所选数值解释变量；记录完整行数，完整行不足则不推断矩阵性质 |
| KnowledgeAgent | 随包分发的 JSON 种子库 | KnowledgeProfile 列表 | 离线人工提取结果的 Schema/ID 校验与导入；不伪装成自动抓取或 LLM 文档抽取 |
| ProfileValidationAgent | 数据、来源、任务、变量与关系画像 | DataProfile | 检查角色冲突、变量数和 Schema，整合质量与七层画像；没有实现人工复核 UI |

Agent 3 的分布统计由共享 `profiling` 工具计算，Agent 5 调用工具补齐质量层。职责按输入输出隔离，避免重复计算。未来若增加 LLM，只允许返回带 `llm_inference` 证据的语义字段，不覆盖程序统计事实。

## 三类 Schema 与七层画像

权威实现：`src/stat_agent/schemas.py`；生成文件：`schemas/TaskProfile.json`、`DataProfile.json`、`KnowledgeProfile.json`。

DataProfile 对应来源、结构、变量、质量、多元关系、设计、证据与未知信息七层。证据区分 computed、official_document、user、rule_inference、llm_inference、unknown；verified 表示来源/计算记录已校验，不表示研究假设成立。

均值、样本方差（ddof=1）、分位数、修正偏度、超额峰度等在变量层保存；关系层计算完整有限数值行上的相关、样本协方差、中心化矩阵秩和基于原始协方差能量的 95% 有效维度。其有效维度不等于后续标准化 PCA 的保留维数。奇异矩阵 condition_number 为 null，并用 singular 标识，避免 JSON Infinity。

数值 dtype 不是测量尺度。唯一列只是候选主键。边际偏态不等于模型残差非正态；IQR 异常标记不授权删除。布局、独立性、配对、重复测量、抽样与缺失机制未由输入证实时均标记未知。

## 检索与执行

`Encoder.encode_pair(query, documents)` 返回同空间向量。统一验证形状、有限值和非零范数，执行稳定 L2 归一化。默认 TF-IDF 为离线测试；可选 SentenceEncoder 使用共享预训练模型。

`S = alpha * cosine - penalty_lambda * sum(weight * severity)`。A 仅余弦，B 加硬过滤，C 再加软惩罚；A 仍记录约束，执行阶段不会因消融绕过硬约束。未知条件保留说明，不赋予极大惩罚。没有候选时返回 `no_compatible_method`。

硬约束中明确区分项目基线签名与 R 函数本身能力，例如 v0.1 的数值解释变量要求比 R 公式系统窄。软惩罚只针对观测到的问题；共线性不会自动惩罚 PCA。所有权重与阈值尚未通过独立验证集校准。

固定 Python 模板使用 SVD PCA 和最小二乘 OLS，做重构误差、方差占比及正交条件校验；不执行外部命令。未来执行模型生成代码前必须建立独立的无网络、文件访问受限、资源受限环境；不能把当前进程内模板称为这种隔离环境。

## 持久化与复现

每个 run 使用唯一 ID。日志记录节点成功/失败、耗时、依赖版本、输入 SHA256、知识库 SHA256、配置和 API 使用情况。当前 API 调用、Token 与 API 费用为零；不等于本地计算无成本。原始数据不自动提交 GitHub。运行失败也保存 run.json 和 SQLite 快照。
