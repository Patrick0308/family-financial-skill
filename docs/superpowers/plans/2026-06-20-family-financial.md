# 家庭财务记录 Skill 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个 `family-financial` Claude Code skill，用自然语言记录家庭收支与资产负债，自动生成资产负债表 / 收入支出表 / 现金流表，并给出财务健康评分与家庭财富等级。

**Architecture:** 仓库本身即 skill 目录。计算与出表由一个 Python 标准库脚本 `scripts/family_finance.py` 完成（确定性、可单测、零第三方依赖）；`SKILL.md` 指导 Claude 把自然语言解析成 CSV 行并调用脚本。用户数据（transactions.csv / balances.csv / reports/）放在调用时指定的 `--data-dir`，与 skill 代码分离。

**Tech Stack:** Python 3（仅标准库：`csv`、`dataclasses`、`argparse`、`datetime`、`calendar`、`collections`）；pytest 做测试；Markdown 写 skill 文档。

---

## 文件结构

```
family-financial/                      # 仓库 = skill 目录
├── SKILL.md                           # 入口：触发与编排说明
├── references/
│   ├── categories-default.md          # 预设分类与资产标签模板
│   ├── scoring.md                     # 评分公式/阈值/权重（与脚本一致）
│   └── wealth-tiers.md                # 财富等级口径与分档阈值
├── assets/
│   ├── transactions.csv               # 空表头模板
│   └── balances.csv                   # 空表头模板
├── scripts/
│   ├── family_finance.py              # 计算 + 出表（核心）
│   └── test_family_finance.py         # pytest 单测
└── docs/superpowers/                  # 规格与计划（开发产物）
```

**`family_finance.py` 职责拆分（同一文件内的纯函数，便于单测）：**
- 数据模型：`Txn`、`Bal`（dataclass）
- 加载器：`load_transactions(path)`、`load_balances(path)`
- 期间筛选：`month_of(date_str)`、`txns_in_month(txns, ym)`、`latest_snapshot(bals, ym)`
- 三表：`balance_sheet(snap)`、`income_statement(txns)`、`cash_flow_statement(txns)`
- 评分：`compute_ratios(...)`、`health_score(ratios)`
- 财富：`investable_net_worth(snap)`、`wealth_tier(amount)`
- 渲染：`render_report(ym, ...)`
- CLI：`main(argv)` —— `report <YYYY-MM> --data-dir DIR`

**数据 schema 较规格的一处务实细化：** 资产标签（流动性 / 性质）直接作为 `balances.csv` 的列携带，而非从 `categories.md` 解析（更稳健、免解析 Markdown）。`balances.csv` 列：`日期,类型,项目,金额,流动性,性质`。

---

## Task 0: 仓库脚手架

**Files:**
- Create: `.gitignore`
- Create: `scripts/__init__.py`（空，使 pytest 可导入）

- [ ] **Step 1: 写 `.gitignore`**

```
__pycache__/
*.pyc
.pytest_cache/
# 用户数据目录（示例），不入库
data/
*.report.md
```

- [ ] **Step 2: 建空包文件**

```bash
touch scripts/__init__.py
```

- [ ] **Step 3: 确认 pytest 可用**

Run: `python3 -m pytest --version`
Expected: 打印 pytest 版本号。若未安装：`python3 -m pip install pytest`

- [ ] **Step 4: Commit**

```bash
git add .gitignore scripts/__init__.py
git commit -m "chore: 仓库脚手架与 gitignore"
```

---

## Task 1: 数据模型与加载器

**Files:**
- Create: `scripts/family_finance.py`
- Test: `scripts/test_family_finance.py`

- [ ] **Step 1: 写失败测试**

```python
# scripts/test_family_finance.py
import csv
from scripts.family_finance import Txn, Bal, load_transactions, load_balances


def _write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def test_load_transactions(tmp_path):
    p = tmp_path / "transactions.csv"
    _write_csv(
        p,
        ["日期", "类型", "现金流分类", "方向", "分类", "金额", "账户", "备注"],
        [["2026-06-20", "支出", "经营", "流出", "餐饮", "120", "招行信用卡", "买菜"]],
    )
    txns = load_transactions(str(p))
    assert txns == [Txn("2026-06-20", "支出", "经营", "流出", "餐饮", 120.0, "招行信用卡", "买菜")]


def test_load_balances_with_tags(tmp_path):
    p = tmp_path / "balances.csv"
    _write_csv(
        p,
        ["日期", "类型", "项目", "金额", "流动性", "性质"],
        [
            ["2026-06-30", "资产", "活期", "50000", "流动", "可投资"],
            ["2026-06-30", "负债", "房贷", "800000", "", ""],
        ],
    )
    bals = load_balances(str(p))
    assert bals[0] == Bal("2026-06-30", "资产", "活期", 50000.0, "流动", "可投资")
    assert bals[1] == Bal("2026-06-30", "负债", "房贷", 800000.0, "", "")


def test_load_missing_file_returns_empty(tmp_path):
    assert load_transactions(str(tmp_path / "nope.csv")) == []
    assert load_balances(str(tmp_path / "nope.csv")) == []
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python3 -m pytest scripts/test_family_finance.py -v`
Expected: FAIL，`ModuleNotFoundError` 或 `ImportError: cannot import name 'Txn'`

- [ ] **Step 3: 写最小实现**

```python
# scripts/family_finance.py
"""家庭财务：计算三表、健康评分、财富等级，并渲染 Markdown 报表。仅用标准库。"""
import csv
import os
from dataclasses import dataclass


@dataclass
class Txn:
    date: str
    type: str          # 收入 / 支出 / 转移
    flow_class: str    # 经营 / 投资 / 筹资
    direction: str     # 流入 / 流出
    category: str
    amount: float
    account: str = ""
    note: str = ""


@dataclass
class Bal:
    date: str
    kind: str          # 资产 / 负债
    item: str
    amount: float
    liquidity: str = ""  # 流动 / 非流动
    nature: str = ""     # 可投资 / 自用


def load_transactions(path):
    if not os.path.exists(path):
        return []
    out = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out.append(Txn(
                r["日期"], r["类型"], r["现金流分类"], r["方向"],
                r["分类"], float(r["金额"]),
                r.get("账户", "") or "", r.get("备注", "") or "",
            ))
    return out


def load_balances(path):
    if not os.path.exists(path):
        return []
    out = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out.append(Bal(
                r["日期"], r["类型"], r["项目"], float(r["金额"]),
                r.get("流动性", "") or "", r.get("性质", "") or "",
            ))
    return out
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `python3 -m pytest scripts/test_family_finance.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/family_finance.py scripts/test_family_finance.py
git commit -m "feat: 数据模型与 CSV 加载器"
```

---

## Task 2: 期间筛选（月份与最近快照）

**Files:**
- Modify: `scripts/family_finance.py`
- Test: `scripts/test_family_finance.py`

- [ ] **Step 1: 写失败测试**

```python
from scripts.family_finance import txns_in_month, latest_snapshot


