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
