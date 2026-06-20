# 资产价格评估能力 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 `family-financial` 技能增加资产估值能力——用户录入持仓/房产，agent 联网查行情/均价折算人民币写入快照，报表标注估算来源与置信度。

**Architecture:** 估值的「查询/折算」由 agent（Claude）在记录时完成并写入 CSV；Python 脚本只新增「读取溯源列 + 报表标注」，保持零联网、零第三方依赖、可单测。新增 `holdings.csv`/`properties.csv` 作为持仓/房产输入清单（agent 用，脚本不解析）。

**Tech Stack:** Python 3 标准库；pytest（`uvx pytest` 运行，host python3 无 pytest）；Markdown。

参考规格：`docs/superpowers/specs/2026-06-20-asset-valuation-design.md`

---

## 文件结构

```
family-financial/
├── scripts/family_finance.py        # 改：Bal +3 字段、load_balances 读新列、render_report 标注
├── scripts/test_family_finance.py   # 改：新增测试
├── assets/holdings.csv              # 新：持仓模板
├── assets/properties.csv           # 新：房产模板
├── references/valuation.md         # 新：估值口径/代码后缀/置信度/隐私
├── SKILL.md                        # 改：新增估值工作流
└── .gitignore                      # 改：忽略根目录 holdings.csv/properties.csv
```

**说明：** 估值查询逻辑是 **agent 行为**（写在 SKILL.md / valuation.md），不是脚本代码，因此没有对应单测；可单测的只有脚本侧的「溯源列读取 + 报表标注」。

---

## Task 1: Bal 增溯源字段 + load_balances 读取

**Files:**
- Modify: `scripts/family_finance.py`（`Bal` 约 :29-37，`load_balances` 约 :46-58）
- Test: `scripts/test_family_finance.py`

- [ ] **Step 1: 写失败测试**（追加到测试文件末尾；复用文件顶部已有的 `_write_csv` 助手）

```python
def test_load_balances_reads_provenance_columns(tmp_path):
    p = tmp_path / "balances.csv"
    _write_csv(
        p,
        ["日期", "类型", "项目", "金额", "流动性", "性质", "来源", "估值日期", "置信度"],
        [["2026-06-30", "资产", "腾讯", "165400", "流动", "可投资", "行情", "2026-06-20", "高"]],
    )
    b = load_balances(str(p))[0]
    assert b.source == "行情"
    assert b.valued_at == "2026-06-20"
    assert b.confidence == "高"


def test_load_balances_without_provenance_columns_still_works(tmp_path):
    # 旧格式（无新列）必须照常加载，新字段为空
    p = tmp_path / "balances.csv"
    _write_csv(
        p,
        ["日期", "类型", "项目", "金额", "流动性", "性质"],
        [["2026-06-30", "资产", "活期", "50000", "流动", "可投资"]],
    )
    b = load_balances(str(p))[0]
    assert b.amount == 50000.0
    assert b.source == "" and b.valued_at == "" and b.confidence == ""
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `uvx pytest scripts/test_family_finance.py -k "provenance" -v`
Expected: FAIL，`AttributeError: 'Bal' object has no attribute 'source'`

- [ ] **Step 3: 改实现**

`Bal` dataclass 增 3 个默认空字段：

```python
@dataclass
class Bal:
    date: str
    kind: str          # 资产 / 负债
    item: str
    amount: float
    liquidity: str = ""  # 流动 / 非流动
    nature: str = ""     # 可投资 / 自用
    source: str = ""     # 来源: 行情 / 搜索 / 手填
    valued_at: str = ""  # 估值日期 YYYY-MM-DD
    confidence: str = "" # 置信度: 高 / 中 / 低
```

`load_balances` 读取新列（仍用 `.get(..., "")` 兼容旧文件）。把构造 `Bal` 的那一行扩展为：

```python
            out.append(Bal(
                r["日期"], r["类型"], r["项目"], float(r["金额"]),
                r.get("流动性", "") or "", r.get("性质", "") or "",
                r.get("来源", "") or "", r.get("估值日期", "") or "",
                r.get("置信度", "") or "",
            ))
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `uvx pytest scripts/test_family_finance.py -k "provenance" -v`
Expected: 2 passed

- [ ] **Step 5: 全量回归**

Run: `uvx pytest scripts/ -q`
Expected: 全部 passed（旧测试不受影响，因新字段有默认值）

- [ ] **Step 6: Commit**

```bash
git add scripts/family_finance.py scripts/test_family_finance.py
git commit -m "feat: Bal 增估值溯源字段（来源/估值日期/置信度），load_balances 兼容读取"
```

