# scripts/family_finance.py
"""家庭财务：计算三表、健康评分、财富等级，并渲染 Markdown 报表。仅用标准库。"""
import csv
import os
import calendar
from dataclasses import dataclass
from collections import OrderedDict


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
