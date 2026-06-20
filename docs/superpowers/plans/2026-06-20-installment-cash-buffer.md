# 分期评估增强（现金缓冲 + 首付）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 增强 `affordability()` 的分期分支：支持首付（`down`），并把现金缓冲（付后应急储备）与还款面（偿债比）「取最严」合成判定。

**Architecture:** 改 `scripts/family_finance.py` 的 installment 分支为 A 现金面 + B 还款面双档取严，新增 `down` 参数与「首付上限」临界值；CLI `afford` 增 `--down`。全款分支不变，纯分期（down=0）会叠加现金面检查。零联网、零依赖、可单测。

**Tech Stack:** Python 3 标准库；pytest（`uvx pytest`）；Markdown。

参考规格：`docs/superpowers/specs/2026-06-20-installment-cash-buffer-design.md`

---

## 文件结构

```
scripts/family_finance.py        # 改：affordability installment 分支 + 签名 down 参数
scripts/test_family_finance.py   # 改：新增分期增强测试
SKILL.md                         # 改：分期口径/--down 说明
references/affordability.md       # 改：分期 A+B 双判定、--down、首付上限
```

---

## Task 1: affordability 分期分支增强（down + A/B 取严）

**Files:**
- Modify: `scripts/family_finance.py`（签名 :329；installment 分支 :367-397）
- Test: `scripts/test_family_finance.py`

设计要点：
- 签名加 `down=0`。
- 分期金额 financed = amount − down；月供 M = monthly 或 financed/months。
- A 现金面：post_reserve = (流动资产 − down)/月支出 → 档位（≥6=0 可承受 / 3–6=1 谨慎 / <3=2 暂不建议）；down>流动资产 直接 A 档=2。
- B 还款面：new_ratio = (现有月供 + M)/月收入 → 档位（≤0.3=0 / 0.3–0.4=1 / >0.4=2）；月结余−M<0 直接 B 档=2。
- 判定 = max(A 档, B 档) → ["可承受","谨慎","暂不建议"]。理由列出达到最严档的那一面（并列都列）。
- 无法评估：月收入≤0 或 月支出≤0；down≥amount（提示用全款）；缺 monthly 且缺 months。
- 临界值：可承受月供上限 = max(0, 0.3×月收入 − 现有月供)；首付上限 = max(0, 流动资产 − 3×月支出)。

- [ ] **Step 1: 写失败测试**（追加到测试文件末尾，复用已有 `_snap_with_liquid` / `_txns_income_expense`）

