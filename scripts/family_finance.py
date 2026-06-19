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
