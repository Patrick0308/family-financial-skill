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