def test_txns_in_month():
    txns = [
        Txn("2026-05-31", "支出", "经营", "流出", "餐饮", 10),
        Txn("2026-06-01", "支出", "经营", "流出", "餐饮", 20),
        Txn("2026-06-30", "收入", "经营", "流入", "工资", 30),
        Txn("2026-07-01", "支出", "经营", "流出", "餐饮", 40),
    ]
    got = txns_in_month(txns, "2026-06")
    assert [t.amount for t in got] == [20, 30]


def test_latest_snapshot_picks_most_recent_on_or_before_month_end():
    bals = [
        Bal("2026-05-31", "资产", "活期", 100),
        Bal("2026-06-10", "资产", "活期", 200),
        Bal("2026-06-10", "负债", "房贷", 50),
        Bal("2026-07-05", "资产", "活期", 999),  # 超出 6 月，应忽略
    ]
    snap = latest_snapshot(bals, "2026-06")
    assert {b.item: b.amount for b in snap} == {"活期": 200, "房贷": 50}


def test_latest_snapshot_empty_when_none_before_month():
    bals = [Bal("2026-07-05", "资产", "活期", 999)]
    assert latest_snapshot(bals, "2026-06") == []
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python3 -m pytest scripts/test_family_finance.py -k "month or snapshot" -v`
Expected: FAIL，`ImportError: cannot import name 'txns_in_month'`

- [ ] **Step 3: 写最小实现**

在 `family_finance.py` 追加：

```python
import calendar


def month_of(date_str):
    """'2026-06-20' -> '2026-06'"""
    return date_str[:7]


def _month_end(ym):
    """'2026-06' -> '2026-06-30'"""
    year, month = int(ym[:4]), int(ym[5:7])
    last = calendar.monthrange(year, month)[1]
    return f"{ym}-{last:02d}"


def txns_in_month(txns, ym):
    return [t for t in txns if month_of(t.date) == ym]


def latest_snapshot(bals, ym):
    """取 <= 月末 的最近一次快照（同一最近日期的全部行）。"""
    end = _month_end(ym)
    eligible = [b for b in bals if b.date <= end]
    if not eligible:
        return []
    latest_date = max(b.date for b in eligible)
    return [b for b in eligible if b.date == latest_date]
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `python3 -m pytest scripts/test_family_finance.py -k "month or snapshot" -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/family_finance.py scripts/test_family_finance.py
git commit -m "feat: 月份筛选与最近资产负债快照"
```

---

## Task 3: 资产负债表

**Files:**
- Modify: `scripts/family_finance.py`
- Test: `scripts/test_family_finance.py`

- [ ] **Step 1: 写失败测试**

```python
from scripts.family_finance import balance_sheet


def test_balance_sheet_totals_and_net_worth():
    snap = [
        Bal("2026-06-30", "资产", "活期", 50000, "流动", "可投资"),
        Bal("2026-06-30", "资产", "自住房", 2000000, "非流动", "自用"),
        Bal("2026-06-30", "负债", "房贷", 800000),
        Bal("2026-06-30", "负债", "信用卡", 20000),
    ]
    bs = balance_sheet(snap)
    assert bs["资产合计"] == 2050000
    assert bs["负债合计"] == 820000
    assert bs["净资产"] == 1230000
    assert bs["资产明细"] == [("活期", 50000), ("自住房", 2000000)]
    assert bs["负债明细"] == [("房贷", 800000), ("信用卡", 20000)]
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python3 -m pytest scripts/test_family_finance.py -k balance_sheet -v`
Expected: FAIL，`ImportError: cannot import name 'balance_sheet'`

- [ ] **Step 3: 写最小实现**

追加：

```python
def balance_sheet(snap):
    assets = [(b.item, b.amount) for b in snap if b.kind == "资产"]
    liabs = [(b.item, b.amount) for b in snap if b.kind == "负债"]
    a_total = sum(a for _, a in assets)
    l_total = sum(a for _, a in liabs)
    return {
        "资产明细": assets,
        "负债明细": liabs,
        "资产合计": a_total,
        "负债合计": l_total,
        "净资产": a_total - l_total,
    }
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `python3 -m pytest scripts/test_family_finance.py -k balance_sheet -v`
Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/family_finance.py scripts/test_family_finance.py
git commit -m "feat: 资产负债表计算"
```

---

## Task 4: 收入支出表

**Files:**
- Modify: `scripts/family_finance.py`
- Test: `scripts/test_family_finance.py`

- [ ] **Step 1: 写失败测试**

```python
from scripts.family_finance import income_statement


def test_income_statement_groups_and_surplus():
    txns = [
        Txn("2026-06-01", "收入", "经营", "流入", "工资", 20000),
        Txn("2026-06-05", "收入", "投资", "流入", "投资收益", 1000),
        Txn("2026-06-10", "支出", "经营", "流出", "餐饮", 3000),
        Txn("2026-06-12", "支出", "经营", "流出", "居住", 5000),
        Txn("2026-06-15", "转移", "投资", "流出", "基金买入", 10000),  # 不计入收支
    ]
    is_ = income_statement(txns)
    assert is_["收入明细"] == [("工资", 20000), ("投资收益", 1000)]
    assert is_["支出明细"] == [("餐饮", 3000), ("居住", 5000)]
    assert is_["收入合计"] == 21000
    assert is_["支出合计"] == 8000
    assert is_["月结余"] == 13000
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python3 -m pytest scripts/test_family_finance.py -k income_statement -v`
Expected: FAIL，`ImportError: cannot import name 'income_statement'`

