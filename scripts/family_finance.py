# scripts/family_finance.py
"""家庭财务：计算三表、健康评分、财富等级，并渲染 Markdown 报表。仅用标准库。"""
import argparse
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
    source: str = ""     # 来源: 行情 / 搜索 / 手填
    valued_at: str = ""  # 估值日期 YYYY-MM-DD
    confidence: str = "" # 置信度: 高 / 中 / 低


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
                r.get("来源", "") or "", r.get("估值日期", "") or "",
                r.get("置信度", "") or "",
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


# (等级名, 下限含, 上限不含)；上限 None 表示无上界
_TIERS = [
    ("温饱", 0, 100_000),
    ("小康", 100_000, 500_000),
    ("宽裕", 500_000, 6_000_000),
    ("富足", 6_000_000, 10_000_000),
    ("财务自由", 10_000_000, 100_000_000),
    ("财富自由", 100_000_000, None),
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
    if amount < 0:
        lo, hi = _TIERS[0][1], _TIERS[0][2]
        return {"等级": _TIERS[0][0], "下一档": _TIERS[1][0], "距下一档": hi - amount}
    for i, (name, lo, hi) in enumerate(_TIERS):
        in_tier = (amount >= lo) and (hi is None or amount < hi)
        if in_tier:
            if hi is None:
                return {"等级": name, "下一档": None, "距下一档": None}
            nxt = _TIERS[i + 1][0]
            return {"等级": name, "下一档": nxt, "距下一档": hi - amount}
    return {"等级": _TIERS[0][0], "下一档": _TIERS[1][0], "距下一档": _TIERS[0][2] - amount}


def _yuan(x):
    return f"-¥{-x:,.0f}" if x < 0 else f"¥{x:,.0f}"


def _valuation_note(b):
    """资产估值标注：（来源·日期·置信度）；搜索类前加 ⚠估；手填/无来源返回空串。"""
    if not b.source or b.source == "手填":
        return ""
    parts = [b.source]
    if b.valued_at:
        parts.append(b.valued_at)
    if b.confidence:
        parts.append(b.confidence)
    mark = " ⚠估" if b.source == "搜索" else ""
    return f"{mark}（{'·'.join(parts)}）"


def _rows_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |",
           "| " + " | ".join(["---"] * len(headers)) + " |"]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(out)


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


def render_report(ym, snap, txns):
    parts = [f"# {ym} 家庭财务报表\n"]

    # 一、资产负债表
    parts.append("## 一、资产负债表\n")
    bs = balance_sheet(snap)
    if not snap:
        parts.append("> 暂无资产负债快照，请先用「更新余额」记录一次。\n")
    else:
        rows = [("资产", b.item + _valuation_note(b), _yuan(b.amount))
                for b in snap if b.kind == "资产"]
        rows += [("负债", b.item, _yuan(b.amount))
                 for b in snap if b.kind == "负债"]
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
        ("日常收支净额（经营）", _yuan(cf["经营性净现金流"])),
        ("投资进出净额（投资）", _yuan(cf["投资性净现金流"])),
        ("借还款净额（筹资）", _yuan(cf["筹资性净现金流"])),
        ("**当月现金净变动**", f"**{_yuan(cf['净现金流合计'])}**"),
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
    if any(b.kind == "资产" and b.source in ("行情", "搜索") for b in snap):
        parts.append("> 含市场估值的项目为某时点估算，房产为区域均价粗估，仅供参考。")
    return "\n".join(parts) + "\n"


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
