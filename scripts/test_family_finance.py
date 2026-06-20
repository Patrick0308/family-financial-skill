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
    assert round(r["资产负债率"], 4) == 0.51       # 510000/1000000
    assert round(r["偿债收入比"], 4) == 0.2        # 4000/20000
    assert round(r["应急储备"], 4) == 20.0         # 200000/10000
    assert round(r["投资资产比"], 4) == 0.2        # 200000/1000000


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
    assert res["等级"] == "宽裕"
    assert res["距下一档"] == 6000000 - 1250000  # 距「富足」下限 600万
    assert res["下一档"] == "富足"


def test_wealth_tier_top_has_no_next():
    res = wealth_tier(150000000)
    assert res["等级"] == "财富自由"
    assert res["下一档"] is None
    assert res["距下一档"] is None


def test_wealth_tier_negative_falls_into_lowest():
    res = wealth_tier(-50000)
    assert res["等级"] == "温饱"
    assert res["下一档"] == "小康"
    assert res["距下一档"] == 100000 - (-50000)  # 150000


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
        "当月现金净变动",
        "/ 100",
        "非持牌",  # 免责声明
    ]:
        assert marker in md, marker


def test_render_report_handles_no_snapshot():
    txns = [Txn("2026-06-01", "收入", "经营", "流入", "工资", 20000)]
    md = render_report("2026-06", [], txns)
    assert "暂无资产负债快照" in md


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