- [ ] **Step 3: 写最小实现**

追加（用有序聚合，保持首次出现顺序）：

```python
from collections import OrderedDict


def _group_sum(pairs):
    """[(cat, amt), ...] -> [(cat, total), ...]，保持首次出现顺序。"""
    acc = OrderedDict()
    for cat, amt in pairs:
        acc[cat] = acc.get(cat, 0) + amt
    return list(acc.items())


def income_statement(txns):
    inc = _group_sum([(t.category, t.amount) for t in txns if t.type == "收入"])
    exp = _group_sum([(t.category, t.amount) for t in txns if t.type == "支出"])
    inc_total = sum(a for _, a in inc)
    exp_total = sum(a for _, a in exp)
    return {
        "收入明细": inc,
        "支出明细": exp,
        "收入合计": inc_total,
        "支出合计": exp_total,
        "月结余": inc_total - exp_total,
    }
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `python3 -m pytest scripts/test_family_finance.py -k income_statement -v`
Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/family_finance.py scripts/test_family_finance.py
git commit -m "feat: 收入支出表计算"
```

---

## Task 5: 现金流表

**Files:**
- Modify: `scripts/family_finance.py`
- Test: `scripts/test_family_finance.py`

- [ ] **Step 1: 写失败测试**

```python
from scripts.family_finance import cash_flow_statement


def test_cash_flow_by_class_and_net():
    txns = [
        Txn("2026-06-01", "收入", "经营", "流入", "工资", 20000),
        Txn("2026-06-10", "支出", "经营", "流出", "餐饮", 8000),
        Txn("2026-06-15", "转移", "投资", "流出", "基金买入", 10000),
        Txn("2026-06-20", "转移", "投资", "流入", "基金赎回", 3000),
        Txn("2026-06-25", "转移", "筹资", "流出", "房贷还本", 4000),
        Txn("2026-06-28", "转移", "筹资", "流入", "借入", 5000),
    ]
    cf = cash_flow_statement(txns)
    assert cf["经营性净现金流"] == 12000   # 20000 - 8000
    assert cf["投资性净现金流"] == -7000   # 3000 - 10000
    assert cf["筹资性净现金流"] == 1000    # 5000 - 4000
    assert cf["净现金流合计"] == 6000
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python3 -m pytest scripts/test_family_finance.py -k cash_flow -v`
Expected: FAIL，`ImportError: cannot import name 'cash_flow_statement'`

- [ ] **Step 3: 写最小实现**

追加：

```python
def _net_for_class(txns, flow_class):
    net = 0
    for t in txns:
        if t.flow_class != flow_class:
            continue
        net += t.amount if t.direction == "流入" else -t.amount
    return net


def cash_flow_statement(txns):
    op = _net_for_class(txns, "经营")
    inv = _net_for_class(txns, "投资")
    fin = _net_for_class(txns, "筹资")
    return {
        "经营性净现金流": op,
        "投资性净现金流": inv,
        "筹资性净现金流": fin,
        "净现金流合计": op + inv + fin,
    }
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `python3 -m pytest scripts/test_family_finance.py -k cash_flow -v`
Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/family_finance.py scripts/test_family_finance.py
git commit -m "feat: 现金流表计算"
```

---

## Task 6: 财务比率

**Files:**
- Modify: `scripts/family_finance.py`
- Test: `scripts/test_family_finance.py`

口径定义（写入 `references/scoring.md`，与代码一致）：
- 结余比率 = 月结余 / 收入合计（收入为 0 时记 0）
- 资产负债率 = 负债合计 / 资产合计（资产为 0 时记 0）
- 偿债收入比 = 筹资类流出合计 / 收入合计（收入为 0 时记 0）
- 应急储备(月) = 流动资产合计 / 月支出（月支出为 0 时记 None，表示无需偿付/无支出）
- 投资资产比 = 可投资资产合计 / 资产合计（资产为 0 时记 0）

- [ ] **Step 1: 写失败测试**

```python
from scripts.family_finance import compute_ratios


def test_compute_ratios():
    snap = [
        Bal("2026-06-30", "资产", "活期", 60000, "流动", "可投资"),
        Bal("2026-06-30", "资产", "基金", 140000, "流动", "可投资"),
        Bal("2026-06-30", "资产", "自住房", 800000, "非流动", "自用"),
        Bal("2026-06-30", "负债", "房贷", 500000),
        Bal("2026-06-30", "负债", "信用卡", 10000),
    ]
    txns = [
        Txn("2026-06-01", "收入", "经营", "流入", "工资", 20000),
        Txn("2026-06-10", "支出", "经营", "流出", "餐饮", 10000),
        Txn("2026-06-25", "转移", "筹资", "流出", "房贷还本", 4000),
    ]
    r = compute_ratios(snap, txns)
    assert round(r["结余比率"], 4) == 0.5          # (20000-10000)/20000
    assert round(r["资产负债率"], 4) == 0.5102     # 510000/1000000
    assert round(r["偿债收入比"], 4) == 0.2        # 4000/20000
    assert round(r["应急储备"], 4) == 20.0         # 200000/10000
    assert round(r["投资资产比"], 4) == 0.2        # 200000/1000000
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python3 -m pytest scripts/test_family_finance.py -k compute_ratios -v`
Expected: FAIL，`ImportError: cannot import name 'compute_ratios'`

- [ ] **Step 3: 写最小实现**

追加：

```python
def _safe_div(num, den):
    return num / den if den else 0.0


def compute_ratios(snap, txns):
    bs = balance_sheet(snap)
    is_ = income_statement(txns)
    liquid_assets = sum(
        b.amount for b in snap if b.kind == "资产" and b.liquidity == "流动"
    )
    investable_assets = sum(
        b.amount for b in snap if b.kind == "资产" and b.nature == "可投资"
    )
    debt_service = sum(
        t.amount for t in txns if t.flow_class == "筹资" and t.direction == "流出"
    )
    exp_total = is_["支出合计"]
    return {
        "结余比率": _safe_div(is_["月结余"], is_["收入合计"]),
        "资产负债率": _safe_div(bs["负债合计"], bs["资产合计"]),
        "偿债收入比": _safe_div(debt_service, is_["收入合计"]),
        "应急储备": _safe_div(liquid_assets, exp_total) if exp_total else None,
        "投资资产比": _safe_div(investable_assets, bs["资产合计"]),
    }
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `python3 -m pytest scripts/test_family_finance.py -k compute_ratios -v`
Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/family_finance.py scripts/test_family_finance.py
git commit -m "feat: 财务比率计算"
```

