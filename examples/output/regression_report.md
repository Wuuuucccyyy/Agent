# 统计分析基线报告

研究目标：线性回归

任务：regression；样本：8；变量：3。
数据 SHA256：`da223769af11576cb785b1c2d21663e8a07bc2b4a5f70340be429ee0007f68d3`

检索后端：`tfidf_char_lexical_smoke_only`；状态：`ranked`。

| 方法 | 余弦分数 | 软惩罚 | 最终分数 |
|---|---:|---:|---:|
| stats::lm | 0.3902 | 0.0000 | 0.3902 |

## 执行与数值验证

状态：`success`；数值校验通过：`True`。
OLS finite coefficients and least-squares orthogonality checked.

```json
{
  "coefficients": {
    "intercept": 1.999999999999998,
    "x1": 3.0000000000000013,
    "x2": -1.000000000000002
  },
  "r_squared": 1.0,
  "sse": 9.668476469615026e-29,
  "predictions": [
    1.999999999999998,
    4.999999999999999,
    0.999999999999996,
    3.9999999999999973,
    6.999999999999998,
    2.999999999999995,
    11.000000000000002,
    4.999999999999994
  ],
  "residuals": [
    1.9984014443252818e-15,
    8.881784197001252e-16,
    3.9968028886505635e-15,
    2.6645352591003757e-15,
    1.7763568394002505e-15,
    4.884981308350689e-15,
    -1.7763568394002505e-15,
    6.217248937900877e-15
  ]
}
```

## 限制与待确认条件

- measurement_scales
- independence
- pairing
- sampling
- repeated_measures
- missingness_mechanism
- In-sample fit only, not predictive validation.
- No p-values or causal claims: independence, heteroscedasticity and residual assumptions remain unchecked.
- Python least squares template; R lm was not executed.
- Study design and independence have not been verified.
- Linearity, homoscedasticity and residual distribution require model-specific diagnostics.

## 被排除的方法

- stats::prcomp: Task regression is outside stats::prcomp's supported tasks.
- stats::kmeans: Task regression is outside stats::kmeans's supported tasks.
- stats::manova: Task regression is outside stats::manova's supported tasks.
- MASS::lda: Task regression is outside MASS::lda's supported tasks.

此报告来自规则与确定性工具基线。数值校验不等于统计假设成立。完整证据与诊断见 JSON 文件。
