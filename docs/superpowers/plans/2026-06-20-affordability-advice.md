# 大额消费可行性评估 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 `family-financial` 增加「大额消费可行性评估」——用户给金额+付款方式，技能基于其财务状态判定 可承受/谨慎/暂不建议，并给关键数字、理由、可落地临界值。

**Architecture:** 确定性计算放进 `scripts/family_finance.py` 的新纯函数 `affordability(...)` + CLI 子命令 `afford`（可单测、零联网、零依赖）；自然语言解析与建议措辞在 agent 层（SKILL.md）。判定口径沿用现有健康指标（应急储备 3–6 个月、偿债收入比 ≤40%）。

**Tech Stack:** Python 3 标准库；pytest（`uvx pytest`，host python3 无 pytest）；Markdown。

参考规格：`docs/superpowers/specs/2026-06-20-affordability-advice-design.md`

---

## 文件结构

```
scripts/family_finance.py        # 改：新增 affordability() + CLI afford 子命令
scripts/test_family_finance.py   # 改：新增测试
SKILL.md                         # 改：新增「消费建议」工作流
references/affordability.md       # 新：口径与免责
```

`affordability` 复用现有 `balance_sheet` / `income_statement` / `_yuan` 与「流动资产、筹资流出」的计算方式。

---

## Task 1: affordability —— 一次性全款（lump）

**Files:**
- Modify: `scripts/family_finance.py`（在 `wealth_tier` 之后、`render_report` 之前新增函数）
- Test: `scripts/test_family_finance.py`

判定（金额 A，流动资产 L，月支出 E）：
- 暂不建议：A > L，或 (L−A)/E < 3
- 谨慎：3 ≤ (L−A)/E < 6
- 可承受：(L−A)/E ≥ 6
- 月支出 E ≤ 0 → 无法评估
- 临界值：max_affordable = max(0, L − 6×E)

- [ ] **Step 1: 写失败测试**