---

## Task 7: 健康评分

**Files:**
- Modify: `scripts/family_finance.py`
- Test: `scripts/test_family_finance.py`

各指标子分（0–100）与权重（写入 `references/scoring.md`）：
- 结余比率 r（权重 25）：r≥0.3→100；0≤r<0.3→ r/0.3×100；r<0→0
- 资产负债率 d（权重 25）：d≤0.5→100；0.5<d<1→ (1−(d−0.5)/0.5)×100；d≥1→0
- 偿债收入比 s（权重 20）：s≤0.4→100；0.4<s<0.8→ (1−(s−0.4)/0.4)×100；s≥0.8→0
- 应急储备 m 月（权重 20）：m≥6→100；3≤m<6→ 60+(m−3)/3×40；0≤m<3→ m/3×60；m=None→60（中性）
- 投资资产比 p（权重 10）：0.2≤p≤0.6→100；p<0.2→ p/0.2×100；p>0.6→ max(0,(1−(p−0.6)/0.4)×100)
- 总分 = 各子分按权重加权平均，四舍五入到整数
- 等级：≥85 优秀 / 70–84 良好 / 55–69 一般 / <55 需改善

- [ ] **Step 1: 写失败测试**

```python
from scripts.family_finance import health_score


def test_health_score_excellent():
    ratios = {"结余比率": 0.4, "资产负债率": 0.3, "偿债收入比": 0.1,
              "应急储备": 8.0, "投资资产比": 0.4}
    res = health_score(ratios)
    assert res["总分"] == 100
    assert res["等级"] == "优秀"


def test_health_score_weighted_midrange():
    # 结余0.15→50; 负债0.75→50; 偿债0.6→50; 应急4.5→80; 投资0.1→50
    # 加权 = 50*.25+50*.25+50*.20+80*.20+50*.10 = 12.5+12.5+10+16+5 = 56
    ratios = {"结余比率": 0.15, "资产负债率": 0.75, "偿债收入比": 0.6,
              "应急储备": 4.5, "投资资产比": 0.1}
    res = health_score(ratios)
    assert res["总分"] == 56
    assert res["等级"] == "一般"
    assert isinstance(res["建议"], list) and len(res["建议"]) >= 1


def test_health_score_emergency_none_is_neutral():
    ratios = {"结余比率": 0.3, "资产负债率": 0.5, "偿债收入比": 0.4,
              "应急储备": None, "投资资产比": 0.4}
    res = health_score(ratios)
    # 100*.25+100*.25+100*.20+60*.20+100*.10 = 92
    assert res["总分"] == 92
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python3 -m pytest scripts/test_family_finance.py -k health_score -v`
Expected: FAIL，`ImportError: cannot import name 'health_score'`

- [ ] **Step 3: 写最小实现**

追加：

```python
def _clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


def _score_surplus(r):
    if r >= 0.3:
        return 100.0
    if r < 0:
        return 0.0
    return r / 0.3 * 100


def _score_debt_ratio(d):
    if d <= 0.5:
        return 100.0
    if d >= 1:
        return 0.0
    return (1 - (d - 0.5) / 0.5) * 100


def _score_debt_service(s):
    if s <= 0.4:
        return 100.0
    if s >= 0.8:
        return 0.0
    return (1 - (s - 0.4) / 0.4) * 100


def _score_emergency(m):
    if m is None:
        return 60.0
    if m >= 6:
        return 100.0
    if m >= 3:
        return 60 + (m - 3) / 3 * 40
    return m / 3 * 60


def _score_investment(p):
    if 0.2 <= p <= 0.6:
        return 100.0
    if p < 0.2:
        return p / 0.2 * 100
    return _clamp((1 - (p - 0.6) / 0.4) * 100)


_WEIGHTS = {
    "结余比率": 25, "资产负债率": 25, "偿债收入比": 20,
    "应急储备": 20, "投资资产比": 10,
}


def _grade(score):
    if score >= 85:
        return "优秀"
    if score >= 70:
        return "良好"
    if score >= 55:
        return "一般"
    return "需改善"


def _suggestions(ratios):
    tips = []
    if ratios["结余比率"] < 0.3:
        tips.append("结余偏低：建议月结余占收入 30% 以上，优先压缩非必要支出。")
    if ratios["资产负债率"] > 0.5:
        tips.append("负债偏高：通用建议将总负债控制在总资产 50% 以内。")
    if ratios["偿债收入比"] > 0.4:
        tips.append("还款压力偏大：月还债额建议不超过月收入 40%。")
    m = ratios["应急储备"]
    if m is not None and m < 3:
        tips.append("应急储备不足：建议预留可覆盖 3–6 个月支出的流动资金。")
    if not tips:
        tips.append("各项指标健康，保持现有节奏，定期复盘即可。")
    return tips


def health_score(ratios):
    subs = {
        "结余比率": _score_surplus(ratios["结余比率"]),
        "资产负债率": _score_debt_ratio(ratios["资产负债率"]),
        "偿债收入比": _score_debt_service(ratios["偿债收入比"]),
        "应急储备": _score_emergency(ratios["应急储备"]),
        "投资资产比": _score_investment(ratios["投资资产比"]),
    }
    total = sum(subs[k] * _WEIGHTS[k] for k in _WEIGHTS) / sum(_WEIGHTS.values())
    total = round(total)
    return {"总分": total, "等级": _grade(total), "子分": subs, "建议": _suggestions(ratios)}
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `python3 -m pytest scripts/test_family_finance.py -k health_score -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/family_finance.py scripts/test_family_finance.py
git commit -m "feat: 财务健康评分"
```

---

## Task 8: 可投资净资产与财富等级

**Files:**
- Modify: `scripts/family_finance.py`
- Test: `scripts/test_family_finance.py`

口径（写入 `references/wealth-tiers.md`）：
- 可投资净资产 = 可投资资产合计 − 非自住房负债（= 总负债 − 项目名为「房贷」的负债）
- 分档（CNY）：起步 <10万；稳健 10万–100万；小康 100万–500万；富裕 500万–1000万；高净值 1000万–1亿；超高净值 >1亿
- 阈值列表常量 `_TIERS`，便于用户改

- [ ] **Step 1: 写失败测试**

```python
from scripts.family_finance import investable_net_worth, wealth_tier