```python
def test_afford_install_blocked_by_cash_side():
    # 还款面宽松（偿债比低），但现金薄：付后应急 <3 个月 → 暂不建议（现金面卡住）
    snap = _snap_with_liquid(40000)            # 流动 4 万
    txns = _txns_income_expense(40000, 20000)  # 月支出 2 万 → 4万/2万=2 个月
    r = affordability(snap, txns, 300000, "installment", monthly=5000)  # 偿债比 12.5%
    assert r["判定"] == "暂不建议"
    assert any("现金面" in x for x in r["理由"])


def test_afford_install_blocked_by_repay_side():
    # 现金充裕（应急很高），但偿债比 >40% → 暂不建议（还款面卡住）
    snap = _snap_with_liquid(2000000)          # 流动 200 万
    txns = _txns_income_expense(40000, 10000)
    r = affordability(snap, txns, 500000, "installment", monthly=18000)  # 45%
    assert r["判定"] == "暂不建议"
    assert any("还款面" in x for x in r["理由"])


def test_afford_install_takes_stricter_tier():
    # 现金面=谨慎（应急 4 个月），还款面=可承受（22.5%）→ 取谨慎
    snap = _snap_with_liquid(80000)            # 流动 8 万
    txns = _txns_income_expense(40000, 20000)  # 月支出 2 万 → 8万/2万=4 个月（谨慎）
    r = affordability(snap, txns, 300000, "installment", monthly=9000)  # 22.5%（可承受）
    assert r["判定"] == "谨慎"
    assert any("现金面" in x for x in r["理由"])


def test_afford_install_down_payment_drains_cash():
    # 首付掏走大部分流动资产 → 现金面卡住
    snap = _snap_with_liquid(200000)
    txns = _txns_income_expense(40000, 20000)
    r = affordability(snap, txns, 300000, "installment", monthly=6000, down=160000)
    # 付首付后流动 = 4万 → 应急 2 个月 → 暂不建议
    assert r["判定"] == "暂不建议"
    assert any("现金面" in x for x in r["理由"])


def test_afford_install_down_exceeds_liquid():
    snap = _snap_with_liquid(50000)
    txns = _txns_income_expense(40000, 20000)
    r = affordability(snap, txns, 300000, "installment", monthly=6000, down=100000)
    assert r["判定"] == "暂不建议"
    assert any("首付" in x for x in r["理由"])


def test_afford_install_financed_uses_amount_minus_down():
    # 月供由 financed/months 推算：financed=(300000-60000)=240000，36期 → 月供 6666.67
    snap = _snap_with_liquid(600000)
    txns = _txns_income_expense(40000, 15000)
    r = affordability(snap, txns, 300000, "installment", months=36, down=60000)
    assert round(r["指标"]["月供"], 2) == round(240000 / 36, 2)


def test_afford_install_thresholds():
    snap = _snap_with_liquid(600000)
    txns = _txns_income_expense(40000, 15000)
    txns.append(Txn("2026-06-25", "转移", "筹资", "流出", "房贷还本", 4000))
    r = affordability(snap, txns, 300000, "installment", monthly=8000)
    assert r["临界值"]["可承受月供上限"] == 0.3 * 40000 - 4000   # 8000
    assert r["临界值"]["首付上限"] == 600000 - 3 * 15000        # 555000


def test_afford_install_down_ge_amount_unknown():
    snap = _snap_with_liquid(600000)
    txns = _txns_income_expense(40000, 15000)
    r = affordability(snap, txns, 300000, "installment", monthly=8000, down=300000)
    assert r["判定"] == "无法评估"
    assert any("全款" in x for x in r["理由"])


def test_afford_install_unknown_when_no_expense():
    snap = _snap_with_liquid(600000)
    txns = _txns_income_expense(40000, 0)  # 无支出 → A 无法算
    r = affordability(snap, txns, 300000, "installment", monthly=8000)
    assert r["判定"] == "无法评估"
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `uvx pytest scripts/test_family_finance.py -k "afford_install_" -v`
Expected: 多数 FAIL（如 `TypeError: affordability() got an unexpected keyword argument 'down'`，或判定/理由不符）

- [ ] **Step 3: 改实现**

(a) 改签名（`family_finance.py:329`）：

```python
def affordability(snap, txns, amount, mode, monthly=None, months=None, down=0):
```

(b) 整段替换 installment 分支（当前 `if mode == "installment":` 到其 `return` 结束）为：

```python
    if mode == "installment":
        if income <= 0 or expense <= 0:
            return _cannot_assess("分期评估需要当月收入与支出数据，请先记录本月收支。")
        if down >= amount:
            return _cannot_assess("首付已覆盖全价，请用全款（lump）评估。")
        financed = amount - down
        if monthly is None:
            if months and months > 0:
                monthly = financed / months
            else:
                return _cannot_assess("分期需要提供月供或期数。")

        post_reserve = (liquid - down) / expense
        new_ratio = (existing_debt + monthly) / income
        new_surplus = surplus - monthly
        new_debt_ratio = (bs["负债合计"] + financed) / bs["资产合计"] if bs["资产合计"] else 0.0
        max_monthly = max(0.0, 0.3 * income - existing_debt)
        max_down = max(0.0, liquid - 3 * expense)

        # A 现金面
        if down > liquid:
            a_tier = 2
            a_reason = f"首付 {_yuan(down)} 超过流动资产 {_yuan(liquid)}，连首付都掏不出。"
        elif post_reserve < 3:
            a_tier = 2
            a_reason = f"付首付后应急储备降至 {post_reserve:.1f} 个月（建议 ≥3 个月）。"
        elif post_reserve < 6:
            a_tier = 1
            a_reason = f"付首付后应急储备 {post_reserve:.1f} 个月（处于 3–6 个月）。"
        else:
            a_tier = 0
            a_reason = f"付首付后应急储备仍有 {post_reserve:.1f} 个月（≥6 个月）。"

        # B 还款面
        if new_surplus < 0:
            b_tier = 2
            b_reason = f"新增月供 {_yuan(monthly)} 后月结余转负（{_yuan(new_surplus)}）。"
        elif new_ratio > 0.4:
            b_tier = 2
            b_reason = f"偿债收入比升至 {new_ratio * 100:.1f}%（建议 ≤40%）。"
        elif new_ratio > 0.3:
            b_tier = 1
            b_reason = f"偿债收入比 {new_ratio * 100:.1f}%（处于 30–40%）。"
        else:
            b_tier = 0
            b_reason = f"偿债收入比 {new_ratio * 100:.1f}%（≤30%），月结余为正。"

        tier = max(a_tier, b_tier)
        verdict = ["可承受", "谨慎", "暂不建议"][tier]
        reasons = []
        if a_tier == tier:
            reasons.append("现金面：" + a_reason)
        if b_tier == tier:
            reasons.append("还款面：" + b_reason)
        return {
            "判定": verdict,
            "指标": {"付后应急储备": post_reserve, "月供": monthly,
                     "新偿债收入比": new_ratio, "新月结余": new_surplus,
                     "新负债率": new_debt_ratio},
            "临界值": {"可承受月供上限": max_monthly, "首付上限": max_down},
            "理由": reasons,
        }