```python
from scripts.family_finance import affordability


def _snap_with_liquid(liquid, fixed=2000000):
    return [
        Bal("2026-06-30", "资产", "活期", liquid, "流动", "可投资"),
        Bal("2026-06-30", "资产", "自住房", fixed, "非流动", "自用"),
    ]


def _txns_income_expense(income, expense):
    out = []
    if income:
        out.append(Txn("2026-06-01", "收入", "经营", "流入", "工资", income))
    if expense:
        out.append(Txn("2026-06-10", "支出", "经营", "流出", "餐饮", expense))
    return out


def test_afford_lump_affordable():
    snap = _snap_with_liquid(600000)   # 流动 60万
    txns = _txns_income_expense(40000, 20000)  # 月支出 2万
    r = affordability(snap, txns, 100000, "lump")  # 付10万 → 剩50万 → 25个月
    assert r["判定"] == "可承受"
    assert round(r["指标"]["付后应急储备"], 1) == 25.0
    assert r["指标"]["流动资产剩余"] == 500000
    assert r["临界值"]["一次性可承受上限"] == 600000 - 6 * 20000  # 480000


def test_afford_lump_caution():
    snap = _snap_with_liquid(200000)   # 流动 20万
    txns = _txns_income_expense(40000, 20000)  # 月支出 2万
    r = affordability(snap, txns, 100000, "lump")  # 剩10万 → 5个月 → 谨慎
    assert r["判定"] == "谨慎"
    assert round(r["指标"]["付后应急储备"], 1) == 5.0


def test_afford_lump_not_advised_low_reserve():
    snap = _snap_with_liquid(200000)
    txns = _txns_income_expense(40000, 20000)
    r = affordability(snap, txns, 160000, "lump")  # 剩4万 → 2个月 → 暂不建议
    assert r["判定"] == "暂不建议"


def test_afford_lump_not_advised_insufficient():
    snap = _snap_with_liquid(50000)
    txns = _txns_income_expense(40000, 20000)
    r = affordability(snap, txns, 100000, "lump")  # 流动不够付
    assert r["判定"] == "暂不建议"
    assert isinstance(r["理由"], list) and r["理由"]


def test_afford_lump_unknown_when_no_expense():
    snap = _snap_with_liquid(600000)
    txns = _txns_income_expense(40000, 0)  # 无支出
    r = affordability(snap, txns, 100000, "lump")
    assert r["判定"] == "无法评估"
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `uvx pytest scripts/test_family_finance.py -k afford_lump -v`
Expected: FAIL，`ImportError: cannot import name 'affordability'`

- [ ] **Step 3: 写最小实现**

在 `family_finance.py` 中 `wealth_tier` 之后新增：

```python
def affordability(snap, txns, amount, mode, monthly=None, months=None):
    """评估一笔大额消费是否可承受。mode: 'lump' 一次性 / 'installment' 分期。"""
    bs = balance_sheet(snap)
    is_ = income_statement(txns)
    income = is_["收入合计"]
    expense = is_["支出合计"]
    surplus = is_["月结余"]
    liquid = sum(b.amount for b in snap if b.kind == "资产" and b.liquidity == "流动")
    existing_debt = sum(
        t.amount for t in txns if t.flow_class == "筹资" and t.direction == "流出"
    )

    if mode == "lump":
        if expense <= 0:
            return {"判定": "无法评估", "指标": {}, "临界值": None,
                    "理由": ["缺少当月支出数据，无法估算应急储备影响，请先记录本月支出。"]}
        remaining = liquid - amount
        post_emergency = remaining / expense
        max_affordable = max(0.0, liquid - 6 * expense)
        if amount > liquid:
            verdict = "暂不建议"
            reason = f"流动资产 {_yuan(liquid)} 不足以全款支付 {_yuan(amount)}。"
        elif post_emergency < 3:
            verdict = "暂不建议"
            reason = f"付款后应急储备降至 {post_emergency:.1f} 个月（建议 ≥3 个月）。"
        elif post_emergency < 6:
            verdict = "谨慎"
            reason = f"付款后应急储备 {post_emergency:.1f} 个月（处于 3–6 个月）。"
        else:
            verdict = "可承受"
            reason = f"付款后应急储备仍有 {post_emergency:.1f} 个月（≥6 个月）。"
        return {
            "判定": verdict,
            "指标": {"流动资产剩余": remaining, "付后应急储备": post_emergency},
            "临界值": {"一次性可承受上限": max_affordable},
            "理由": [reason],
        }

    if mode == "installment":
        if income <= 0:
            return {"判定": "无法评估", "指标": {}, "临界值": None,
                    "理由": ["缺少当月收入数据，无法估算偿债能力，请先记录本月收入。"]}
        if monthly is None:
            if months and months > 0:
                monthly = amount / months
            else:
                return {"判定": "无法评估", "指标": {}, "临界值": None,
                        "理由": ["分期需要提供月供或期数。"]}
        new_ratio = (existing_debt + monthly) / income
        new_surplus = surplus - monthly
        new_debt_ratio = (bs["负债合计"] + amount) / bs["资产合计"] if bs["资产合计"] else 0.0
        max_monthly = max(0.0, 0.3 * income - existing_debt)
        if new_surplus < 0:
            verdict = "暂不建议"
            reason = f"新增月供 {_yuan(monthly)} 后月结余转负（{_yuan(new_surplus)}）。"
        elif new_ratio > 0.4:
            verdict = "暂不建议"
            reason = f"偿债收入比升至 {new_ratio * 100:.1f}%（建议 ≤40%）。"
        elif new_ratio > 0.3:
            verdict = "谨慎"
            reason = f"偿债收入比 {new_ratio * 100:.1f}%（处于 30–40%）。"
        else:
            verdict = "可承受"
            reason = f"偿债收入比 {new_ratio * 100:.1f}%（≤30%），月结余仍为正。"
        return {
            "判定": verdict,
            "指标": {"月供": monthly, "新偿债收入比": new_ratio,
                     "新月结余": new_surplus, "新负债率": new_debt_ratio},
            "临界值": {"可承受月供上限": max_monthly},
            "理由": [reason],
        }

    return {"判定": "无法评估", "指标": {}, "临界值": None,
            "理由": [f"未知付款方式：{mode}"]}
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `uvx pytest scripts/test_family_finance.py -k afford_lump -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/family_finance.py scripts/test_family_finance.py
git commit -m "feat: affordability 一次性全款可行性评估"
```