def test_investable_net_worth_excludes_self_home_mortgage():
    snap = [
        Bal("2026-06-30", "资产", "活期", 300000, "流动", "可投资"),
        Bal("2026-06-30", "资产", "基金", 200000, "流动", "可投资"),
        Bal("2026-06-30", "资产", "自住房", 2000000, "非流动", "自用"),
        Bal("2026-06-30", "负债", "房贷", 800000),
        Bal("2026-06-30", "负债", "信用卡", 20000),
    ]
    # 可投资资产 500000 - 非房贷负债 20000 = 480000
    assert investable_net_worth(snap) == 480000


def test_wealth_tier_and_gap():
    res = wealth_tier(1250000)
    assert res["等级"] == "小康"
    assert res["距下一档"] == 5000000 - 1250000  # 距「富裕」下限 500万
    assert res["下一档"] == "富裕"


def test_wealth_tier_top_has_no_next():
    res = wealth_tier(150000000)
    assert res["等级"] == "超高净值"
    assert res["下一档"] is None
    assert res["距下一档"] is None
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python3 -m pytest scripts/test_family_finance.py -k "investable or wealth_tier" -v`
Expected: FAIL，`ImportError: cannot import name 'investable_net_worth'`

- [ ] **Step 3: 写最小实现**

追加：

```python
# (等级名, 下限含, 上限不含)；上限 None 表示无上界
_TIERS = [
    ("起步", 0, 100_000),
    ("稳健", 100_000, 1_000_000),
    ("小康", 1_000_000, 5_000_000),
    ("富裕", 5_000_000, 10_000_000),
    ("高净值", 10_000_000, 100_000_000),
    ("超高净值", 100_000_000, None),
]


def investable_net_worth(snap):
    investable = sum(
        b.amount for b in snap if b.kind == "资产" and b.nature == "可投资"
    )
    non_home_debt = sum(
        b.amount for b in snap if b.kind == "负债" and b.item != "房贷"
    )
    return investable - non_home_debt


def wealth_tier(amount):
    for i, (name, lo, hi) in enumerate(_TIERS):
        if amount < 0:
            name, hi = _TIERS[0][0], _TIERS[0][2]
            i = 0
        in_tier = (amount >= lo) and (hi is None or amount < hi)
        if in_tier:
            if hi is None:
                return {"等级": name, "下一档": None, "距下一档": None}
            nxt = _TIERS[i + 1][0]
            return {"等级": name, "下一档": nxt, "距下一档": hi - amount}
    # amount < 0 落到起步
    return {"等级": _TIERS[0][0], "下一档": _TIERS[1][0], "距下一档": _TIERS[0][2] - amount}
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `python3 -m pytest scripts/test_family_finance.py -k "investable or wealth_tier" -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/family_finance.py scripts/test_family_finance.py
git commit -m "feat: 可投资净资产与家庭财富等级"
```

---

## Task 9: 报表渲染

**Files:**
- Modify: `scripts/family_finance.py`
- Test: `scripts/test_family_finance.py`

- [ ] **Step 1: 写失败测试**

```python
from scripts.family_finance import render_report


def test_render_report_contains_all_sections():
    snap = [
        Bal("2026-06-30", "资产", "活期", 200000, "流动", "可投资"),
        Bal("2026-06-30", "资产", "自住房", 2000000, "非流动", "自用"),
        Bal("2026-06-30", "负债", "房贷", 800000),
    ]
    txns = [
        Txn("2026-06-01", "收入", "经营", "流入", "工资", 20000),
        Txn("2026-06-10", "支出", "经营", "流出", "餐饮", 8000),
    ]
    md = render_report("2026-06", snap, txns)
    for marker in [
        "# 2026-06 家庭财务报表",
        "## 一、资产负债表",
        "## 二、收入支出表",
        "## 三、现金流表",
        "## 四、财务健康评分",
        "## 五、家庭财富等级",
        "净资产",
        "月结余",
        "净现金流合计",
        "/ 100",
        "非持牌",  # 免责声明
    ]:
        assert marker in md, marker


def test_render_report_handles_no_snapshot():
    txns = [Txn("2026-06-01", "收入", "经营", "流入", "工资", 20000)]
    md = render_report("2026-06", [], txns)
    assert "暂无资产负债快照" in md
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python3 -m pytest scripts/test_family_finance.py -k render_report -v`
Expected: FAIL，`ImportError: cannot import name 'render_report'`

- [ ] **Step 3: 写最小实现**

追加（金额格式化为带千分位的 `¥`）：

