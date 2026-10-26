# 多模态统计分析 Agent

按[项目工作手册](docs/WORKBOOK.md)开发的统计分析基线：生成带证据的数据画像，用统计约束解释方法推荐，再调用经过审核的 Python 统计模板。当前版本 `0.3.0` 优先建设 CRAN 候选数据库，已完成官方源码采集、协作画像、版本化入库、恢复及检索。首批 8 条函数画像中 5 条机器复核通过、3 条待复核。见[数据库验证记录](docs/CRAN_DATABASE_VALIDATION.md)和[可读画像目录](database/cran_profiles.md)。此前真实模型与完整分析链路见[阶段记录](docs/STAGE2_VALIDATION.md)。

**进度与下一步：[PROGRESS.md](PROGRESS.md)** · **架构与 Agent 接口：[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** · **验证记录：[docs/VALIDATION.md](docs/VALIDATION.md)**

## 已实现

- CSV / XLSX 读取，三类 Pydantic 画像与导出的 JSON Schema。
- 五个职责明确的画像组件，LangGraph 顺序编排；数值由程序计算，研究设计保留未知状态。
- 五条默认知识画像；可选九条扩展库，增加 princomp、岭回归、层次聚类、QDA 同任务候选。
- L2 归一化、余弦排序、硬约束过滤、可解释软惩罚和 A/B/C 消融入口。
- PCA 与单响应 OLS 的 Python 模板、数值验证、Markdown/JSON 报告、SQLite 留档及失败日志。
- 合成示例、自动化测试与可复现检索冒烟评估。

默认仍为离线规则任务理解、五条知识与 **TF-IDF 词法演示基线**。可显式启用 DeepSeek 任务理解、固定 revision 的 multilingual-e5-small 和扩展库。统计量始终由程序计算，LLM 推断字段标记为未核验。五个组件的存在本身不证明多 Agent 优于单 Agent。

## 安装

Python 3.11 或以上。在仓库目录执行：

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Linux / macOS 使用 `source .venv/bin/activate`。如需复现本次测试依赖，先执行 `python -m pip install -r requirements.lock.txt`，再安装项目。锁定清单来自 Python 3.11 / Windows；其他平台以 CI 和实际安装结果为准。

## CRAN 数据库

先恢复仓库中的快照，即可离线查看和检索：

```powershell
python -m stat_agent kb restore
python -m stat_agent kb inspect
python -m stat_agent kb search --goal "回归模型的岭常数与 GCV"
python -m stat_agent kb search --goal "linear regression lambda GCV" --input examples/data/regression.csv --task regression --targets y --predictors x1 x2 --out runs/knowledge-query.json
```

源码来源为 MASS 7.3-66、cluster 2.1.8.3、psych 2.6.9，版本与 SHA256 已锁定。每条画像包含函数签名、参数说明、适用数据文本、带原文证据的输入/参数/假设/输出/失败条件、未知项与复核记录。原九条内置知识与这批八条 CRAN 画像分开存放，存在重叠，不能相加视为十七种方法。

重新采集或建库：

```powershell
python -m stat_agent kb collect
python -m stat_agent kb build
python -m stat_agent kb index --embedding-config configs/embedding.json
python -m stat_agent kb search --goal "数值变量的二次判别分析" --embedding-config configs/embedding.json
```

`collect` 联网下载官方源码并生成版本锁；只更新已配置的包和函数，不抓取全站。`build` 使用 CC Switch DeepSeek，提取和复核分角色调用，最多两轮修正；已有相同指纹结果会复用。显式 `--refresh` 重新调用模型。退出码 2 表示有待复核或失败条目，详情在构建报告中；机器复核不等于独立人工审核。

`search --input` 使用规则任务画像和程序计算的数据画像构成查询。它仅返回候选及条件；新库条件尚未编译成自动硬过滤规则，搜索不会执行 R 或替代 `analyze` 的可信模板。原始源码和 SQLite 在本地，仓库保存可恢复 JSON 与可读 Markdown，完整说明见 [database/README](database/README.md)。

## 运行

只提供数据集、只生成画像：

```powershell
python -m stat_agent profile YOUR_DATA.csv --out runs/profiles
python -m stat_agent profile YOUR_DATA.xlsx --sheet Sheet1 --out runs/profiles
```

不需要先给出分析目标或选择方法；输出结构化 `profile.json`、可读 `report.md`、任务信息及运行记录。可用 `--targets`、`--predictors`、`--groups` 补充变量角色。此入口只调用本地统计工具，不调用 LLM、不检索或执行统计方法；研究设计等无法从表格确定的条件保持未知。

PCA：

```powershell
python -m stat_agent analyze examples/data/pca.csv --goal "主成分分析" --predictors x1 x2 x3 --out runs/pca
```

已知系数的回归示例 `y = 2 + 3*x1 - x2`：

```powershell
python -m stat_agent analyze examples/data/regression.csv --goal "线性回归" --targets y --predictors x1 x2 --out runs/regression
```

Excel 可替换输入路径，使用 `--sheet 测量` 指定工作表。CSV 为 UTF-8（支持 BOM），XLSX 支持工作表名或从 0 开始的序号。当前上限为 20 MiB、10 万行、200 列，不支持旧版 `.xls`。

`--task pca|regression|clustering|manova|discriminant` 可明确任务。无法识别或包含多项任务时会要求澄清，不猜测执行。目标变量、分组和解释变量通过参数指定；未指定解释变量时使用除目标/分组外的数值列，真实分析建议显式选择，避免将数字 ID 当作测量变量。

默认规则模式对逻辑回归、岭回归等未支持方法以及未标准化 PCA 请求保留待澄清状态。DeepSeek 加扩展库可识别岭回归等具体候选，但新增方法尚无执行模板；任何额外分析或预处理限制仍需明确支持后才执行，不静默丢弃。单独说“降维”“组间比较”也需要明确方法。

每次运行在输出目录下创建唯一 run ID，包含 `task.json`、`profile.json`、`knowledge.json`、`retrieval.json`、`execution.json`、`run.json`、`report.md`，父目录保存 `profiles.sqlite3`。退出码：`0` 成功执行；`2` 需要澄清、约束阻止或执行接口未实现；`1` 输入/配置错误。运行数据默认被 Git 忽略；仓库只提交合成示例。

当前 TaskProfile、DataProfile、QualityProfile、RelationsProfile、ExecutionResult 使用 Schema `0.2.0`。任务画像新增可空的 `requested_method`，用于保留明确函数要求；旧画像可继续读取。缺失模式的键为列名数组的 JSON 字符串（完整行是 `[]`）；OLS 截距位于 `metrics.intercept`，`metrics.coefficients` 只含预测变量。Markdown 报告数组最多预览 10 项，完整数值仍保存在 JSON。

## DeepSeek 与固定语义模型

```powershell
python -m pip install -r requirements.semantic.lock.txt
python -m pip install --no-deps -e ".[semantic]"
python scripts/download_embedding.py
python -m stat_agent analyze examples/data/pca.csv --goal "使用 stats::prcomp 对 x1、x2、x3 做主成分分析" --task-agent deepseek --knowledge expanded --embedding-config configs/embedding.json --out runs/semantic
```

DeepSeek 适配器只读本机 `~/.cc-switch/cc-switch.db`，选择 Claude 配置下当前启用、名称为 DeepSeek 的服务。若仅有一个 DeepSeek 配置也可使用；多个候选且没有当前项时需先在 CC Switch 选定。支持官方 Anthropic 兼容接口，移除模型名末尾的 `[1m]` 等上下文标签后发送请求。本次配置及返回模型为 `deepseek-v4-pro`；它是服务端别名，不能保证长期权重不变。

仅向服务发送目标文本、列名、显式角色和可用方法；原始数据单元格不发送。密钥不进入日志，日志记录请求/响应哈希、模型名、Token 和有限重试。费用缺少固定价格依据时为 null。每次真实调用可能产生服务费用，默认离线命令不会调用服务。

本地模型固定为 `intfloat/multilingual-e5-small` revision `614241f622f53c4eeff9890bdc4f31cfecc418b3`，384 维；查询/文档分别带 `query: ` / `passage: ` 前缀。下载约 0.5 GB 文件至忽略目录 `.cache/models/`，保存 SHA256 清单；推理只加载本地文件，核验清单且禁用远程自定义代码。真实语义诊断已运行；通用接口仍可用 `--encoder sentence --model PATH --revision SHA`。

## 验证

```powershell
python -m pytest -q
python evaluation/run.py
python evaluation/expanded.py
python evaluation/expanded.py --embedding-config configs/embedding.json --out evaluation/results/expanded_semantic.json
python evaluation/profile_quality.py
python -m stat_agent schemas --out schemas
```

上述评估不调用 LLM。真实 API 验收入口为 `python evaluation/live_tasks.py`、`python scripts/live_pipeline_demo.py` 和 `python scripts/extract_knowledge_demo.py`，分别检查任务理解、完整链路和知识草稿提取。草稿均为未核验状态，不自动加入知识库。

保留原七例冒烟集，新增 8 个验证案例和 8 个测试案例。仅用验证集选 λ；两种编码器均选出 0，B/C 测试结果相同，因此没有软惩罚增益证据。应用默认 λ=0.5 保持演示配置，未将小样本调参结果当作生产配置。标注由开发者编写，尚待独立审核，细节见[阶段验证](docs/STAGE2_VALIDATION.md)。

## 当前边界

仅执行仓库内固定 PCA/OLS 模板，不执行 LLM 生成代码，不宣称具备任意代码沙盒。PCA 固定中心化和样本标准差缩放；OLS 使用截距和单个数值响应。缺失值、无穷值、PCA 常数列和不适用的回归矩阵均有阻止路径，不自动删行或插补。数值验证不证明独立性、模型假设或因果解释成立。

后续：独立人工标注、正式画像质量对照、统计诊断扩展、R 与受限执行环境、图片/图表/PDF、多 Agent 对照和 DARE 可复现性核验。当前真实模型与小样本诊断通过，不等于完成全部研究阶段。
