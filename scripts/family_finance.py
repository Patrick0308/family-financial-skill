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