```python
def _yuan(x):
    return f"¥{x:,.0f}"


def _rows_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |",
           "| " + " | ".join(["---"] * len(headers)) + " |"]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(out)


def render_report(ym, snap, txns):
    parts = [f"# {ym} 家庭财务报表\n"]

    # 一、资产负债表
    parts.append("## 一、资产负债表\n")
    if not snap:
        parts.append("> 暂无资产负债快照，请先用「更新余额」记录一次。\n")
        bs = {"资产合计": 0, "负债合计": 0, "净资产": 0}
    else:
        bs = balance_sheet(snap)
        rows = [("资产", item, _yuan(amt)) for item, amt in bs["资产明细"]]
        rows += [("负债", item, _yuan(amt)) for item, amt in bs["负债明细"]]
        parts.append(_rows_table(["类型", "项目", "金额"], rows))
        parts.append(
            f"\n- 资产合计：{_yuan(bs['资产合计'])}　负债合计：{_yuan(bs['负债合计'])}"
            f"　**净资产：{_yuan(bs['净资产'])}**\n"
        )

    # 二、收入支出表
    is_ = income_statement(txns)
    parts.append("## 二、收入支出表\n")
    rows = [("收入", c, _yuan(a)) for c, a in is_["收入明细"]]
    rows += [("支出", c, _yuan(a)) for c, a in is_["支出明细"]]
    parts.append(_rows_table(["类型", "分类", "金额"], rows) if rows else "> 本月无收支流水。")
    parts.append(
        f"\n- 收入合计：{_yuan(is_['收入合计'])}　支出合计：{_yuan(is_['支出合计'])}"
        f"　**月结余：{_yuan(is_['月结余'])}**\n"
    )

    # 三、现金流表
    cf = cash_flow_statement(txns)
    parts.append("## 三、现金流表\n")
    parts.append(_rows_table(["项目", "金额"], [
        ("经营性净现金流", _yuan(cf["经营性净现金流"])),
        ("投资性净现金流", _yuan(cf["投资性净现金流"])),
        ("筹资性净现金流", _yuan(cf["筹资性净现金流"])),
        ("**净现金流合计**", f"**{_yuan(cf['净现金流合计'])}**"),
    ]))
    parts.append("")

    # 四、健康评分
    ratios = compute_ratios(snap, txns)
    hs = health_score(ratios)
    parts.append("## 四、财务健康评分\n")
    em = "—" if ratios["应急储备"] is None else f"{ratios['应急储备']:.1f} 个月"
    parts.append(_rows_table(["指标", "数值", "子分"], [
        ("结余比率", f"{ratios['结余比率']*100:.1f}%", f"{hs['子分']['结余比率']:.0f}"),
        ("资产负债率", f"{ratios['资产负债率']*100:.1f}%", f"{hs['子分']['资产负债率']:.0f}"),
        ("偿债收入比", f"{ratios['偿债收入比']*100:.1f}%", f"{hs['子分']['偿债收入比']:.0f}"),
        ("应急储备", em, f"{hs['子分']['应急储备']:.0f}"),
        ("投资资产比", f"{ratios['投资资产比']*100:.1f}%", f"{hs['子分']['投资资产比']:.0f}"),
    ]))
    parts.append(f"\n**综合评分：{hs['总分']} / 100（{hs['等级']}）**\n")
    parts.append("建议：")
    parts.extend(f"- {t}" for t in hs["建议"])
    parts.append("")

    # 五、财富等级
    inw = investable_net_worth(snap)
    wt = wealth_tier(inw)
    parts.append("## 五、家庭财富等级\n")
    line = f"**{wt['等级']}**（可投资净资产 {_yuan(inw)}；总净资产 {_yuan(bs['净资产'])}）"
    if wt["下一档"]:
        line += f"，距「{wt['下一档']}」还差 {_yuan(wt['距下一档'])}"
    parts.append(line + "\n")

    parts.append("---")
    parts.append("> 免责声明：本报表为家庭自助记录工具，评分与等级为通用参考，"
                 "不构成个性化投资建议；作者非持牌财务顾问。")
    return "\n".join(parts) + "\n"
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `python3 -m pytest scripts/test_family_finance.py -k render_report -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/family_finance.py scripts/test_family_finance.py
git commit -m "feat: Markdown 报表渲染"
```

---

## Task 10: CLI 入口

**Files:**
- Modify: `scripts/family_finance.py`
- Test: `scripts/test_family_finance.py`

- [ ] **Step 1: 写失败测试**

```python
import os
from scripts.family_finance import main


def test_main_report_writes_file(tmp_path, capsys):
    data = tmp_path
    _write_csv(
        data / "transactions.csv",
        ["日期", "类型", "现金流分类", "方向", "分类", "金额", "账户", "备注"],
        [["2026-06-01", "收入", "经营", "流入", "工资", "20000", "", ""],
         ["2026-06-10", "支出", "经营", "流出", "餐饮", "8000", "", ""]],
    )
    _write_csv(
        data / "balances.csv",
        ["日期", "类型", "项目", "金额", "流动性", "性质"],
        [["2026-06-30", "资产", "活期", "200000", "流动", "可投资"],
         ["2026-06-30", "负债", "房贷", "800000", "", ""]],
    )
    rc = main(["report", "2026-06", "--data-dir", str(data)])
    assert rc == 0
    out_path = data / "reports" / "2026-06.md"
    assert out_path.exists()
    content = out_path.read_text(encoding="utf-8")
    assert "净资产" in content
    # stdout 也打印路径，便于 Claude 读取
    assert "2026-06.md" in capsys.readouterr().out
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python3 -m pytest scripts/test_family_finance.py -k main_report -v`
Expected: FAIL，`ImportError: cannot import name 'main'`

- [ ] **Step 3: 写最小实现**

追加（文件末尾）：

```python
import argparse


def main(argv=None):
    parser = argparse.ArgumentParser(prog="family_finance")
    sub = parser.add_subparsers(dest="cmd", required=True)
    rep = sub.add_parser("report", help="生成某月报表")
    rep.add_argument("month", help="YYYY-MM，如 2026-06")
    rep.add_argument("--data-dir", default=".", help="数据目录（含 transactions.csv / balances.csv）")
    args = parser.parse_args(argv)

    if args.cmd == "report":
        data_dir = args.data_dir
        txns = load_transactions(os.path.join(data_dir, "transactions.csv"))
        bals = load_balances(os.path.join(data_dir, "balances.csv"))
        snap = latest_snapshot(bals, args.month)
        md = render_report(args.month, snap, txns_in_month(txns, args.month))
        out_dir = os.path.join(data_dir, "reports")
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"{args.month}.md")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(md)
        print(f"已生成报表：{out_path}")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `python3 -m pytest scripts/test_family_finance.py -v`
Expected: 全部 passed（含此前所有任务）

- [ ] **Step 5: Commit**

```bash
git add scripts/family_finance.py scripts/test_family_finance.py
git commit -m "feat: CLI report 入口"
```

---

## Task 11: 资产/数据模板

**Files:**
- Create: `assets/transactions.csv`
- Create: `assets/balances.csv`

- [ ] **Step 1: 写 transactions.csv 模板（仅表头）**

