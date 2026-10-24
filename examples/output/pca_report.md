# 统计分析基线报告

研究目标：主成分分析

任务：pca；样本：8；变量：3。
数据 SHA256：`1cbad5d80c3bcf724ffcadac6a7d6ffe3bdb009134116af31f50c3eb403c0387`

检索后端：`tfidf_char_lexical_smoke_only`；状态：`ranked`。

| 方法 | 余弦分数 | 软惩罚 | 最终分数 |
|---|---:|---:|---:|
| stats::prcomp | 0.2350 | 0.0000 | 0.2350 |

## 执行与数值验证

状态：`success`；数值校验通过：`True`。
PCA reconstruction and variance accounting checked.

```json
{
  "explained_variance": [
    2.590696833288521,
    0.3359096300384515,
    0.07339353667302742
  ],
  "explained_variance_ratio": [
    0.8635656110961736,
    0.11196987667948381,
    0.02446451222434247
  ],
  "loadings": [
    [
      0.6062102442695286,
      -0.0761055935968914,
      0.7916546458942457
    ],
    [
      0.5559348087424932,
      0.7523696076833866,
      -0.35337863809629844
    ],
    [
      0.568722804335404,
      -0.6543301246753142,
      -0.49840391227523667
    ]
  ],
  "scores": [
    [
      -1.781863792719314,
      -0.25844535845538086,
      -0.465296415440897
    ],
    [
      -1.9935190447308175,
      -0.3295397882720554,
      0.20563401041933208
    ],
    [
      -1.2973365556284124,
      0.8279802064461097,
      0.2994995367225134
    ],
    [
      -0.5802713571689455,
      -0.31163084256137913,
      0.15653978199527607
    ],
    [
      0.8072307924474229,
      0.6187844486950891,
      -0.300806006884538
    ],
    [
      1.0651564430106695,
      -0.560851051648406,
      -0.09602699157564665
    ],
    [
      1.761338932113075,
      0.596668943069759,
      -0.0021614652724656147
    ],
    [
      2.0192645826763216,
      -0.5829665572737361,
      0.2026175500364258
    ]
  ],
  "components_for_95_percent": 2
}
```

## 限制与待确认条件

- measurement_scales
- independence
- pairing
- sampling
- repeated_measures
- missingness_mechanism
- Python SVD equivalent to centered, scaled PCA; no R runtime was invoked.
- Exploratory summary only; study design and feature meaning are not verified.
- Study design and independence have not been verified.
- Scaling and feature selection need scientific justification; PCA needs no marginal normality assumption.

## 被排除的方法

- stats::lm: Task pca is outside stats::lm's supported tasks.
- stats::kmeans: Task pca is outside stats::kmeans's supported tasks.
- stats::manova: Task pca is outside stats::manova's supported tasks.
- MASS::lda: Task pca is outside MASS::lda's supported tasks.

此报告来自规则与确定性工具基线。数值校验不等于统计假设成立。完整证据与诊断见 JSON 文件。
