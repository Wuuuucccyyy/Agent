# 来源与核验范围

v0.3 新增 CRAN 源码采集：MASS 7.3-66、cluster 2.1.8.3、psych 2.6.9。锁文件 `configs/cran_sources.lock.json` 保存官方 PACKAGES 索引信息、下载 URL 和源码 SHA256；函数画像另记录 Rd 路径与 SHA256。来源使用本轮固定包，而不是此前 R-devel 页面的包版本。清洗/引用内容沿用来源许可，见 [database/README](../database/README.md)。

Rd 结构依据：[Writing R Extensions — Rd format](https://cran.r-project.org/doc/manuals/r-release/R-exts.html#Rd-format)。实现为有限静态解析，处理嵌套大括号、文档编码、注释及常见文本宏，保留原 usage；未运行 R 的正式 Rd 编译器。复杂宏的完整语义仍待扩展。

核对日期：2026-10-24。用户工作手册是范围依据，文字摘录见 [WORKBOOK](WORKBOOK.md)。本轮未修改原始 Word 文件。

| 画像 | 官方参考 | 核对范围 |
|---|---|---|
| stats::prcomp | https://stat.ethz.ch/R-manual/R-devel/library/stats/html/prcomp.html | SVD、中心化/缩放、输出、样本方差分母与常数列缩放限制 |
| stats::lm | https://stat.ethz.ch/R-manual/R-devel/library/stats/html/lm.html | 公式、最小二乘、缺失策略、奇异拟合选项 |
| stats::kmeans | https://stat.ethz.ch/R-manual/R-devel/library/stats/html/kmeans.html | 数值输入、中心配置、聚类输出与收敛提示 |
| stats::manova | https://stat.ethz.ch/R-manual/R-devel/library/stats/html/manova.html | 多元响应、aov 包装和 summary 路径；未完整核对所有多元检验假设 |
| MASS::lda | https://stat.ethz.ch/R-manual/R-devel/library/MASS/html/lda.html | grouping、缺失处理、类内常数和协方差奇异边界 |
| stats::princomp | https://stat.ethz.ch/R-manual/R-devel/library/stats/html/princomp.html | 原始矩阵 n≥p、协方差特征分解、方差除数 N、相关矩阵常数列限制 |
| MASS::lm.ridge | https://stat.ethz.ch/R-manual/R-devel/library/MASS/html/lm.ridge.html | lambda 默认 0、截距不惩罚、缩放与 GCV；正 lambda 需要另行调参 |
| stats::hclust | https://stat.ethz.ch/R-manual/R-devel/library/stats/html/hclust.html | 距离输入、连接规则与树输出；资源阈值来自项目策略 |
| MASS::qda | https://stat.ethz.ch/R-manual/R-devel/library/MASS/html/qda.html | 类内协方差奇异报错；组样本数只是必要条件 |

R-devel 是可变文档来源。stats 页面显示 4.6.0；这不表示本地安装过 R 4.6.0。MASS 包版本未固定。知识库中的 `official_docs_reviewed` 表示人工核对参考页，未做 R 运行验证；解释性假设、项目简化签名和替代项另记 rule_inference/unverified。正式实验前需要固定发行版文档及包版本并增加逐字段证据。

工程接口依据：

- LangGraph StateGraph：https://docs.langchain.com/oss/python/langgraph/graph-api
- Sentence Transformers 查询/文档编码：https://sbert.net/docs/package_reference/sentence_transformer/model.html

DARE 目前仅保留手册中的待核验事项，尚未确认准确的论文、仓库和评估资源，因此没有对照结果或优越性声明。

v0.2 新增来源：

- DeepSeek Anthropic 兼容接口：https://api-docs.deepseek.com/guides/anthropic_api/ 。使用强制工具调用与 JSON Schema，关闭 thinking，有限重试；模型来自用户 CC Switch 配置。
- e5 模型卡：https://huggingface.co/intfloat/multilingual-e5-small 。固定 revision `614241f622f53c4eeff9890bdc4f31cfecc418b3`，即使中文也使用 query/passage 前缀；384 维，512 token 截断。
- 扩展库 MASS 页面显示 7.3-65，stats 页面显示 4.6.0；记录于新画像中，仍未安装或执行这些 R 版本。原五条知识保留历史来源记录。
- prcomp 自动草稿在 evaluation/results/knowledge_draft.json 保存文档哈希、模型回执与未核验字段；原 HTML 缓存在忽略目录。未核验草稿不代替人工审阅库。
