# family-finance-skill 家庭财务记录技能

> A portable **Agent Skill** for tracking family finances in natural language — auto-generates a balance sheet, income/expense statement, and cash-flow statement, plus a financial-health score and wealth tier.

用自然语言记录家庭财务状况的 **Agent Skill**：你只管口头报账、报余额，技能自动整理成三张规范报表，并给出财务健康评分和家庭财富等级。

计算由一个 **Python 标准库脚本**（零第三方依赖）完成，保证金额、合计、净值、评分都准确，不靠模型手算。

## 能做什么

- 🧾 **家庭资产负债表** —— 某时点的资产、负债、净资产
- 💸 **收入支出表** —— 当期收入、支出、月结余
- 🌊 **现金流表** —— 经营 / 投资 / 筹资三类净现金流
- 🩺 **财务健康评分** —— 0–100 分 + 等级 + 通用理财建议（基于结余率、负债率、应急储备等指标）
- 🏅 **家庭财富等级** —— 以「可投资净资产」为主轴分档

## 怎么用

记录与出表都用自然语言触发：

| 你说 | 技能做什么 |
|---|---|
| 「记一笔：今天买菜 120」 | 追加一行流水（自动判断 支出/经营/餐饮） |
| 「工资到账 20000」 | 追加流水（收入/经营/工资） |
| 「更新余额：房贷剩 80 万、活期 5 万」 | 写一组资产负债快照 |
| 「出 6 月的表」 | 生成 `reports/2026-06.md`（三表 + 评分 + 等级） |

数据以 CSV 存在你指定的目录（`transactions.csv` 流水、`balances.csv` 资产负债快照），报表输出到 `reports/`。可版本管理、可离线、可用 Excel/飞书打开。

## 安装

这是符合 [Agent Skills](https://www.anthropic.com/news/skills) 规范的技能（`SKILL.md` + frontmatter），可用于 Claude Code、Copilot CLI、Gemini CLI、Codex 等支持该格式的 agent。

**一行命令安装**（用 [`degit`](https://github.com/Rich-Harris/degit) 拉取，无需 clone 历史）——把技能装进你所用 agent 的技能目录即可：

```bash
# Claude Code（个人级）
npx degit Patrick0308/family-financial-skill ~/.claude/skills/family-finance
```

其它 agent 同理，只改目标目录：

| Agent | 目标目录 |
|---|---|
| Claude Code（个人） | `~/.claude/skills/family-finance` |
| Claude Code（项目级） | `.claude/skills/family-finance` |
| Gemini CLI | `~/.gemini/skills/family-finance` |
| Codex / 其它 | 该 agent 的技能/扩展目录下 `family-finance` |

```bash
# 例：装到当前项目（任何支持 .claude/skills 的工具）
npx degit Patrick0308/family-financial-skill .claude/skills/family-finance
```

> **说明**：各 agent 查找技能的目录不同，没有跨所有 agent 的统一路径，所以用「同一条 `npx` 命令 + 各自的技能目录」来覆盖。Copilot CLI 走插件机制，按其插件方式引入本仓库即可。
>
> 装好后在 agent 里直接说「记一笔…」「出 X 月的表」即可触发。运行只需本机有 `python3`（macOS 自带）；`pytest` 仅开发期需要。

**更新到最新版**：对同一目录重跑上面的 `npx degit … --force` 即可。

## 直接用脚本（不经 agent）

```bash
# 准备数据
cp assets/transactions.csv ./transactions.csv
cp assets/balances.csv ./balances.csv
# 编辑后出表
python3 scripts/family_finance.py report 2026-06 --data-dir .
cat reports/2026-06.md
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
| 经营性净现金流 | ¥12,000 |
| 投资性净现金流 | -¥9,000 |
| 筹资性净现金流 | -¥4,000 |
| **净现金流合计** | **-¥1,000** |

## 四、财务健康评分
**综合评分：95 / 100（优秀）**

## 五、家庭财富等级
**稳健**（可投资净资产 ¥190,000；总净资产 ¥1,690,000），距「小康」还差 ¥810,000
```

## 自定义

- **分类**：编辑 [`references/categories-default.md`](references/categories-default.md)
- **评分阈值与权重**：见 [`references/scoring.md`](references/scoring.md)，与 `scripts/family_finance.py` 中的常量对应，改了两处要一起改并更新测试
- **财富等级分档**：见 [`references/wealth-tiers.md`](references/wealth-tiers.md)（默认值为经验分档，非官方标准，建议按地区调整）

## 开发

```bash
uvx pytest scripts/ -v   # 或 pip install pytest 后 python3 -m pytest scripts/ -v
```

## 免责声明

本技能是家庭自助记账工具。评分与财富等级为**通用参考**，**不构成个性化投资建议**，作者非持牌财务顾问。所有数据仅存于你本地。币种为人民币（¥），单币种。

## License

[MIT](LICENSE) © 2026 白泽
