# 多模态统计分析 Agent

按[项目工作手册](docs/WORKBOOK.md)开发的统计分析基线：生成带证据的数据画像，用统计约束解释方法推荐，再调用经过审核的 Python 统计模板。当前版本 `0.1.0` 是首轮可运行交付，项目尚未完成全部研究目标。

**进度与下一步：[PROGRESS.md](PROGRESS.md)** · **架构与 Agent 接口：[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** · **验证记录：[docs/VALIDATION.md](docs/VALIDATION.md)**

## 已实现

- CSV / XLSX 读取，三类 Pydantic 画像与导出的 JSON Schema。
- 五个职责明确的画像组件，LangGraph 顺序编排；数值由程序计算，研究设计保留未知状态。
- 五条官方文档参考知识画像：PCA、线性回归、K-means、MANOVA、LDA。
- L2 归一化、余弦排序、硬约束过滤、可解释软惩罚和 A/B/C 消融入口。
- PCA 与单响应 OLS 的 Python 模板、数值验证、Markdown/JSON 报告、SQLite 留档及失败日志。
- 合成示例、自动化测试与可复现检索冒烟评估。

默认编码器是 **TF-IDF 词法演示基线**，不是预训练语义双编码器。已提供共享预训练模型的 Sentence Transformers 查询/文档接口；真实模型下载与语义评估待下一阶段完成。任务理解目前使用显式参数和关键词规则，尚未接入 LLM API。五个组件的存在本身不证明多 Agent 优于单 Agent。

## 安装

Python 3.11 或以上。在仓库目录执行：

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Linux / macOS 使用 `source .venv/bin/activate`。如需复现本次测试依赖，先执行 `python -m pip install -r requirements.lock.txt`，再安装项目。锁定清单来自 Python 3.11 / Windows；其他平台以 CI 和实际安装结果为准。

## 运行

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

每次运行在输出目录下创建唯一 run ID，包含 `task.json`、`profile.json`、`knowledge.json`、`retrieval.json`、`execution.json`、`run.json`、`report.md`，父目录保存 `profiles.sqlite3`。退出码：`0` 成功执行；`2` 需要澄清、约束阻止或执行接口未实现；`1` 输入/配置错误。运行数据默认被 Git 忽略；仓库只提交合成示例。

## 语义检索接口

```powershell
python -m pip install -e ".[semantic]"
python -m stat_agent analyze examples/data/pca.csv --goal "主成分分析" --predictors x1 x2 x3 --encoder sentence --model PATH_TO_LOCAL_MODEL --out runs/semantic
```

也可传入模型 ID 和 `--revision COMMIT_SHA`。必须选择查询与文档处于同一空间的模型；实现使用同一 Sentence Transformer 的 `encode_query` 和 `encode_document`，禁用远程自定义代码。模型 ID 可能触发下载；默认词法模式无需网络、密钥或模型文件。本次尚未实测此可选依赖及模型路径。

## 验证

```powershell
python -m pytest -q
python evaluation/run.py
python -m stat_agent schemas --out schemas
```

评估依据见 [evaluation/cases.json](evaluation/cases.json)，结果见 [evaluation/results/smoke.json](evaluation/results/smoke.json)。这七个合成案例只用于检查检索流程，不是独立标注研究基准。未知条件不直接施加惩罚；软惩罚权重目前为未校准的演示配置。

## 当前边界

仅执行仓库内固定 PCA/OLS 模板，不执行 LLM 生成代码，不宣称具备任意代码沙盒。PCA 固定中心化和样本标准差缩放；OLS 使用截距和单个数值响应。缺失值、无穷值、PCA 常数列和不适用的回归矩阵均有阻止路径，不自动删行或插补。数值验证不证明独立性、模型假设或因果解释成立。

后续：LLM 语义理解、预训练 Embedding 验证、同任务多候选知识库、统计诊断扩展、R 与受限执行环境、图片/图表/PDF、多 Agent 对照和 DARE 可复现性核验。按手册先验收当前基线，再扩大数据源。
