# CRAN 函数画像数据库

这个目录保存可版本控制、可离线恢复的数据库快照。实际 SQLite 数据库位于 `database/knowledge.sqlite3`，运行文件被 Git 忽略；首次获取仓库后执行下面的恢复命令即可得到数据库，不需要 API 密钥或重新采集。

```powershell
python -m stat_agent kb restore
python -m stat_agent kb inspect
python -m stat_agent kb search --goal "用岭回归拟合模型并比较 GCV"
```

`cran_profiles.json` 包含当前批次的不可变快照、函数元数据、清洗后的官方参考片段、适用数据文本、带引文的结构化条件、复核过程、模型回执与质量状态。每条画像以内容哈希标识版本；恢复时核对画像与快照哈希、元数据一致性、文本一致性及已通过条目的证据引用。

首批范围：MASS 的 lda、qda、lm.ridge；cluster 的 pam、clara、agnes、diana；psych 的 principal。具体包版本与源码包哈希固定在 `configs/cran_sources.lock.json`。它们是方法/函数画像，不是 CRAN 示例数据集的统计描述。

## 质量状态

- `machine_checked`：通过结构校验、引用检查和模型复核或明确记录的来源裁决，进入默认候选搜索。当前 8 条经 Codex 来源复核通过。
- `needs_review`：两轮内仍有问题，保存在数据库中，但默认搜索排除。
- `semantic_verification=llm_inference_not_human_verified`：所有生成的语义字段仍未经过独立人工审核。
- `runtime_verified=false`：未执行 R 函数或帮助中的示例。

初始复核与提取共用 DeepSeek；本轮 Codex 对照锁定原文处理了真实错误与误报，保留原记录，不等于独立专家一致意见。新增 66 条显式维护、来源绑定的条件规则；搜索只排除明确违反硬条件的候选，缺信息返回未知。详见 [复核与规则](../docs/AUDIT_AND_RULES.md)。不直接执行模型表达式，不执行 R；现有 `analyze` 的固定 PCA/OLS 路径保持独立。

## 更新、索引与历史

```powershell
# 有意更新版本时才重新采集；普通 build 使用锁定版本。
python -m stat_agent kb collect
python -m stat_agent kb build
# 本地固定 e5 模型需要按仓库 README 先安装和下载。
python -m stat_agent kb index --embedding-config configs/embedding.json
python -m stat_agent kb search --goal "大型数据的抽样中心对象聚类" --embedding-config configs/embedding.json
```

构建按来源、解析器、提示词、Schema 和模型名的指纹复用已有结果，包括待复核画像；`--refresh` 会明确重新调用模型。每个函数最多两轮提取与复核。函数失败不会阻止后续函数的处理，但有构建错误时不切换当前快照。待复核画像可随完整批次保存，不进入默认检索。锁文件以规范化 JSON 计算哈希，避免跨平台换行差异。

数据库保留 `profiles`、`snapshots`、`builds` 和 `vectors`；活跃快照在全部函数处理完成且无构建错误后切换。向量按画像版本、文本哈希和模型名缓存，模型或画像变化时重新编码。JSON 导出不包含向量；恢复后按需重建本地索引。JSON 保留当前快照，完整历史仍在本地 SQLite 和 Git 历史中。

## 来源与许可

来源为 CRAN 官方源码分发包的 DESCRIPTION 和 man/*.Rd。没有安装包、运行源码或执行 Rd 示例。清洗保留原文引用、包版本、源码包/Rd SHA256、文档路径及采集时间。

| 包 | 官方来源 | 原始包声明许可 |
|---|---|---|
| MASS | https://cran.r-project.org/package=MASS | GPL-2 或 GPL-3 |
| cluster | https://cran.r-project.org/package=cluster | GPL ≥ 2 |
| psych | https://cran.r-project.org/package=psych | GPL ≥ 2 |

快照中的 CRAN 原文片段、参数说明及其改编部分沿用 GPL-2 条款，许可证文本见 [LICENSE-CRAN-DERIVED.txt](LICENSE-CRAN-DERIVED.txt)。原始作者、完整源码及修改历史以锁文件链接对应的包为准；本项目静态清洗、模型中文归纳和新增校验记录均在画像中标识。仓库自有程序代码仍按根目录 LICENSE 发布。
