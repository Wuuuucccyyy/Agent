# v0.6 单次提取与协作复核配对实验

实验记录日期：2026-10-28；交付更新：2026-10-29。执行工作手册第 8.1 节中不依赖人工答案的部分：同源、同模型的画像生成对照，记录真实调用、Token、耗时、结构检查及失败。人工语义质量指标待独立参考和标注后计算。

## 实验设计

沿用 MASS 7.3-66、cluster 2.1.8.3、psych 2.6.9 的 8 个锁定函数。两组共用同一份来源、函数元数据、提取提示词、证据编号及输出 Schema。模型由用户指定的 CC Switch DeepSeek 配置读取；凭据不写入实验文件。

- **single**：调用一次适用性提取 Agent，完成 Schema 和原文引用位置检查后结束。
- **cooperative**：从完全相同的初稿继续，由另一次同模型调用复核；若未通过，最多修订一次并再次复核。

这是共享初稿的配对续跑设计，不是两次独立采样，也不是通用多 Agent 优越性实验。一次初稿生成失败时两组均记失败，不给某一组悄悄补跑。使用原有提示词，没有根据这批实验结果修订答案。

每个函数最多 4 次逻辑模型调用；每次请求最多一次传输重试。temperature=0、thinking disabled、max_output_tokens=4000、timeout=60。函数执行顺序固定，重复次数 1，因此耗时可能受缓存、时段和服务波动影响，不能进行显著性推断。

生产数据库中 Codex 修订过的画像和人工编写的 66 条规则不作为实验答案。实验不调用 R、不发布新数据库快照，也不改变已有机器或人工核验状态。

## 运行与复现

```powershell
python -m stat_agent.profile_experiment run --out evaluation/experiments/cran-paired-2026-10-28
python -m stat_agent.profile_experiment report --experiment evaluation/experiments/cran-paired-2026-10-28
```

`run` 使用本地只读 CC Switch 配置并联网调用官方 DeepSeek；仅发送公开的来源文档和生成草稿。`report` 离线读取已保存文件，不需要凭据或 API。

同一目录的已完成案例会原样复用，包含失败案例，避免反复生成直到成功。更改模型、来源、提示词、Schema 或设置时必须使用新目录。运行在每个阶段前后留档；若进程中断且请求是否完成不明，不会自动重放付费请求，而是保留记录并要求新实验目录。

每个实验目录保存：

| 文件 | 内容 |
|---|---|
| `plan.json` | 固定来源、模型设置、配对协议及计划哈希 |
| `sources.json` | 原始静态来源，便于离线核对 |
| `prompts.json` | 实际使用的提取/复核提示词及 Schema |
| `cases/*.json` | 初稿、复核、修订、失败信息、Token、耗时、模型回执及内容哈希 |
| `summary.json` | 保留计划分母的两组汇总和实际总消耗 |

模型回执包含请求和响应哈希、返回模型名及 stop_reason，不保存认证头或未经处理的提供商错误正文。DeepSeek 模型别名并非不可变版本，不能承诺跨日期逐字复现。

## 结果解释

本轮结果来自 [真实实验汇总](../evaluation/experiments/cran-paired-2026-10-28/summary.json)，不是模拟响应：

| 观测项 | single | cooperative（含共享初稿） |
|---|---:|---:|
| 计划 / 可用候选 | 8 / 8 | 8 / 8 |
| Schema 与引用位置检查通过 | 8 | 8 |
| 模型复核接受 / 待复核 | 未进行 | 6 / 2 |
| 完整流程调用次数 | 8 | 20 |
| 提供商报告 Token（含缓存输入） | 45,453 | 102,166 |
| 各调用阶段耗时之和 | 105.46 秒 | 201.93 秒 |
| 人工语义准确率 | 待标注 | 待标注 |

CLARA 和 principal 均触发一次修订，最后仍为 needs_review；原始意见和两次草稿全部保留。实际实验合计 20 次 API 调用、102,166 Token、0 次传输重试，共享初稿只计一次。

供人工对照的单元数为 single 125、cooperative 122。不同组生成条目数可以不同；各组内部不能删除难例缩小分母，完整率则必须采用同一份冻结参考中的 required 事实。少生成条目不能单独作为质量改善的证据。

`structurally_valid` 仅说明输出满足 Schema、包含输入/输出声明且引文可定位。`machine_accepted` 仅是同一个模型复核角色的判断。两者都不是人工准确率，不能用来证明更可靠。

两组 `accounted_usage` 都包含共享初稿成本，以描述各自完整流程所需成本。实际调用只有一份初稿，必须读取 `realized_usage`，不能将两组消耗相加。Token 是提供商成功响应报告的值，失败请求未报告的消耗不可推算；未配置可核验价目，美元成本保留为空。

生成失败仍在计划函数总数中。无法生成完整组别的候选时，工具拒绝制作仅含成功案例的人工对照表，以避免缩小分母。未通过机器复核但有完整候选的案例仍可接受人工对照。

## 接入独立人工参考

完整 8 函数实验沿用 v0.5 的同一来源集合，可使用 [独立复核材料](INDEPENDENT_REVIEW.md)编写并冻结参考。先完成来源参考，再查看实验候选；两组对照表分别标注，禁止互换或复用旧标签。

```powershell
python -m stat_agent.profile_experiment review-form --experiment evaluation/experiments/cran-paired-2026-10-28 --arm single --reference runs/review/reference-frozen.json --out runs/review/single
python -m stat_agent.profile_experiment review-form --experiment evaluation/experiments/cran-paired-2026-10-28 --arm cooperative --reference runs/review/reference-frozen.json --out runs/review/cooperative
python -m stat_agent.profile_experiment review-score --experiment evaluation/experiments/cran-paired-2026-10-28 --arm single --reference runs/review/reference-frozen.json --annotations runs/review/single-filled.json --out runs/review/single-quality.json
```

协作组同理填写和评分。工具不向标注者展示旧的模型复核意见，但表单生成时的组别目录可见；目前没有实现随机匿名双盲对照。质量指标必须在真实参考和完整标注到位后计算，不能从字段数量或机器通过率代替推断。

原文和改编的生成画像遵循对应 CRAN 来源许可，见 [许可证](../database/LICENSE-CRAN-DERIVED.txt)。

## 工程验证

本地全量测试：**128 passed**，其中新增 10 个配对实验测试。CI 仅离线读取真实留档并复算，不重新调用模型。

新增测试验证共享初稿成本只计一次、最多一次修订、失败保留分母、成功/失败均可零调用恢复、配置变化拒绝混用、中断请求不自动重放、来源/计划/案例哈希校验，以及同一独立参考可用于两组但标注不可互换。仓库保存的真实实验可在 CI 无密钥环境中离线校验和复算。

[恢复验证记录](../evaluation/results/cran_paired_resume.json)：明确禁止网络后，8 个案例全部复用，新增 API 调用和 Token 均为 0；生产快照仍为原 v0.4 快照。真实实验耗时来自各模型调用阶段之和，不含安装、测试或文档整理时间。
