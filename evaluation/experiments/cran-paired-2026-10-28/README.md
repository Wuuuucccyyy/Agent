# CRAN 配对画像生成实验（2026-10-28）

真实 DeepSeek 调用结果；本目录不是生产知识库，也不是独立人工参考答案。

[实验设计与解读](../../../docs/PROFILE_COMPARISON.md) · [汇总](summary.json) · [固定计划](plan.json)

实际合计 20 次 API 调用、102,166 Token；两组共享初稿，不应将两组消耗相加。

| 函数与完整记录 | 协作组最后状态 |
|---|---|
| [MASS::lda](cases/a3ecd3675a433eaef955b03c08b62e6aaa6c7f1f565b11559080390cc4f77c64.json) | machine_accepted |
| [MASS::lm.ridge](cases/cc8fa9376cb808106265c9089cbba35a903e727d287e26fad3acb3dada1e7ba3.json) | machine_accepted |
| [MASS::qda](cases/26de659413331d0b8dcb96221cf1a6d7e1609f5503c47ce441f610c9dcddc865.json) | machine_accepted |
| [cluster::agnes](cases/68c35c49cdeb98b79f803dfac1f17054eaf8d5f55effa05a9b3495aba722d65f.json) | machine_accepted |
| [cluster::clara](cases/d87da3b9eb18e5f630cc3be6cf5fa4a8af823f6e308f37441a75eee715be35e4.json) | needs_review |
| [cluster::diana](cases/179e0be63046150714925dd4294724f80bf26382059c3a33fe0ba7ef531e0d89.json) | machine_accepted |
| [cluster::pam](cases/e72ff6e4eef87f51a5c8c5e99b182a9e7ba9d7e0a2ed5e18043e81ec74070610.json) | machine_accepted |
| [psych::principal](cases/756d157b32c09426c5ca76dbe7a3763d25044c04a3315243fa3c031f8270704b.json) | needs_review |

所有人工语义准确率均待独立参考和标注；machine_accepted 只是同模型复核结论。
原文及改编画像遵循 [CRAN 来源许可](../../../database/LICENSE-CRAN-DERIVED.txt)。