---

## Task 2: 报表标注估值来源与置信度

**Files:**
- Modify: `scripts/family_finance.py`（新增 `_valuation_note`；`render_report` 资产表段约 :315-323；免责段约 :373-375）
- Test: `scripts/test_family_finance.py`

标注规则：
- 来源为空或「手填」→ 无标注
- 来源「行情」→ `（行情·YYYY-MM-DD）`
- 来源「搜索」→ ` ⚠估（搜索·YYYY-MM-DD·置信度）`
- 通用：拼 `来源·估值日期·置信度`（缺项跳过），搜索类前面加 ` ⚠估`
- 若快照中存在来源为「行情」或「搜索」的资产，免责区追加一行估值说明

- [ ] **Step 1: 写失败测试**

```python
def test_valuation_note_formats():
    from scripts.family_finance import _valuation_note
    quote = Bal("2026-06-30", "资产", "腾讯", 165400, "流动", "可投资",
                "行情", "2026-06-20", "高")
    est = Bal("2026-06-30", "资产", "投资房", 2000000, "非流动", "可投资",
              "搜索", "2026-06-18", "低")
    manual = Bal("2026-06-30", "资产", "活期", 50000, "流动", "可投资")
    assert _valuation_note(quote) == "（行情·2026-06-20·高）"
    assert _valuation_note(est) == " ⚠估（搜索·2026-06-18·低）"
    assert _valuation_note(manual) == ""


def test_render_report_annotates_estimated_assets():
    snap = [
        Bal("2026-06-30", "资产", "活期", 50000, "流动", "可投资"),
        Bal("2026-06-30", "资产", "腾讯", 165400, "流动", "可投资",
            "行情", "2026-06-20", "高"),
        Bal("2026-06-30", "资产", "投资房", 2000000, "非流动", "可投资",
            "搜索", "2026-06-18", "低"),
    ]
    md = render_report("2026-06", snap, [])
    assert "腾讯（行情·2026-06-20·高）" in md
    assert "投资房 ⚠估（搜索·2026-06-18·低）" in md
    assert "活期 |" in md  # 手填项无标注，项目名后直接是表格分隔
    assert "区域均价粗估" in md  # 估值免责行出现


def test_render_report_no_valuation_disclaimer_when_all_manual():
    snap = [Bal("2026-06-30", "资产", "活期", 50000, "流动", "可投资")]
    md = render_report("2026-06", snap, [])
    assert "区域均价粗估" not in md
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `uvx pytest scripts/test_family_finance.py -k "valuation_note or annotates or no_valuation" -v`
Expected: FAIL，`ImportError: cannot import name '_valuation_note'`

- [ ] **Step 3: 改实现**

(a) 在 `_yuan` 附近新增 `_valuation_note`：

```python
def _valuation_note(b):
    if not b.source or b.source == "手填":
        return ""
    parts = [b.source]
    if b.valued_at:
        parts.append(b.valued_at)
    if b.confidence:
        parts.append(b.confidence)
    mark = " ⚠估" if b.source == "搜索" else ""
    return f"{mark}（{'·'.join(parts)}）"
```

(b) `render_report` 资产负债表段：把构造资产/负债行改为直接遍历 `snap`（保留 `bs` 算合计），给资产项目名追加标注。将这段：

```python
    else:
        bs = balance_sheet(snap)
        rows = [("资产", item, _yuan(amt)) for item, amt in bs["资产明细"]]
        rows += [("负债", item, _yuan(amt)) for item, amt in bs["负债明细"]]
        parts.append(_rows_table(["类型", "项目", "金额"], rows))
```

改为：

```python
    else:
        bs = balance_sheet(snap)
        rows = [("资产", b.item + _valuation_note(b), _yuan(b.amount))
                for b in snap if b.kind == "资产"]
        rows += [("负债", b.item, _yuan(b.amount))
                 for b in snap if b.kind == "负债"]
        parts.append(_rows_table(["类型", "项目", "金额"], rows))
```

(c) 免责段：在固定免责行之后，按需追加估值说明行。将这段：

```python
    parts.append("---")
    parts.append("> 免责声明：本报表为家庭自助记录工具，评分与等级为通用参考，"
                 "不构成个性化投资建议；作者非持牌财务顾问。")
    return "\n".join(parts) + "\n"