```
日期,类型,现金流分类,方向,分类,金额,账户,备注
```

- [ ] **Step 2: 写 balances.csv 模板（表头 + 一行注释示例，便于用户照填）**

```
日期,类型,项目,金额,流动性,性质
2026-06-30,资产,活期,0,流动,可投资
2026-06-30,负债,房贷,0,,
```

- [ ] **Step 3: Commit**

```bash
git add assets/transactions.csv assets/balances.csv
git commit -m "feat: 数据 CSV 模板"
```

---

## Task 12: references 文档

**Files:**
- Create: `references/categories-default.md`
- Create: `references/scoring.md`
- Create: `references/wealth-tiers.md`

- [ ] **Step 1: 写 `categories-default.md`**

内容（完整，照抄）：

```markdown
# 预设家庭分类（可自定义）

新增/删除分类时直接改本文件；资产项目须带「流动性」「性质」两个标签，写入 balances.csv 对应列。

## 资产（项目 → 流动性 / 性质）
- 现金/活期 → 流动 / 可投资
- 定期存款 → 流动 / 可投资
- 投资（股票/基金） → 流动 / 可投资
- 房产（自住） → 非流动 / 自用
- 房产（投资） → 非流动 / 可投资
- 车辆（自用） → 非流动 / 自用
- 其他资产 → 非流动 / 自用

> 「自住」房产命名为「房贷」对应的房产；财富等级计算会把项目名为「房贷」的负债视为自住房负债整体剔除。

## 负债（项目）
- 房贷、车贷、信用卡、消费贷、其他

## 收入（分类 → 默认类型/现金流分类）
- 工资、奖金 → 收入 / 经营
- 投资收益 → 收入 / 投资
- 其他 → 收入 / 经营

## 支出（分类，均为 支出 / 经营 / 流出）
- 餐饮、居住、交通、教育、医疗、娱乐、人情、其他

## 转移（既非收入也非支出的现金流）
- 投资买入/卖出 → 转移 / 投资
- 借入 → 转移 / 筹资 / 流入
- 还本金 → 转移 / 筹资 / 流出
```

- [ ] **Step 2: 写 `scoring.md`**

内容须与 `family_finance.py` 中的口径、阈值、权重逐字一致。完整内容：

```markdown
# 财务健康评分口径

> 与 scripts/family_finance.py 实现保持一致；改了这里也要改代码与测试。

## 比率定义
- 结余比率 = 月结余 / 收入合计（收入 0 → 0）
- 资产负债率 = 负债合计 / 资产合计（资产 0 → 0）
- 偿债收入比 = 筹资类流出合计 / 收入合计（收入 0 → 0）
- 应急储备(月) = 流动资产合计 / 月支出（月支出 0 → 不适用，记中性）
- 投资资产比 = 可投资资产合计 / 资产合计（资产 0 → 0）

## 子分（0–100）
- 结余比率 r：r≥0.3→100；0≤r<0.3→ r/0.3×100；r<0→0
- 资产负债率 d：d≤0.5→100；0.5<d<1→ (1−(d−0.5)/0.5)×100；d≥1→0
- 偿债收入比 s：s≤0.4→100；0.4<s<0.8→ (1−(s−0.4)/0.4)×100；s≥0.8→0
- 应急储备 m：m≥6→100；3≤m<6→ 60+(m−3)/3×40；0≤m<3→ m/3×60；不适用→60
- 投资资产比 p：0.2≤p≤0.6→100；p<0.2→ p/0.2×100；p>0.6→ max(0,(1−(p−0.6)/0.4)×100)

## 权重与总分
结余比率 25 / 资产负债率 25 / 偿债收入比 20 / 应急储备 20 / 投资资产比 10。
总分 = 加权平均（四舍五入到整数）。

## 等级
≥85 优秀 / 70–84 良好 / 55–69 一般 / <55 需改善。

## 免责
评分与建议为通用家庭理财参考，不构成个性化投资建议。
```

- [ ] **Step 3: 写 `wealth-tiers.md`**

内容与代码 `_TIERS` 一致。完整内容：

```markdown
# 家庭财富等级口径

> 与 scripts/family_finance.py 的 _TIERS / investable_net_worth 保持一致。

## 可投资净资产口径
可投资净资产 = 可投资资产合计 − 非自住房负债
其中：可投资资产 = balances 中 性质=可投资 的资产；
非自住房负债 = 总负债 − 项目名为「房贷」的负债（房贷视作自住房负债整体剔除）。

同屏一并展示：总净资产（总资产−总负债）作为参考。

## 分档（人民币；经验值，非官方标准，按地区自行调整）
| 等级 | 可投资净资产 |
|---|---|
| 起步 | < 10 万 |
| 稳健 | 10 万 – 100 万 |
| 小康 | 100 万 – 500 万 |
| 富裕 | 500 万 – 1000 万 |
| 高净值 | 1000 万 – 1 亿 |
| 超高净值 | > 1 亿 |

## 阈值来源
参考高净值/私人银行「可投资资产」口径与国内城镇家庭资产负债调查，属经验分档，
非权威发布。要调整：改 family_finance.py 的 _TIERS 与本表，并更新测试。
```

- [ ] **Step 4: Commit**

```bash
git add references/
git commit -m "docs: references 分类/评分/财富等级口径"
```

---

## Task 13: SKILL.md（入口与编排）

**Files:**
- Create: `SKILL.md`

- [ ] **Step 1: 写 `SKILL.md`**

完整内容：

````markdown
---
name: family-financial
description: 帮助家庭用自然语言记录财务状况，生成家庭资产负债表、收入支出表、现金流表，并给出财务健康评分与家庭财富等级。当用户要记账、记一笔收支、更新资产/负债余额、出月度/季度/年度财务报表、查看家庭净资产、财务健康评分或财富等级时使用。
---

# 家庭财务记录

用自然语言记录家庭收支与资产负债，自动生成三张报表 + 健康评分 + 财富等级。
计算由 `scripts/family_finance.py`（Python 标准库，零依赖）完成，确保数值准确。

## 数据位置

默认数据目录为当前工作目录。其中：
- `transactions.csv` —— 收支/转移流水
- `balances.csv` —— 资产负债快照
- `reports/` —— 生成的报表

