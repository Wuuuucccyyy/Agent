# CRAN 函数画像目录

由数据库快照自动导出。语义内容为模型推断，未经过独立人工审核或 R 运行验证。

machine_checked 进入候选搜索；needs_review 保留待复核并从默认搜索排除。

来源文档及改编部分沿用对应 CRAN 许可，见同目录 README 与许可证。

快照：`aa61823f904a1b780aaf68113c85136e4269a228d8371d92ef54b3ae3ac489c1`

## MASS::lda

版本：7.3-66；状态：**machine_checked**。

该函数执行线性判别分析，用于分类任务：以分组因子为响应、以非因子解释变量为判别器，拟合判别函数并输出类别与后验概率。输入可为公式+数据框，或矩阵/数据框+分组因子。可指定先验概率、容差、估计方法及留一交叉验证。需注意缺失值默认导致失败、常数变量会被拒绝。

### 函数接口

```r

lda(x, \dots)

\method{lda}{formula}(formula, data, \dots, subset, na.action)

\method{lda}{default}(x, grouping, prior = proportions, tol = 1.0e-4,
    method, CV = FALSE, nu, \dots)

\method{lda}{data.frame}(x, \dots)

\method{lda}{matrix}(x, grouping, \dots, subset, na.action)

```

参数：formula, data, x, grouping, prior, tol, subset, na.action, method, CV, nu, ...

### 适用条件与输出

- **input**：输入可采用公式形式 groups ~ x1 + x2 + ...，其中响应为分组因子，右侧为（非因子）判别变量。
- **input**：也可采用矩阵/数据框/Matrix 作为解释变量 x，并配合一个指定每观测类别的因子 grouping。
- **parameter**：prior 指定各类别的先验概率；若未指定则使用训练集的类别比例，若指定则须按因子水平顺序给出。
- **parameter**：method 可选 "moment"、"mle"、"mve" 或 "t"，分别对应标准估计、MLE、cov.mve 及基于 t 分布的稳健估计。
- **parameter**：CV=TRUE 时返回留一交叉验证的类别（MAP 分类因子）与后验概率；若先验为估计值则使用整个数据集的比例。
- **preprocessing**：subset 与 na.action 若使用必须完整命名；na.action 默认使过程失败，na.omit 则剔除含缺失值的观测。
- **failure**：若某变量组内方差小于 tol^2，函数会停止并报告该变量为常数；这可能源于变量恒定或尺度不佳。
- **output**：非 CV 情形返回 "lda" 对象，含 prior、means、scaling、svd、N 与 call 等分量；svd 的平方为典型 F 统计量。
- **assumption**：指定 prior 会影响分类（除非在 predict.lda 中覆盖），并影响判别旋转，因为使用了按先验加权的组间协方差矩阵。
- **failure**：若数据中缺失一个或多个组，这些组会被丢弃并给出警告，但分类仍相对于原始水平集合。

### 未知与待复核

- 文档未说明对样本量、正态性或组内协方差齐性等推断性假设的要求。
- 文档未说明该函数对任意特定用户数据集的适用性或研究设计是否成立。
- 文档未说明 tol 的默认值 1.0e-4 之外应如何针对具体数据选择容差。

