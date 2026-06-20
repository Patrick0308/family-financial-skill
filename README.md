# family-finance-skill 家庭财务记录技能

> A portable **Agent Skill** for tracking family finances in natural language — auto-generates a balance sheet, income/expense statement, and cash-flow statement, plus a financial-health score and wealth tier.

用自然语言记录家庭财务状况的 **Agent Skill**：你只管口头报账、报余额，技能自动整理成三张规范报表，给出财务健康评分和家庭财富等级，还能按市价估值资产、对大额消费给可行性建议。

计算由一个 **Python 标准库脚本**（零第三方依赖）完成，保证金额、合计、净值、评分都准确，不靠模型手算。

## 能做什么

- 🧾 **家庭资产负债表** —— 某时点的资产、负债、净资产
- 💸 **收入支出表** —— 当期收入、支出、月结余
- 🌊 **现金流表** —— 日常收支 / 投资进出 / 借还款三类净现金流
- 🩺 **财务健康评分** —— 0–100 分 + 等级 + 通用理财建议（基于结余率、负债率、应急储备等指标）
- 🏅 **家庭财富等级** —— 以「可投资净资产」为主轴分档（阈值对齐招行/贝恩、胡润报告口径）
- 💹 **资产估值** —— 录入股票/基金持仓、房产信息，按当前行情/区域均价折算人民币市值，报表标注来源与置信度
- 🛒 **大额消费咨询** —— 「想买 X 万的车，合适吗？」基于你的财务状态判定可承受/谨慎/暂不建议，全款看应急储备、分期看现金面+还款面，并给可落地临界值

## 怎么用

记录与出表都用自然语言触发：

| 你说 | 技能做什么 |
|---|---|
| 「记一笔：今天买菜 120」 | 追加一行流水（自动判断 支出/经营/餐饮） |
| 「工资到账 20000」 | 追加流水（收入/经营/工资） |
| 「更新余额：房贷剩 80 万、活期 5 万」 | 写一组资产负债快照 |
| 「加持仓：腾讯 500 股」「房子，南山某小区 89 平自住」 | 记录持仓/房产，待估值 |
| 「刷新估值」 | 按当前行情/汇率/区域均价折算人民币写入快照 |
| 「想买 35 万的车，分期 36 期，合适吗？」 | 给可承受/谨慎/暂不建议 + 关键数字 + 临界值 |
| 「出 6 月的表」 | 生成 `reports/2026-06.md`（三表 + 评分 + 等级） |

数据以 CSV 存在你指定的目录（`transactions.csv` 流水、`balances.csv` 资产负债快照、`holdings.csv` 持仓、`properties.csv` 房产），报表输出到 `reports/`。可版本管理、可离线、可用 Excel/飞书打开。含持仓与住址的文件不会进版本库。

## 安装

这是符合 [Agent Skills](https://www.anthropic.com/news/skills) 规范的技能（`SKILL.md` + frontmatter），可用于 Claude Code、Copilot CLI、Gemini CLI、Codex 等支持该格式的 agent。

**一行命令安装**（用 [`skills`](https://www.npmjs.com/package/skills) CLI，自动识别并装到你所用各 agent 的技能目录）：

```bash
npx skills add Patrick0308/family-financial-skill
```

它会下载本仓库、识别 `SKILL.md`，并安装到检测到的 agent（Claude Code、Cursor、Copilot、Codex 等）对应目录。常用参数：

```bash
npx skills add Patrick0308/family-financial-skill -g            # 全局安装（所有项目可用）
npx skills add Patrick0308/family-financial-skill -a claude-code # 只装到指定 agent
npx skills update                                                # 更新已装技能
npx skills remove family-finance                                # 卸载
```

> 装好后在 agent 里直接说「记一笔…」「出 X 月的表」即可触发。运行只需本机有 `python3`（macOS 自带）；`pytest` 仅开发期需要。

**不想用 CLI？** 也可以用 [`degit`](https://github.com/Rich-Harris/degit) 直接拉到某个 agent 的技能目录：

```bash
npx degit Patrick0308/family-financial-skill ~/.claude/skills/family-finance   # Claude Code 个人级
npx degit Patrick0308/family-financial-skill .claude/skills/family-finance     # 当前项目级
```

## 直接用脚本（不经 agent）

```bash
# 准备数据
cp assets/transactions.csv ./transactions.csv
cp assets/balances.csv ./balances.csv
# 编辑后出表
python3 scripts/family_finance.py report 2026-06 --data-dir .
cat reports/2026-06.md

# 大额消费评估（全款 / 分期 / 含首付）
python3 scripts/family_finance.py afford --amount 350000 --mode lump --data-dir .
python3 scripts/family_finance.py afford --amount 350000 --mode installment --months 36 --down 100000 --data-dir .
```

## 样例报表

```markdown
# 2026-06 家庭财务报表

## 一、资产负债表
- 资产合计：¥2,200,000　负债合计：¥510,000　**净资产：¥1,690,000**

## 二、收入支出表
- 收入合计：¥21,000　支出合计：¥8,000　**月结余：¥13,000**

## 三、现金流表
| 项目 | 金额 |
| --- | --- |
| 日常收支净额（经营） | ¥12,000 |
| 投资进出净额（投资） | -¥9,000 |
| 借还款净额（筹资） | -¥4,000 |
| **当月现金净变动** | **-¥1,000** |

## 四、财务健康评分
**综合评分：95 / 100（优秀）**

## 五、家庭财富等级
**小康**（可投资净资产 ¥190,000；总净资产 ¥1,690,000），距「宽裕」还差 ¥310,000
```

> 资产估值与消费咨询另有独立输出（报表会标注估算项，消费评估通过 `afford` 命令或自然语言触发）。

## 自定义

- **分类**：编辑 [`references/categories-default.md`](references/categories-default.md)
- **评分阈值与权重**：见 [`references/scoring.md`](references/scoring.md)，与 `scripts/family_finance.py` 中的常量对应，改了两处要一起改并更新测试
- **财富等级分档**：见 [`references/wealth-tiers.md`](references/wealth-tiers.md)（阈值对齐招行/贝恩、胡润报告，可按地区调整）
- **估值口径**：见 [`references/valuation.md`](references/valuation.md)（代码后缀、汇率、置信度、隐私约束）
- **消费评估口径**：见 [`references/affordability.md`](references/affordability.md)（一次性/分期判定、现金面+还款面、临界值）

## 开发

```bash
uvx pytest scripts/ -v   # 或 pip install pytest 后 python3 -m pytest scripts/ -v
```

## 免责声明

本技能是家庭自助记账工具。评分与财富等级为**通用参考**，**不构成个性化投资建议**，作者非持牌财务顾问。所有数据仅存于你本地。币种为人民币（¥），单币种。

## License

[MIT](LICENSE) © 2026 白泽