---

## Task 2: affordability —— 分期（installment）

**Files:**
- Modify: `scripts/family_finance.py`（实现已在 Task 1 一并写入；本任务补测试验证分期分支）
- Test: `scripts/test_family_finance.py`

判定（新增月供 M，月收入 I，现有月还债 D，月结余 S）：
- 暂不建议：S−M < 0，或 (D+M)/I > 0.4
- 谨慎：0.3 < (D+M)/I ≤ 0.4
- 可承受：(D+M)/I ≤ 0.3 且 S−M > 0
- 月收入 I ≤ 0 → 无法评估
- 只给期数：monthly = amount / months（无息估）
- 临界值：max_monthly = max(0, 0.3×I − D)

- [ ] **Step 1: 写失败测试**

```python
def test_afford_installment_affordable():
    snap = _snap_with_liquid(200000)
    txns = _txns_income_expense(40000, 15000)  # 月收入4万，无现有还债
    r = affordability(snap, txns, 300000, "installment", monthly=9000)
    # 偿债比 9000/40000 = 22.5% ≤30%，结余 40000-15000-9000>0
    assert r["判定"] == "可承受"
    assert round(r["指标"]["新偿债收入比"], 4) == 0.225
    assert r["指标"]["新月结余"] == 25000 - 9000  # 16000
    assert r["临界值"]["可承受月供上限"] == 0.3 * 40000 - 0  # 12000


def test_afford_installment_caution():
    snap = _snap_with_liquid(200000)
    txns = _txns_income_expense(40000, 15000)
    r = affordability(snap, txns, 300000, "installment", monthly=14000)
    # 偿债比 14000/40000 = 35% → 谨慎
    assert r["判定"] == "谨慎"
    assert round(r["指标"]["新偿债收入比"], 4) == 0.35


def test_afford_installment_not_advised_ratio():
    snap = _snap_with_liquid(200000)
    txns = _txns_income_expense(40000, 10000)
    r = affordability(snap, txns, 500000, "installment", monthly=18000)
    # 偿债比 18000/40000 = 45% >40% → 暂不建议
    assert r["判定"] == "暂不建议"


def test_afford_installment_not_advised_negative_surplus():
    snap = _snap_with_liquid(200000)
    txns = _txns_income_expense(20000, 18000)  # 结余仅 2000
    r = affordability(snap, txns, 100000, "installment", monthly=5000)
    # 结余 2000-5000 = -3000 <0 → 暂不建议（即便偿债比不高）
    assert r["判定"] == "暂不建议"


def test_afford_installment_estimates_monthly_from_months():
    snap = _snap_with_liquid(200000)
    txns = _txns_income_expense(40000, 15000)
    r = affordability(snap, txns, 360000, "installment", months=36)
    # 无息估月供 = 360000/36 = 10000；偿债比 25%
    assert r["指标"]["月供"] == 10000
    assert round(r["指标"]["新偿债收入比"], 4) == 0.25


def test_afford_installment_existing_debt_counts():
    snap = _snap_with_liquid(200000)
    txns = _txns_income_expense(40000, 10000)
    txns.append(Txn("2026-06-25", "转移", "筹资", "流出", "房贷还本", 6000))
    r = affordability(snap, txns, 300000, "installment", monthly=8000)
    # 现有还债6000 + 新8000 = 14000 / 40000 = 35% → 谨慎
    assert r["判定"] == "谨慎"
    assert r["临界值"]["可承受月供上限"] == 0.3 * 40000 - 6000  # 6000


def test_afford_installment_unknown_when_no_income():
    snap = _snap_with_liquid(200000)
    txns = _txns_income_expense(0, 15000)
    r = affordability(snap, txns, 300000, "installment", monthly=9000)
    assert r["判定"] == "无法评估"


def test_afford_installment_unknown_without_monthly_or_months():
    snap = _snap_with_liquid(200000)
    txns = _txns_income_expense(40000, 15000)
    r = affordability(snap, txns, 300000, "installment")
    assert r["判定"] == "无法评估"
```