首次使用时若不存在，从 `assets/` 复制模板：
```bash
cp <skill>/assets/transactions.csv ./transactions.csv
cp <skill>/assets/balances.csv ./balances.csv
```

## 操作

### 1. 记一笔流水
用户说「记一笔：今天买菜 120」「工资到账 20000」等时：
1. 解析出 日期(默认今天)、类型、现金流分类、方向、分类、金额、账户、备注。
   - 映射规则见 `references/categories-default.md`。
   - 买菜/吃饭→支出/经营/流出/餐饮；工资→收入/经营/流入/工资；
     买基金→转移/投资/流出；还房贷本金→转移/筹资/流出。
2. **若类型或分类不确定，先向用户确认，不要臆测。**
3. 追加一行到 `transactions.csv`（保持列顺序：日期,类型,现金流分类,方向,分类,金额,账户,备注）。

### 2. 更新资产负债余额
用户说「更新余额：房贷剩 80 万、活期 5 万…」时：
1. 解析为多条 (类型, 项目, 金额) ，资产项补全 流动性/性质 标签（见分类表）。
2. 日期默认为今天（或用户指定的月末）。
3. 把这组快照行追加到 `balances.csv`。出表时自动取最近一次快照。

### 3. 出报表
用户说「出 6 月的表」「看 2026-06 报表」时：
```bash
python3 <skill>/scripts/family_finance.py report 2026-06 --data-dir .
```
脚本生成 `reports/2026-06.md`。读取该文件内容展示给用户。

### 4. 季/年汇总
脚本按月出表。多月汇总时，对相关月份分别 report 后由你聚合呈现，
或直接读取多个月的 transactions 汇总（资产负债取目标期末最近快照）。

### 5. 增删分类
直接编辑 `references/categories-default.md`（或用户本地的分类说明），并提醒用户
新资产项目要在 balances.csv 填好 流动性/性质 两列。

## 重要约束
- 评分里的「建议」限于**通用家庭理财常识**，**不做个性化投资推荐**（不推荐具体标的、
  不做择时建议）。报表已含免责声明：作者非持牌财务顾问。
- 金额为人民币（¥），单币种。

## 自测
```bash
python3 -m pytest <skill>/scripts/test_family_finance.py -v
```
````

- [ ] **Step 2: 校验 frontmatter 与脚本路径**

Run: `head -5 SKILL.md`
Expected: 显示 `name: family-financial` 与 `description:` 行。

- [ ] **Step 3: Commit**

```bash
git add SKILL.md
git commit -m "feat: SKILL.md 入口与编排说明"
```

---

## Task 14: 端到端冒烟测试（真实样例）

**Files:**
- Test: 临时数据目录（不入库）

- [ ] **Step 1: 造样例数据并出表**

```bash
mkdir -p /tmp/ff-smoke && cd /tmp/ff-smoke
cat > transactions.csv <<'EOF'
日期,类型,现金流分类,方向,分类,金额,账户,备注
2026-06-01,收入,经营,流入,工资,20000,,
2026-06-05,收入,投资,流入,投资收益,1000,,
2026-06-10,支出,经营,流出,餐饮,3000,,
2026-06-12,支出,经营,流出,居住,5000,,
2026-06-15,转移,投资,流出,基金买入,10000,,
2026-06-25,转移,筹资,流出,房贷还本,4000,,
EOF
cat > balances.csv <<'EOF'
日期,类型,项目,金额,流动性,性质
2026-06-30,资产,活期,60000,流动,可投资
2026-06-30,资产,基金,140000,流动,可投资
2026-06-30,资产,自住房,2000000,非流动,自用
2026-06-30,负债,房贷,500000,,
2026-06-30,负债,信用卡,10000,,
EOF
python3 /Users/patrick/projects/family-financial/scripts/family_finance.py report 2026-06 --data-dir .
cat reports/2026-06.md
```

- [ ] **Step 2: 人工核对关键数字**

Expected（手算核对）：
- 资产合计 ¥2,200,000；负债合计 ¥510,000；**净资产 ¥1,690,000**
- 收入合计 ¥21,000；支出合计 ¥8,000；**月结余 ¥13,000**
- 经营性净现金流 ¥4,000（21000−... 注意投资收益属投资类：经营=工资20000−餐饮3000−居住5000=12000）
  - 经营 = 20000 − 3000 − 5000 = **¥12,000**
  - 投资 = 1000 − 10000 = **−¥9,000**
  - 筹资 = −4000 = **−¥4,000**
  - **净现金流合计 = −¥1,000**
- 可投资净资产 = 可投资资产(60000+140000) − 非房贷负债(10000) = **¥190,000** → 等级「稳健」，距「小康」差 ¥810,000
- 评分应在 0–100 间，含等级与建议，末尾有免责声明

若数字不符，回到对应 Task 修正后重跑。

- [ ] **Step 3: 全量测试回归**

Run: `cd /Users/patrick/projects/family-financial && python3 -m pytest scripts/ -v`
Expected: 全部 passed

- [ ] **Step 4: 清理 + Commit（仅 README 提示如何使用，可选）**

```bash
rm -rf /tmp/ff-smoke
```
冒烟测试不产生入库文件。如需，可在此追加一个 `README.md` 说明安装方式（symlink 到 ~/.claude/skills）。

---

## 自检结论（写作者已核对）

- **规格覆盖**：三表(Task3-5)、评分(Task6-7)、可投资净资产+财富等级(Task8)、渲染含两行结论与免责(Task9)、CLI(Task10)、模板(Task11)、references 三文档(Task12)、SKILL.md(Task13) 均有任务对应。
- **类型一致**：`Txn`/`Bal` 字段、`balance_sheet`/`income_statement`/`cash_flow_statement`/`compute_ratios`/`health_score`/`investable_net_worth`/`wealth_tier`/`render_report`/`main` 在各任务间签名一致。
- **口径一致**：scoring.md / wealth-tiers.md 的阈值与代码常量逐条对应。
- **无占位符**：每个代码步骤均为完整可运行代码。
- **已知细化**：资产标签随 balances.csv 列携带（较规格的 categories.md 更稳健），已在文件结构说明标注。