```

改为：

```python
    parts.append("---")
    parts.append("> 免责声明：本报表为家庭自助记录工具，评分与等级为通用参考，"
                 "不构成个性化投资建议；作者非持牌财务顾问。")
    if any(b.kind == "资产" and b.source in ("行情", "搜索") for b in snap):
        parts.append("> 含市场估值的项目为某时点估算，房产为区域均价粗估，仅供参考。")
    return "\n".join(parts) + "\n"
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `uvx pytest scripts/test_family_finance.py -k "valuation_note or annotates or no_valuation" -v`
Expected: 3 passed

- [ ] **Step 5: 全量回归**

Run: `uvx pytest scripts/ -q`
Expected: 全部 passed（原 `test_render_report_*` 的 snap 无 source，标注为空，不受影响）

- [ ] **Step 6: Commit**

```bash
git add scripts/family_finance.py scripts/test_family_finance.py
git commit -m "feat: 报表标注资产估值来源/置信度，按需追加估值免责"
```

---

## Task 3: 持仓/房产输入模板

**Files:**
- Create: `assets/holdings.csv`
- Create: `assets/properties.csv`

- [ ] **Step 1: 写 holdings.csv（表头 + 一行示例）**

```
代码,名称,市场,份额,资产分类,备注
00700.HK,腾讯控股,港股,0,投资,示例行可删除
```

- [ ] **Step 2: 写 properties.csv（表头 + 一行示例）**

```
项目名,小区或区域,面积㎡,性质,备注
自住房,城市+区域(勿填详细门牌),0,自住,示例行可删除
```

- [ ] **Step 3: Commit**

```bash
git add assets/holdings.csv assets/properties.csv
git commit -m "feat: 持仓与房产输入模板"
```

---

## Task 4: .gitignore 忽略持仓/房产真实数据

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: 追加忽略项**

在 `.gitignore` 的用户数据段（`/transactions.csv` 等所在处）补两行，最终该段为：

```
# 用户真实数据，绝不入库（assets/ 下的空白模板不受影响）
/transactions.csv
/balances.csv
/holdings.csv
/properties.csv
/reports/
data/
```

- [ ] **Step 2: 验证模板仍跟踪、根目录真实数据被忽略**

```bash
git check-ignore assets/holdings.csv assets/properties.csv && echo "BAD: 模板被忽略" || echo "OK: 模板未忽略"
touch holdings.csv properties.csv
git check-ignore holdings.csv properties.csv && echo "OK: 真实数据被忽略" || echo "BAD: 未忽略"
rm -f holdings.csv properties.csv
```
Expected: `OK: 模板未忽略` 与 `OK: 真实数据被忽略`

- [ ] **Step 3: Commit**

```bash
git add .gitignore
git commit -m "fix: .gitignore 忽略根目录 holdings.csv/properties.csv"
```

---

## Task 5: references/valuation.md 估值口径

**Files:**
- Create: `references/valuation.md`

- [ ] **Step 1: 写 references/valuation.md（完整内容）**

```markdown
# 资产估值口径

估值由 agent（Claude）在记账时联网完成并写入 CSV；Python 脚本不联网、不解析本文件。

## 持仓（holdings.csv → balances.csv）
- 代码后缀：A股 沪 `600519.SS` / 深 `000001.SZ`；港股 `00700.HK`；美股 `AAPL`（无后缀）。
- 人民币市值 = 原币现价 × 份额 × 汇率。A股汇率=1；港股取 HKDCNY；美股取 USDCNY（取当日汇率）。
- 写入 balances.csv 时：类型=资产，项目=持仓名称，标签 流动/可投资，
  来源=`行情`，估值日期=行情日期，置信度=`高`。
- 「刷新估值」= 遍历 holdings.csv 按最新价重算，写一组新日期的快照行。

## 房产（properties.csv → balances.csv）
- 仅按「小区/区域」粒度联网搜均价，**不发送详细门牌**。
- 估值 = 区域均价 × 面积，给区间，标 来源=`搜索`、置信度=`低`、附均价出处。
- 标签：自住→非流动/自用；投资→非流动/可投资。

## 置信度
- 高：实时行情（股票/基金）
- 中：行情过期或汇率粗取
- 低：房产区域均价粗估、或本次联网失败沿用旧值

## 错误处理
- 代码/标的不明确 → 向用户确认，不臆填。
- 联网失败 → 保留上次市值，置信度=低 + 旧估值日期，并明确告知未刷新成功。

## 隐私
- holdings.csv / properties.csv 含持仓与住址，属敏感数据，加入 .gitignore，绝不入库。
- 联网只发区域级信息；估值不构成投资建议（不推荐买卖、不做择时）。
```