```

- [ ] **Step 4: 运行新测试，确认通过**

Run: `uvx pytest scripts/test_family_finance.py -k "afford_install_" -v`
Expected: 9 passed

- [ ] **Step 5: 全量回归（确认既有分期/CLI 测试不受影响）**

Run: `uvx pytest scripts/ -q`
Expected: 全部 passed。既有分期测试因流动资产充足（应急 ≥6 个月）现金面均为可承受，判定不变；如个别失败，按设计核对其数据是否触发了新增 A 检查并调整测试数据使其表达原意图。

- [ ] **Step 6: Commit**

```bash
git add scripts/family_finance.py scripts/test_family_finance.py
git commit -m "feat: 分期评估增强——首付 down + 现金面/还款面取严"
```

---

## Task 2: CLI 增 --down

**Files:**
- Modify: `scripts/family_finance.py`（`afford` 子解析器与处理分支）
- Test: `scripts/test_family_finance.py`

- [ ] **Step 1: 写失败测试**

```python
def test_main_afford_installment_with_down(tmp_path, capsys):
    _write_csv(
        tmp_path / "transactions.csv",
        ["日期", "类型", "现金流分类", "方向", "分类", "金额", "账户", "备注"],
        [["2026-06-01", "收入", "经营", "流入", "工资", "40000", "", ""],
         ["2026-06-10", "支出", "经营", "流出", "餐饮", "20000", "", ""]],
    )
    _write_csv(
        tmp_path / "balances.csv",
        ["日期", "类型", "项目", "金额", "流动性", "性质"],
        [["2026-06-30", "资产", "活期", "200000", "流动", "可投资"]],
    )
    rc = main(["afford", "--amount", "300000", "--mode", "installment",
               "--months", "36", "--down", "160000", "--data-dir", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "判定" in out
    assert "首付上限" in out
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `uvx pytest scripts/test_family_finance.py -k main_afford_installment_with_down -v`
Expected: FAIL（argparse: unrecognized arguments: --down）

- [ ] **Step 3: 改实现**

(a) 在 `afford` 子解析器里（`--months` 之后）新增：

```python
    aff.add_argument("--down", type=float, default=0, help="分期首付（¥），默认 0")
```

(b) 在 afford 处理分支里，把 `affordability(...)` 调用补上 `down`：

```python
        res = affordability(snap, txns_in_month(txns, ym),
                            args.amount, args.mode, args.monthly, args.months,
                            down=args.down)
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `uvx pytest scripts/test_family_finance.py -k main_afford_installment_with_down -v`
Expected: 1 passed

- [ ] **Step 5: 全量回归 + Commit**

Run: `uvx pytest scripts/ -q`
Expected: 全部 passed

```bash
git add scripts/family_finance.py scripts/test_family_finance.py
git commit -m "feat: CLI afford 增 --down 首付参数"
```

---

## Task 3: 文档同步（references + SKILL.md）

**Files:**
- Modify: `references/affordability.md`
- Modify: `SKILL.md`

- [ ] **Step 1: 更新 references/affordability.md 的分期段**

把现有「分期（月收入 I...）」整段替换为：

```markdown
分期（月收入 I、月支出 E、流动资产 L、现有月还债 D、月结余 S、首付 down、总价 amount）：
- 分期金额 financed = amount − down；月供 M = monthly 或 financed/期数（无息估）
- A 现金面：付后应急储备 = (L − down)/E → ≥6 可承受 / 3–6 谨慎 / <3 暂不建议；down>L 直接暂不建议
- B 还款面：偿债比 = (D + M)/I → ≤30% 可承受 / 30–40% 谨慎 / >40% 暂不建议；S−M<0 直接暂不建议
- 判定 = A、B 取更严的一档；理由点明现金面/还款面
- 临界值：可承受月供上限 = max(0, 0.3×I − D)；首付上限 = max(0, L − 3×E)

无法评估：月收入或月支出为 0；首付 ≥ 总价（请用全款）；未给月供且未给期数。
```

- [ ] **Step 2: 更新 SKILL.md「### 2.8 消费建议」里分期相关说明**

在该小节的命令示例处补充 `--down`，并加一句双判定说明。把分期命令行示例改为：

```markdown
   分期：`--mode installment --months 36`（或 `--monthly 9000`）；有首付加 `--down 60000`。
   分期会同时看「现金面（付首付后应急储备）」和「还款面（偿债比）」，取更严的一档。
```

- [ ] **Step 3: 校验**

Run: `grep -n "首付\|--down\|现金面\|还款面" SKILL.md references/affordability.md`
Expected: 命中新增内容

- [ ] **Step 4: Commit**

```bash
git add references/affordability.md SKILL.md
git commit -m "docs: 分期评估口径同步——首付与现金面/还款面双判定"
```

---

## Task 4: 端到端冒烟 + 回归

**Files:** 临时数据目录（不入库）

- [ ] **Step 1: 造样例并跑首付/无首付对比**

```bash
SMOKE=$(mktemp -d)
cat > "$SMOKE/transactions.csv" <<'EOF'
日期,类型,现金流分类,方向,分类,金额,账户,备注
2026-06-01,收入,经营,流入,工资,44800,,
2026-06-10,支出,经营,流出,餐饮,18100,,
2026-06-25,转移,筹资,流出,房贷还本,5500,,
EOF
cat > "$SMOKE/balances.csv" <<'EOF'
日期,类型,项目,金额,流动性,性质
2026-06-30,资产,活期,120000,流动,可投资
2026-06-30,资产,定期存款,300000,流动,可投资
2026-06-30,资产,基金,180000,流动,可投资
2026-06-30,负债,房贷,1500000,,
EOF
echo "--- 分期 35 万 / 36 期 / 无首付 ---"
python3 scripts/family_finance.py afford --amount 350000 --mode installment --months 36 --data-dir "$SMOKE"
echo "--- 分期 35 万 / 36 期 / 首付 40 万（掏空大半现金）---"
python3 scripts/family_finance.py afford --amount 350000 --mode installment --months 36 --down 400000 --data-dir "$SMOKE"
rm -rf "$SMOKE"
```

- [ ] **Step 2: 人工核对**

Expected：
- 无首付：流动 60 万 → 付后应急 60万/1.81万 ≈ 33 个月（现金面可承受）；月供 350000/36 ≈ 9722，偿债比 (5500+9722)/44800 ≈ 34%（还款面谨慎）→ **取严=谨慎**，理由含「还款面」。
- 首付 40 万：down(40万) < 流动(60万) 不触发硬性；付后应急 =(60万−40万)/1.81万 ≈ 11 个月（仍可承受）；financed=350000−400000<0 → down≥amount? 否（40万<35万？不，40万>35万）→ **down≥amount 成立 → 无法评估（提示用全款）**。
  - 注：示例首付 40 万 > 总价 35 万，正好演示「首付≥总价→提示全款」。如需演示现金面卡住，可改 `--down 300000`（首付 30 万 < 35 万；付后应急 =(60万−30万)/1.81万 ≈ 16.6 个月仍可承受，财务太健康不易卡住，可把活期改小）。

- [ ] **Step 3: 全量回归**

Run: `uvx pytest scripts/ -q`
Expected: 全部 passed

---

## 自检结论（写作者已核对）

- **规格覆盖**：down 参数+financed(Task1)、A 现金面/B 还款面取严(Task1)、硬性条件(Task1)、临界值含首付上限(Task1)、无法评估三类(Task1)、CLI --down(Task2)、文档同步(Task3)、端到端(Task4)。
- **类型一致**：`affordability(..., down=0)`；installment 指标键 付后应急储备/月供/新偿债收入比/新月结余/新负债率；临界值键 可承受月供上限/首付上限；CLI 透传 down。
- **向后兼容**：down 默认 0；已逐个核对既有 6 个分期测试与 2 个 CLI 测试在新逻辑下判定不变（流动资产充足→现金面可承受，不改变取严结果），无需改既有测试。
- **无占位符**：每步均含完整代码或命令。