[官方源码包](https://cran.r-project.org/src/contrib/MASS_7.3-66.tar.gz)；文档 `MASS/man/lda.Rd`。

画像版本：`cd7e0e24b80a623113e9251c15b5cf94316cc44f2dfcda8b984bdd57152fcf01`。逐条原文证据和参数说明见同名 JSON。

## MASS::lm.ridge

版本：7.3-66；状态：**machine_checked**。

该函数用于通过岭回归拟合线性模型，适用于以公式指定响应变量与预测变量的回归任务。输入可为数据框、列表或环境，支持子集筛选、缺失值过滤、offset 项及因子对比设置。lambda 可为标量或向量，一次拟合多个岭常数。输出为系数矩阵（每行对应一个 lambda）、缩放信息、GCV 及 HKB/L-W 岭常数估计；系数非原始尺度，需经 coef 方法使用。截距系数不被惩罚。

### 函数接口

```r

lm.ridge(formula, data, subset, na.action, lambda = 0, model = FALSE,
         x = FALSE, y = FALSE, contrasts = NULL, \dots)
select(obj)

```

参数：formula, data, subset, na.action, lambda, model, x, y, contrasts, ..., obj

### 适用条件与输出

- **input**：该函数通过公式指定响应变量与预测变量，拟合线性模型。
- **input**：data 可为数据框、列表或环境，用于解释公式中的变量；offset 项被允许。
- **parameter**：lambda 可为标量或向量，表示一个或多个岭常数。
- **parameter**：subset 用于选择参与拟合的行，默认包含全部观测；na.action 用于过滤缺失数据。
- **parameter**：contrasts 可为公式中的部分或全部因子项指定对比方式。
- **assumption**：若模型中存在截距，其系数不被惩罚；若要惩罚截距，需自行加入常数项并移除截距。
- **output**：返回列表，其中 coef 为系数矩阵，每行对应一个 lambda 值；这些系数不在原始尺度上，需由 coef 方法使用。
- **output**：返回值还包含 scales（X 矩阵缩放）、Inter（是否含截距）、lambda、ym、xm、GCV、kHKB 与 kLW 等分量。
- **failure**：model、x、y 参数（是否返回模型框、设计矩阵、响应）未实现。

### 未知与待复核

- 文档未说明对样本量、变量分布或残差独立同分布等推断性假设的要求。
- 文档未说明该函数对任意特定用户数据集的适用性或预测性能。
- 文档未说明 lambda 的默认取值或推荐选择方式（仅说明默认 lambda = 0）。

[官方源码包](https://cran.r-project.org/src/contrib/MASS_7.3-66.tar.gz)；文档 `MASS/man/lm.ridge.Rd`。

画像版本：`531aa23cbb48846084c7768a0a3536f9233e8529c855afedd1ef4df1e27c4ec1`。逐条原文证据和参数说明见同名 JSON。

## MASS::qda

版本：7.3-66；状态：**machine_checked**。

该函数执行二次判别分析，用于将观测分配到由分组因子定义的类别。输入可为公式（响应为分组因子，右侧为非因子判别变量）或矩阵/数据框/Matrix 加分组因子。可指定先验概率、估计方法、子集与缺失值处理，并支持留一交叉验证。输出为 qda 对象（或 CV=TRUE 时的分类与后验概率）。

### 函数接口

```r

qda(x, \dots)

\method{qda}{formula}(formula, data, \dots, subset, na.action)

\method{qda}{default}(x, grouping, prior = proportions,
    method, CV = FALSE, nu, \dots)

\method{qda}{data.frame}(x, \dots)

\method{qda}{matrix}(x, grouping, \dots, subset, na.action)

```

参数：formula, data, x, grouping, prior, subset, na.action, method, CV, nu, ...

### 适用条件与输出

- **input**：输入可通过公式 groups ~ x1 + x2 + ... 指定，其中响应为分组因子，右侧为（非因子）判别变量。
- **input**：若不使用公式，则需提供 x（矩阵、数据框或 Matrix，含解释变量）与 grouping（指定每个观测类别的因子）。
- **parameter**：prior 指定类别先验概率；未指定时使用训练集的类别比例，若指定则应按因子水平顺序给出。
- **parameter**：method 可选 "moment"、"mle"、"mve"（使用 cov.mve）或 "t"（基于 t 分布的稳健估计），其中 method="t" 需用 nu 指定自由度。
- **parameter**：subset 为指定训练样本案例的索引向量，na.action 指定缺失值处理；两者若给出必须命名。
- **preprocessing**：默认缺失值处理是使过程失败；可选用 na.omit 以剔除在任一所需变量上存在缺失值的案例。
- **parameter**：CV=TRUE 时返回留一交叉验证的结果（类别与后验概率）；若先验被估计，则使用整个数据集的类别比例。
- **output**：返回 qda 类对象，包含 prior、means、scaling、ldet、lev、terms（若为公式）与 call 等组件。
- **output**：当 CV=TRUE 时，返回值是含 class（MAP 分类因子）与 posterior（各类后验概率）的列表。
- **failure**：使用 QR 分解，若任一组内方差奇异则给出错误信息。

### 未知与待复核

- 文档未说明对样本量、变量分布或组间协方差结构的具体要求，也未说明该方法对任意特定用户数据集的适用性。
- 文档未说明各 method 选项（如 mve、t）对数据规模或异常值情形的具体适用条件。
- 文档未说明奇异组内方差之外的其他失败条件或数值稳定性限制。

[官方源码包](https://cran.r-project.org/src/contrib/MASS_7.3-66.tar.gz)；文档 `MASS/man/qda.Rd`。

画像版本：`4e4f1b4e77ebf85c5b1e359acf60905a4f36da0a3f5317b2752e1b7ca00bdac0`。逐条原文证据和参数说明见同名 JSON。

## cluster::agnes

版本：2.1.8.3；状态：**needs_review**。

agnes 用于对数据集进行凝聚式层次聚类。输入可为数值型数据矩阵/数据框（行=观测、列=变量，允许缺失值），或相异度矩阵/向量（不允许缺失值）。可通过 metric 选择欧氏或曼哈顿距离，stand 控制标准化，method 选择 linkage 方法。输出为 agnes 类对象，含凝聚系数并可通过 plot.agnes 查看 banner 图形。

### 函数接口

```r

agnes(x, diss = inherits(x, "dist"), metric = "euclidean",
      stand = FALSE, method = "average", par.method,
      keep.diss = n < 100, keep.data = !diss, trace.lev = 0)

```

参数：x, diss, metric, stand, method, par.method, keep.diss, keep.data, trace.lev

### 适用条件与输出

- **input**：x 可为数据矩阵、数据框或相异度矩阵，取决于 diss 参数的值。
- **input**：当 x 为矩阵或数据框时，每行对应一个观测，每列对应一个变量，且所有变量必须为数值型。
- **input**：矩阵/数据框形式允许缺失值（NA），但相异度矩阵形式不允许缺失值。
- **input**：相异度矩阵通常为 daisy 或 dist 的输出，也允许长度为 n*(n-1)/2 的向量（n 为观测数）。
- **parameter**：metric 可选 "euclidean" 或 "manhattan"；若 x 已是相异度矩阵，该参数被忽略。
- **parameter**：stand=TRUE 时按列标准化（减去均值并除以平均绝对偏差）；若 x 已是相异度矩阵则被忽略。
- **parameter**：method 实现的方法包括 average、single、complete、ward、weighted，以及作为 weighted 推广的 flexible 和作为 average 推广的 gaverage（后两者使用 Lance-Williams 公式与 par.method）。
- **parameter**：par.method 仅在 method 为 flexible 或 gaverage 时使用，为长度 1、3 或 4 的数值向量（gaverage 有默认值）。
- **parameter**：keep.diss 与 keep.data 控制是否在结果中保留相异度与输入数据，设为 FALSE 可显著减小结果并节省内存。
- **output**：返回 agnes 类对象（继承自 twins），表示聚类结果，并产生凝聚系数以度量聚类结构。
- **output**：除树状结构外，agnes 还提供 banner 图形显示（通过 plot.agnes 查看）。
- **failure**：自 cluster 2.0 起，导致无效合并结构的选择会报错。

### 未知与待复核

- 文档未说明对样本量、变量独立性或分布的任何要求，也未确立该函数对任意特定用户数据集的适用性。
- 文档未说明 ward 方法的具体距离更新公式或其对欧氏距离的依赖。
- 文档未说明缺失值在矩阵/数据框形式下如何处理（如成对删除或插补）。
- 复核意见：claim "method 实现的方法包括 average、single、complete、ward、weighted，以及作为 weighted 推广的 flexible 和作为 average 推广的 gaverage" 中，将 flexible 描述为 weighted 的推广、gaverage 描述为 average 的推广，与原文不符。原文 arguments 明确列出六种方法为 average、single、complete、ward、weighted、flexible、gaverage（实为七种），且 details 中说明 weighted 等价于 flexible, par.method=0.5（即 weighted 是 flexible 的特例，而非 flexible 是 weighted 的推广），gaverage 是 average 的推广（flexible UPGMA）。应改为：方法包括 average、single、complete、ward、weighted、flexible、gaverage，其中 weighted 等价于 flexible, par.method=0.5，gaverage 是 average 的推广。
- 复核意见：claim "par.method 仅在 method 为 flexible 或 gaverage 时使用，为长度 1、3 或 4 的数值向量（gaverage 有默认值）" 中，"仅在 method 为 flexible 或 gaverage 时使用" 的表述与原文一致，但原文还说明 gaverage 的默认值为 -0.1（"if par.method is not specified, a default value of -0.1 is used"），该默认值信息被省略，导致 gaverage 默认行为描述不完整。建议补充 gaverage 默认 par.method = -0.1。

[官方源码包](https://cran.r-project.org/src/contrib/cluster_2.1.8.3.tar.gz)；文档 `cluster/man/agnes.Rd`。

画像版本：`a270a1ad1a30e23bfb6cf8e9b28b35e1f1debd209aa7017aecf4fbc055bfb62a`。逐条原文证据和参数说明见同名 JSON。

## cluster::clara

版本：2.1.8.3；状态：**needs_review**。

clara 用于将数据划分为 k 个簇的分区聚类，适合处理远大于 pam 可处理规模的数据集。输入为数值（或逻辑）矩阵/数据框，允许缺失值；需指定簇数 k（0<k<n）。可通过 metric、stand、samples、sampsize 等参数控制距离度量、标准化与抽样规模，输出 clara 对象或仅聚类向量。

### 函数接口

```r

clara(x, k, metric = c("euclidean", "manhattan", "jaccard"),
      stand = FALSE, cluster.only = FALSE, samples = 5,
      sampsize = min(n, 40 + 2 * k), trace = 0, medoids.x = TRUE,
      keep.data = medoids.x, rngR = FALSE, pamLike = FALSE, correct.d = TRUE)

```

参数：x, k, metric, stand, cluster.only, samples, sampsize, trace, medoids.x, keep.data, rngR, pamLike, correct.d

### 适用条件与输出

- **input**：x 为数据矩阵或数据框，每行对应一个观测，每列对应一个变量。
- **input**：所有变量必须为数值型（或逻辑型），且允许存在缺失值（NA）。
- **parameter**：k 为整数，表示簇数，要求 0 < k < n，其中 n = nrow(x)。
- **parameter**：metric 指定计算观测间相异度的度量，可选 "euclidean"、"manhattan"、"jaccard"；欧氏距离为差值平方和的平方根，曼哈顿距离为绝对差之和。
- **preprocessing**：stand=TRUE 时，在计算相异度前对每列变量标准化，即减去该变量均值并除以该变量的平均绝对偏差。
- **parameter**：samples 为抽取的样本数，默认 N=5 偏小，文档建议将其设大一个数量级；sampsize 为每个样本的观测数，默认 min(n, 40+2*k)，应大于 k 且至多为 n。
- **assumption**：在固定子样本大小（sampsize）与样本数（samples）下，时间与存储需求随 n 线性增长而非二次增长；存储约为 O(n*p)+O(j^2)，CPU 时间约为 O(n*p*j^2*N)，其中 j=sampsize、N=samples。
- **output**：cluster.only=FALSE（默认）时返回类 "clara" 的对象；cluster.only=TRUE 时返回长度为 n、取值为 1:k 的整数聚类向量。
- **failure**：当 x 中存在 NA 时，correct.d 控制是否使用正确的距离计算；默认 correct.d=TRUE（即默认使用正确公式），若未显式指定 correct.d 会发出警告。
- **parameter**：rngR=FALSE 时使用 Fortran 内置的确定性抽样方案；rngR=TRUE 时使用 R 的随机数生成器，每次调用结果不同，可用 set.seed() 使结果可复现。

### 未知与待复核

- 文档未给出适用于特定用户数据集的样本量阈值，仅说明 clara 可处理远大于 pam 的数据集，"小"数据集取决于可用内存与速度。
- 文档未对数据分布、独立性或正态性等推断性假设作出说明，因此本函数对任意特定用户数据集的适用性未经验证。
- 文档未说明 jaccard 度量下 clara 的算法细节（details 仅针对 euclidean 与 manhattan 描述）。
- 复核意见：claim（failure 类）关于 correct.d 的表述有误：文档说明默认 correct.d=TRUE，但警告是在存在 NA 且用户未显式指定 correct.d 时发出。该 claim 将"默认使用正确公式"与"未显式指定会警告"并列陈述，但未准确传达：即使默认 correct.d=TRUE，只要用户未显式指定，仍会发出警告。原文为"a warning is signalled in this case, unless the user explicitly specifies correct.d"，即警告条件仅取决于是否显式指定，而非取决于 correct.d 的取值。当前表述"默认 correct.d=TRUE（即默认使用正确公式），若未显式指定 correct.d 会发出警告"实际上与原文一致，但需确认：原文并未说明默认 correct.d=TRUE 时使用正确公式这一因果，且警告与 correct.d 取值无关。建议改为：存在 NA 时，除非用户显式指定 correct.d，否则会发出警告；默认 correct.d=TRUE。
- 复核意见：claim（assumption 类）将复杂度表述为"在固定子样本大小与样本数下，时间与存储需求随 n 线性增长"，但原文 note 中存储复杂度 O(n*p)+O(j^2) 与 CPU 时间 O(n*p*j^2*N) 均以"for small k"为前提条件，且 details 中"linear in n rather than quadratic"是针对存储与时间随 n 的缩放。当前 claim 未提及"for small k"这一限定，可能过度概括。建议补充"（假设 k 较小）"这一限定。

[官方源码包](https://cran.r-project.org/src/contrib/cluster_2.1.8.3.tar.gz)；文档 `cluster/man/clara.Rd`。

画像版本：`d1fd90818704a9643c0878ad50c210d70c189054005ec5ec6b57f36346512ff1`。逐条原文证据和参数说明见同名 JSON。

## cluster::diana

版本：2.1.8.3；状态：**machine_checked**。

该函数用于对数据集执行分裂式层次聚类，返回 diana 类对象。输入可为数值型数据矩阵/数据框（行=观测、列=变量，允许缺失值），或由 daisy/dist 生成的相异度矩阵/对象（不允许缺失值）。可通过 metric 选择欧氏或曼哈顿距离，stand 控制按列标准化。输出含分裂系数 dc、merge 矩阵、order 等，并支持 print/summary/plot 及 as.hclust、cutree 等后续处理。

### 函数接口

```r

diana(x, diss = inherits(x, "dist"), metric = "euclidean", stand = FALSE,
      stop.at.k = FALSE,
      keep.diss = n < 100, keep.data = !diss, trace.lev = 0)

```

参数：x, diss, metric, stand, stop.at.k, keep.diss, keep.data, trace.lev

### 适用条件与输出

- **input**：x 可为数据矩阵或数据框，此时每行对应一个观测、每列对应一个变量，且所有变量必须为数值型。
- **input**：当 x 为矩阵或数据框时允许存在缺失值（NA）；当 x 为相异度矩阵时不允许缺失值。
- **input**：x 也可为相异度矩阵或对象（通常由 daisy 或 dist 生成），或长度为 n*(n-1)/2 的向量，其中 n 为观测数。
- **parameter**：diss 为逻辑标志：TRUE（dist 或相异度对象的默认值）时 x 视为相异度矩阵，FALSE 时视为观测×变量矩阵。
- **parameter**：metric 指定计算相异度的度量，可选 "euclidean" 或 "manhattan"；若 x 已是相异度矩阵则该参数被忽略。
- **parameter**：stand 为 TRUE 时，在计算相异度前对每列变量标准化（减去均值并除以平均绝对偏差）；若 x 已是相异度矩阵则被忽略。
- **parameter**：stop.at.k 默认 FALSE，非默认值（提前停止）尚未实现。
- **output**：返回 diana 类对象，含 order、height、dc（分裂系数）、merge 等组件，并提供 print、summary、plot 方法。
- **output**：diana 类继承自 twins，可用 pltree，且提供 as.hclust 与 as.dendrogram 方法；cutree 可用于分组提取。
- **output**：分裂系数 dc 随观测数增长，因此不应用于比较规模差异很大的数据集。
- **failure**：当输入为相异度矩阵时，data 组件不可用；keep.diss 与 keep.data 设为 FALSE 可减小结果体积。

### 未知与待复核

- 文档未说明对样本量、变量独立性或分布形态的任何要求，也未给出最小样本量阈值。
- 文档未说明该函数对特定用户数据集的适用性或聚类质量保证，需结合具体数据与领域知识判断。
- 文档未说明缺失值在矩阵/数据框输入下被如何处理（如成对删除或插补）。

[官方源码包](https://cran.r-project.org/src/contrib/cluster_2.1.8.3.tar.gz)；文档 `cluster/man/diana.Rd`。

画像版本：`f26327a7d6970c03ea92ed535fb5eb3749780ebca9dea991cbf4666d3df180c8`。逐条原文证据和参数说明见同名 JSON。

## cluster::pam

版本：2.1.8.3；状态：**machine_checked**。

该函数用于围绕中心点(medoids)的划分聚类，是K-means的更稳健版本。输入可为数值/逻辑型数据矩阵或数据框（行=观测、列=变量），也可为相异度矩阵或对象（如daisy、dist的输出）或长度为n*(n-1)/2的向量。需指定簇数k（小于观测数）。支持欧氏与曼哈顿距离，可标准化变量、指定初始中心点、随机重启及多种算法变体。输出为"pam"类聚类对象，或cluster.only=TRUE时仅返回聚类向量。注意内存与时间均为O(n^2)，且n有65536的硬上限。

### 函数接口

```r

pam(x, k, diss = inherits(x, "dist"),
    metric = c("euclidean", "manhattan"), %% FIXME: add "jaccard"
    medoids = if(is.numeric(nstart)) "random",
    nstart = if(variant == "faster") 1 else NA,
    stand = FALSE, cluster.only = FALSE,
    do.swap = TRUE,
    keep.diss = !diss && !cluster.only && n < 100,
    keep.data = !diss && !cluster.only,
    variant = c("original", "o_1", "o_2", "f_3", "f_4", "f_5", "faster"),
    pamonce = FALSE, trace.lev = 0)

```

参数：x, k, diss, metric, medoids, nstart, stand, cluster.only, do.swap, keep.diss, keep.data, pamonce, variant, trace.lev

### 适用条件与输出

- **input**：x 可为数据矩阵或数据框，每行对应一个观测、每列对应一个变量；所有变量必须为数值型或逻辑型。
- **input**：x 也可为相异度矩阵或对象（通常是 daisy 或 dist 的输出），或长度为 n*(n-1)/2 的向量。
- **input**：当 x 为矩阵或数据框时允许缺失值，只要每对观测至少有一个变量不缺失；当 x 为相异度矩阵时不允许缺失值。
- **parameter**：k 是正整数，指定簇数，且必须小于观测数。
- **parameter**：diss 为逻辑标志：TRUE（dist 或相异度对象的默认值）时 x 视为相异度矩阵，FALSE 时视为观测×变量矩阵。
- **parameter**：metric 可选 "euclidean" 或 "manhattan"；若 x 已是相异度矩阵则该参数被忽略。
- **preprocessing**：stand=TRUE 时在计算相异度前对每个变量（列）标准化，即减去变量均值并除以变量的平均绝对偏差；若 x 已是相异度矩阵则被忽略。
- **parameter**：medoids 可为 NULL（默认，使用 build 算法）或长度为 k 的整数索引向量（在 1:n 内）指定初始中心点；nstart 仅在 medoids="random" 时用于指定随机重启次数。
- **parameter**：variant 是 pamonce 的更自文档化版本，应优先使用；"faster" 使用 pamonce=6 且默认 nstart=1、medoids="random"。
- **output**：返回类 "pam" 的聚类对象；当 cluster.only=TRUE 时仅返回（可能带名称的）整数聚类向量，等价于 pam(x,k)$clustering 但计算更高效。
- **failure**：对于大数据集，pam 可能因内存或计算时间（均为 O(n^2)）不足而受限，此时 clara() 更可取；且存在 n <= 65536 的硬上限。

### 未知与待复核

- 文档未说明该函数对任何特定用户数据集的适用性，也未给出样本量阈值、正态性或独立性等推断性假设要求。
- 文档未说明聚类质量或最优簇数 k 的判定标准（仅提及可用 silhouette 宽度辅助选择）。
- 文档未说明 do.swap=FALSE 或不同 pamonce/variant 设置对最终聚类结果质量的具体影响程度。

[官方源码包](https://cran.r-project.org/src/contrib/cluster_2.1.8.3.tar.gz)；文档 `cluster/man/pam.Rd`。

画像版本：`db3589d99baed8a32dcfef47c06df3d2cce8804b124dbabbfbc5b037758a00c9`。逐条原文证据和参数说明见同名 JSON。

## psych::principal

版本：2.6.9；状态：**needs_review**。

该函数用于主成分分析(PCA)：对相关矩阵或协方差矩阵做特征值分解，提取指定数量的成分，返回特征值、载荷、拟合度及(可选)残差相关与成分得分。输入可为相关矩阵或原始数据矩阵(自动按成对删除求相关)。支持多种旋转/变换、缺失值插补、观测权重及多种相关类型。注意旋转后的成分不再是严格意义上的主成分，且部分统计量更适合因子分析、仅供比较。

### 函数接口

```r

principal(r, nfactors = 1, residuals = FALSE,rotate="varimax",n.obs=NA, covar=FALSE,
 scores=TRUE,missing=FALSE,impute="median",oblique.scores=TRUE,method="regression",
 use ="pairwise",cor="cor",correct=.5,weight=NULL,n.rotations=1,
hyper=.15,...)

```

参数：r, nfactors, residuals, rotate, n.obs, covar, scores, missing, impute, oblique.scores, method, weight, use, cor, correct, n.rotations, hyper, ...

### 适用条件与输出

- **input**：输入 r 可为相关矩阵；若提供原始数据矩阵，则使用成对删除处理缺失值后求相关。
- **input**：covar=FALSE 时从原始数据求相关矩阵，或将输入的方阵转换为相关矩阵。
- **parameter**：nfactors 指定要提取的成分数量；residuals=TRUE 时报告残差相关。
- **parameter**：rotate 可选 "none"、"varimax"、"quartimax"、"promax"、"oblimin"、"simplimax"、"cluster" 等旋转/变换。
- **parameter**：cor 参数可选择 Pearson("cor")、协方差("cov")、tetrachoric("tet")、polychoric("poly")、mixed(mixedCor 混合)以及 Yuleb、Yuleq、YuleY 等 Yule 系数。
- **parameter**：scores=TRUE 且 missing=TRUE 时，用中位数或均值(impute="median"/"mean")插补缺失值。
- **parameter**：weight 若非 NULL，为长度 n.obs 的每观测权重向量；NULL 等价于所有观测权重为 1。
- **preprocessing**：use 参数控制缺失数据处理方式，默认 use="pairwise"，其他选项见 cor。
- **output**：返回特征值(values)、载荷矩阵(loadings)、模型对相关矩阵的拟合(fit)、非对角元素复现程度(fit.off)、残差矩阵(若请求)及自由度(dof)。
- **output**：scores=TRUE 时报告成分得分估计；回归权重由相关矩阵的逆乘以载荷求得，且基于结构矩阵(Structure matrix)而非模式矩阵(Pattern matrix)。
- **output**：若请求斜交旋转(如 oblimin)，返回成分间相关 Phi；rot.mat 为产生旋转载荷的旋转矩阵。
- **failure**：旋转后的主成分不再是特征值分解对应的主成分，而仅是成分(标记为 RCi/TCi)；部分统计量更适合最大似然因子分析，仅供比较。

### 未知与待复核

- 文档未说明对样本量、变量分布(如正态性)或变量间独立性的任何要求。
- 文档未说明该函数对任意特定用户数据集的适用性，也未给出成分数量选择的统计准则(需借助 VSS、fa.parallel 等)。
- 文档未说明 tetrachoric/polychoric/mixed 相关在空单元格处理(correct 参数)之外的具体适用条件。
- 复核意见：claim 'cor 参数可选择...Yuleb、Yuleq、YuleY 等 Yule 系数' 的表述不准确：原文为 'Yuleb is Yulebonett, Yuleq and YuleY are the obvious Yule coefficients as appropriate'，即 Yuleb 对应 Yulebonett 系数，Yuleq 与 YuleY 是相应的 Yule 系数，并非三种都叫 Yule 系数。请修正为 Yuleb(Yulebonett)、Yuleq、YuleY 等。
- 复核意见：claim 'scores=TRUE 时报告成分得分估计；回归权重由相关矩阵的逆乘以载荷求得' 中，回归权重公式表述不完整：原文为 'R^(-1) lambda'，即相关矩阵的逆乘以载荷矩阵，且该回归权重基于结构矩阵(Structure matrix)而非模式矩阵。当前表述将'基于结构矩阵'与'相关矩阵的逆乘以载荷'并列，但原文明确指出回归权重由结构矩阵求得，请明确回归权重基于结构矩阵。
- 复核意见：claim '返回特征值(values)、载荷矩阵(loadings)、模型对相关矩阵的拟合(fit)、非对角元素复现程度(fit.off)、残差矩阵(若请求)及自由度(dof)' 中，将 fit 表述为'模型对相关矩阵的拟合'不够准确：原文为 'fit Fit of the model to the correlation matrix'，可接受，但 fit.off 原文为 'how well are the off diagonal elements reproduced?'，表述为'非对角元素复现程度'可接受。此条无实质问题。
- 复核意见：claim '若请求斜交旋转(如 oblimin)，返回成分间相关 Phi' 中，原文为 'Phi If oblique rotations (using oblimin from the GPArotation package) are requested, what is the interfactor correlation.'，表述为'成分间相关'可接受，但原文用词为 interfactor correlation(因子间相关)，建议保留'因子间相关'以忠实原文。

[官方源码包](https://cran.r-project.org/src/contrib/psych_2.6.9.tar.gz)；文档 `psych/man/principal.Rd`。

画像版本：`813e43d235e0d26c3bb71936986a9b69a3dff11379477401c2c1518a42bb015b`。逐条原文证据和参数说明见同名 JSON。