- [ ] **Step 2: Commit**

```bash
git add references/valuation.md
git commit -m "docs: references 资产估值口径（代码后缀/汇率/置信度/隐私）"
```

---

## Task 6: SKILL.md 增估值工作流

**Files:**
- Modify: `SKILL.md`

- [ ] **Step 1: 在 SKILL.md 的「## 操作」小节中，「### 2. 更新资产负债余额」之后插入新小节**

```markdown
### 2.5 估值（股票/基金/房产）
详细口径见 `references/valuation.md`。

**录入持仓**（用户说「加持仓：腾讯 500 股」）：
1. 解析代码/市场（A股加 .SS/.SZ，港股加 .HK，美股无后缀；不确定则向用户确认）。
2. 追加到 `holdings.csv`（列：代码,名称,市场,份额,资产分类,备注）。

**录入房产**（用户说「房子，南山 XX 小区 89 平，自住」）：
1. 只记小区/区域，不记详细门牌。
2. 追加到 `properties.csv`（列：项目名,小区或区域,面积㎡,性质,备注）。

**刷新估值**（用户说「刷新估值」或「更新余额」）：
1. 对每个持仓：查当前价 + 汇率，人民币市值 = 原币价 × 份额 × 汇率
   （A股汇率=1，港股 HKDCNY，美股 USDCNY）。
2. 对每套房：按小区/区域联网搜均价 × 面积，给粗估区间。
3. 连同用户口头报的现金/存款/负债，写成**同一日期**的快照到 `balances.csv`，
   并填好新列：来源（行情/搜索/手填）、估值日期、置信度（行情=高，房产=低）。
4. 报表会据此标注估算项。
5. 查不到或网络失败时，向用户确认或保留旧值并标低置信度，**不要臆填**。
```

- [ ] **Step 2: 校验**

Run: `grep -n "刷新估值\|holdings.csv\|properties.csv" SKILL.md`
Expected: 命中新加内容

- [ ] **Step 3: Commit**

```bash
git add SKILL.md
git commit -m "feat: SKILL.md 增股票/基金/房产估值工作流"
```

---

## Task 7: 端到端冒烟 + 回归

**Files:** 临时数据目录（不入库）

- [ ] **Step 1: 造带估值溯源的样例并出表**

```bash
SMOKE=$(mktemp -d)
cat > "$SMOKE/transactions.csv" <<'EOF'
日期,类型,现金流分类,方向,分类,金额,账户,备注
2026-06-01,收入,经营,流入,工资,20000,,
EOF
cat > "$SMOKE/balances.csv" <<'EOF'
日期,类型,项目,金额,流动性,性质,来源,估值日期,置信度
2026-06-30,资产,活期,50000,流动,可投资,手填,,
2026-06-30,资产,腾讯控股,165400,流动,可投资,行情,2026-06-20,高
2026-06-30,资产,投资房,2000000,非流动,可投资,搜索,2026-06-18,低
2026-06-30,负债,信用卡,10000,,,,,
EOF
python3 scripts/family_finance.py report 2026-06 --data-dir "$SMOKE"
cat "$SMOKE/reports/2026-06.md"
rm -rf "$SMOKE"
```

- [ ] **Step 2: 人工核对**

Expected:
- 资产负债表中：`腾讯控股（行情·2026-06-20·高）`、`投资房 ⚠估（搜索·2026-06-18·低）`、`活期` 无标注
- 末尾出现估值免责行「…区域均价粗估，仅供参考。」
- 资产合计 ¥2,215,400、净资产 ¥2,205,400 计算正确

- [ ] **Step 3: 全量回归**

Run: `uvx pytest scripts/ -q`
Expected: 全部 passed

---

## 自检结论（写作者已核对）

- **规格覆盖**：4.1/4.2 模板(Task3)、4.3 溯源列(Task1)、第5节工作流(Task6)、第6节标注+免责(Task2)、第8节隐私 gitignore(Task4)、口径文档(Task5)、端到端(Task7) 均有任务对应。估值查询为 agent 行为，记录在 SKILL.md/valuation.md（无脚本单测，符合架构）。
- **类型一致**：`Bal` 新增 `source/valued_at/confidence` 在 Task1 定义，Task2 `_valuation_note` 与 render 使用一致；CSV 列名「来源/估值日期/置信度」前后一致。
- **无占位符**：每步均含完整代码或完整命令。
- **向后兼容**：新列均为可选、新字段有默认值，旧 balances.csv 与原有测试不受影响（Task1 专门测试覆盖）。
