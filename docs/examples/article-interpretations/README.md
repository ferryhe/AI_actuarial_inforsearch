# 人工审校解读样稿

这里收录三篇经过人工逐条核对和编辑的中文草稿，供阅读与审查。它们尚未作为系统已通过稿件保存，也未在公众号发表。正文原样保留人工审校稿的文字与阅读链接。

| 类型 | 中文样稿 | 原文与国内阅读 |
| --- | --- | --- |
| 方法综述 | [机器学习怎样补充精算模型：从变量分箱到风险预测](human-reviewed-drafts.md#样稿一) | [Machine Learning Applications in Insurance](https://www.casact.org/sites/default/files/2022-03/01_Winter-Eforum-2022-ML_in_Insurance.pdf) · [国内阅读](https://aiactuary.cn/file-detail?file_id=1386) |
| 案例 | [从退保概率到客户联系：一项互助保险会员留存实践](human-reviewed-drafts.md#样稿二) | [Machine Learning for Health Insurance Member Retention: A Case Study](https://www.institutdesactuaires.com/global/gene/link.php?doc_id=17510&fg=1) · [国内阅读](https://aiactuary.cn/file-detail?file_id=2823) |
| 研究 | [健康险反欺诈模型如何解释：从变量贡献到交互关系](human-reviewed-drafts.md#样稿三) | [Interpretable Machine Learning for Health Insurance Fraud Detection](https://www.soa.org/globalassets/assets/files/resources/research-report/2024/interpretable-ml-methods.pdf) · [国内阅读](https://aiactuary.cn/file-detail?file_id=1374) |

## 本地排版预览

`method.md`、`case.md`、`research.md` 分别对应三篇人工审校样稿；同名 `.html` 文件用于本地浏览器预览。排版约定见 [layout.md](layout.md)。这些 HTML 仅用于本地查看，微信编辑器粘贴效果尚未验证。

## 关键编辑说明

- 方法稿：按原文重写研究背景与GLM相关表述；将预测表现与复杂度的权衡明确列为编辑归纳，不冒充原文通用标准。
- 案例稿：将交易数纠正为284,807；保留原文0.142%并披露整数复算约0.173%的不一致；34%、57%、8%合计99%，未擅自归一化。移除无原文依据的年龄方向，按原文写为对电话联系较敏感的年龄段；会员留存项目与另一个Kaggle信用卡欺诈演示分开叙述，电话联系结果也没有写成已证实的因果收益。
- 研究稿：删除没有原文支撑的方法清单和外部验证断言，按原文区分三组解释方法；将编辑建议、模型输出和因果结论分开。开头统计明确标为报告引用的外部数字，不作独立核实的现状结论。

## OpenML补充核对的边界

案例稿末尾的OpenML说明是独立的外部数据目录交叉核对，不是法国原文引用，也不是会员留存项目的数据。目录的0.172%、原文的0.142%和编辑复算的约0.173%分别注明，未相互替换。它们不能被解读为已核实的健康保险欺诈率。