- [ ] **Step 2: 运行测试，确认通过**（实现已在 Task 1 写好；分期分支应直接通过）

Run: `uvx pytest scripts/test_family_finance.py -k afford_installment -v`
Expected: 8 passed。若有失败，回到 Task 1 的 installment 分支修正后重跑。

- [ ] **Step 3: 全量回归**

Run: `uvx pytest scripts/ -q`
Expected: 全部 passed

- [ ] **Step 4: Commit**

```bash
git add scripts/test_family_finance.py
git commit -m "test: affordability 分期可行性评估覆盖"
```

---

## Task 3: CLI 子命令 afford

**Files:**
- Modify: `scripts/family_finance.py`（`main` 内新增子解析器与处理分支）
- Test: `scripts/test_family_finance.py`

- [ ] **Step 1: 写失败测试**

```python
def test_main_afford_lump_writes_stdout(tmp_path, capsys):
    _write_csv(
        tmp_path / "transactions.csv",
        ["日期", "类型", "现金流分类", "方向", "分类", "金额", "账户", "备注"],
        [["2026-06-01", "收入", "经营", "流入", "工资", "40000", "", ""],
         ["2026-06-10", "支出", "经营", "流出", "餐饮", "20000", "", ""]],
    )
    _write_csv(
        tmp_path / "balances.csv",
        ["日期", "类型", "项目", "金额", "流动性", "性质"],
        [["2026-06-30", "资产", "活期", "600000", "流动", "可投资"]],
    )
    rc = main(["afford", "--amount", "100000", "--mode", "lump",
               "--data-dir", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "可承受" in out
    assert "应急储备" in out


def test_main_afford_installment_months(tmp_path, capsys):
    _write_csv(
        tmp_path / "transactions.csv",
        ["日期", "类型", "现金流分类", "方向", "分类", "金额", "账户", "备注"],
        [["2026-06-01", "收入", "经营", "流入", "工资", "40000", "", ""],
         ["2026-06-10", "支出", "经营", "流出", "餐饮", "15000", "", ""]],
    )
    _write_csv(
        tmp_path / "balances.csv",
        ["日期", "类型", "项目", "金额", "流动性", "性质"],
        [["2026-06-30", "资产", "活期", "200000", "流动", "可投资"]],
    )
    rc = main(["afford", "--amount", "360000", "--mode", "installment",
               "--months", "36", "--data-dir", str(tmp_path)])
    assert rc == 0
    assert "判定" in capsys.readouterr().out
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `uvx pytest scripts/test_family_finance.py -k main_afford -v`
Expected: FAIL（argparse 报错 invalid choice 'afford' 或 SystemExit）

- [ ] **Step 3: 写实现**

在 `main` 里、`args = parser.parse_args(argv)` 之前，新增子解析器（紧跟现有 `rep` 定义之后）：

```python
    aff = sub.add_parser("afford", help="评估一笔大额消费是否可承受")
    aff.add_argument("--amount", type=float, required=True, help="消费金额（¥）")
    aff.add_argument("--mode", choices=["lump", "installment"], required=True,
                     help="lump 一次性 / installment 分期")
    aff.add_argument("--monthly", type=float, default=None, help="分期月供（¥）")
    aff.add_argument("--months", type=int, default=None, help="分期期数")
    aff.add_argument("--month", default=None, help="评估基于的月份 YYYY-MM，默认最近有流水的月份")
    aff.add_argument("--data-dir", default=".", help="数据目录")
