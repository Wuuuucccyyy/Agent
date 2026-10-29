# 独立来源参考：第一阶段

请先只阅读 sources.json，在 reference.template.json 的副本中编写参考事实。
不要先看候选画像、旧复核意见或 candidate_items。当前目录不包含候选内容。
每个函数覆盖 task、input、roles、parameters、conditions、output、unknowns 七个方面；
没有在文档建立的事实写为 not_established，说明范围和理由，不补造假设。
documented / derived 必须引用本包对应函数原文；derived 还应解释推导。
事实的 required 字段决定后续完整率分母，必须在看候选之前确定。
完成后填写真实复核身份、日期、独立性与 source-only 声明，设置 scope_complete=true。

用 kb review freeze 固定参考后，再用 kb review form 获取候选对照表。
原文继承对应 CRAN 许可，见仓库 database/LICENSE-CRAN-DERIVED.txt。
此材料由程序整理，所有答案留空；本目录的存在不表示人工复核已经完成。