```

在 `if args.cmd == "report":` 分支之后、`return 1` 之前，新增处理分支：

```python
    if args.cmd == "afford":
        data_dir = args.data_dir
        txns = load_transactions(os.path.join(data_dir, "transactions.csv"))
        bals = load_balances(os.path.join(data_dir, "balances.csv"))
        ym = args.month or max((month_of(t.date) for t in txns), default=None)
        if not ym:
            print("无流水数据，无法评估。请先记录本月收支。")
            return 1
        snap = latest_snapshot(bals, ym)
        res = affordability(snap, txns_in_month(txns, ym),
                            args.amount, args.mode, args.monthly, args.months)
        print(f"消费评估（基于 {ym}）：{_yuan(args.amount)} / "
              f"{'一次性' if args.mode == 'lump' else '分期'}")
        print(f"判定：{res['判定']}")
        for k, v in res["指标"].items():
            if isinstance(v, float) and ("比" in k or "率" in k):
                print(f"- {k}：{v * 100:.1f}%")
            elif isinstance(v, float) and "储备" in k:
                print(f"- {k}：{v:.1f} 个月")
            else:
                print(f"- {k}：{_yuan(v)}")
        if res.get("临界值"):
            for k, v in res["临界值"].items():
                print(f"- {k}：{_yuan(v)}")
        for r in res["理由"]:
            print(f"  理由：{r}")
        print("> 说明：基于你自身数据的消费预算分析，非投资建议；作者非持牌财务顾问。")
        return 0
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `uvx pytest scripts/test_family_finance.py -k main_afford -v`
Expected: 2 passed

- [ ] **Step 5: 全量回归 + Commit**

Run: `uvx pytest scripts/ -q`
Expected: 全部 passed

```bash
git add scripts/family_finance.py scripts/test_family_finance.py
git commit -m "feat: CLI afford 子命令"
```

---

## Task 4: SKILL.md 工作流 + references/affordability.md

**Files:**
- Modify: `SKILL.md`
- Create: `references/affordability.md`

- [ ] **Step 1: 写 references/affordability.md（完整内容）**

```markdown
# 大额消费可行性评估口径

> 与 scripts/family_finance.py 的 affordability() 一致；联网/措辞在 agent 层，计算在脚本。

## 输入
- 金额 amount；付款方式 mode = lump（一次性）/ installment（分期）
- 分期补充：月供 monthly，或期数 months（只给期数则无息估 monthly = amount/months）

## 判定
一次性（流动资产 L、月支出 E、金额 A）：
- 暂不建议：A>L，或 (L−A)/E < 3
- 谨慎：3 ≤ (L−A)/E < 6
- 可承受：(L−A)/E ≥ 6
- 临界值：一次性可承受上限 = max(0, L − 6×E)

分期（月收入 I、现有月还债 D、月结余 S、月供 M）：
- 暂不建议：S−M<0，或 (D+M)/I > 0.4
- 谨慎：0.3 < (D+M)/I ≤ 0.4
- 可承受：(D+M)/I ≤ 0.3 且 S−M>0
- 临界值：可承受月供上限 = max(0, 0.3×I − D)

无法评估：一次性且月支出为 0，或分期且月收入为 0，或分期未给月供/期数。

## 边界
- 这是消费预算分析（基于用户自身数据），不构成投资建议（不推荐标的、不做择时）。
- 分期按无息估算，未做利率/IRR 精算。
```

- [ ] **Step 2: 在 SKILL.md「## 操作」中，「### 3. 出报表」之前插入新小节**

```markdown
### 2.8 消费建议（大额消费可行性）
详细口径见 `references/affordability.md`。

用户说「想买 30 万的车，合适吗 / 分期 36 期 / 月供 9000」时：
1. 解析金额、付款方式（lump 一次性 / installment 分期）、分期的月供或期数。
   **不明确就先确认**：全款还是分期？分期多少期或月供多少？
2. 调脚本：
   `python3 <skill>/scripts/family_finance.py afford --amount 300000 --mode lump --data-dir .`
   分期：`--mode installment --months 36`（或 `--monthly 9000`）。
3. 把脚本输出的「判定 + 关键数字 + 临界值」转述给用户，并补一句可落地的替代方案
   （如「降到 ¥X 以内为可承受」「改 48 期月供降到 ¥Y」）。
4. 这是基于用户数据的**消费预算分析**，**不做投资建议**；保留非持牌顾问免责。
5. 数据不足（收入/支出为 0）时，如实说明并请用户补记录，不臆断。
```

- [ ] **Step 3: 校验**

Run: `grep -n "消费建议\|afford\|affordability" SKILL.md`
Expected: 命中新内容

- [ ] **Step 4: Commit**

```bash
git add SKILL.md references/affordability.md
git commit -m "feat: SKILL.md 消费建议工作流 + references 口径"
```

---

## Task 5: 端到端冒烟 + 回归

**Files:** 临时数据目录（不入库）

- [ ] **Step 1: 造样例并跑两种付款方式**

```bash
SMOKE=$(mktemp -d)
cat > "$SMOKE/transactions.csv" <<'EOF'
日期,类型,现金流分类,方向,分类,金额,账户,备注
2026-06-01,收入,经营,流入,工资,40000,,
2026-06-10,支出,经营,流出,餐饮,18000,,
2026-06-25,转移,筹资,流出,房贷还本,5000,,
EOF
cat > "$SMOKE/balances.csv" <<'EOF'
日期,类型,项目,金额,流动性,性质
2026-06-30,资产,活期,300000,流动,可投资
2026-06-30,负债,房贷,1500000,,
EOF
echo "--- 一次性 30 万 ---"
python3 scripts/family_finance.py afford --amount 300000 --mode lump --data-dir "$SMOKE"
echo "--- 分期 30 万 / 36 期 ---"
python3 scripts/family_finance.py afford --amount 300000 --mode installment --months 36 --data-dir "$SMOKE"
rm -rf "$SMOKE"
```

- [ ] **Step 2: 人工核对**

Expected：
- 一次性：流动 30 万 − 30 万 = 0，应急储备 0 个月 → **暂不建议**；一次性可承受上限 = 300000 − 6×18000 = 192000
- 分期：月供 = 300000/36 ≈ 8333；偿债比 = (5000+8333)/40000 ≈ 33.3% → **谨慎**；可承受月供上限 = 0.3×40000 − 5000 = 7000
- 两条输出末尾都有「非投资建议」免责

- [ ] **Step 3: 全量回归**

Run: `uvx pytest scripts/ -q`
Expected: 全部 passed

---

## 自检结论（写作者已核对）

- **规格覆盖**：一次性三档+不足+无支出(Task1)、分期三档+结余转负+无息估+现有还债+无收入+缺参数(Task2)、CLI(Task3)、SKILL.md 工作流+references(Task4)、端到端(Task5)。临界值(Task1/2)、免责(Task3/4)均覆盖。
- **类型一致**：`affordability(snap, txns, amount, mode, monthly=None, months=None)` 返回 `判定/指标/临界值/理由`，CLI 与测试按此读取；指标键名（付后应急储备/流动资产剩余/月供/新偿债收入比/新月结余/新负债率）前后一致。
- **无占位符**：每步均含完整代码或命令。
- **架构一致**：计算全在脚本、零联网零依赖；估值/建议措辞与联网在 agent 层。
