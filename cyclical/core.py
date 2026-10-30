"""A股周期行业估值扫描：用 PB 分位 + 盈利位置，而不是 PE。

单文件、零外部依赖（除 pandas/pyarrow），数据随仓库提供。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# 周期性行业的关键词。A 股的行业分类用的是细分名（铜、铝、水运），
# 不是"有色"这种大类，所以关键词要写到细分层。
CYCLICAL_WORDS = (
    "有色", "小金属", "矿物制品", "铝", "铜", "铅锌", "黄金", "稀土", "钨", "锂",
    "钢铁", "普钢", "特种钢", "钢加工",
    "煤炭", "石油", "采掘", "焦炭",
    "化工", "化纤", "水泥", "建材", "玻璃", "造纸",
    "航运", "水运", "港口", "船舶", "航空", "物流", "仓储物流",
    "养殖", "农林牧渔", "房地产", "汽车", "机械",
    "半导体", "面板",
)

TAG_TOP = "周期顶（PB贵+盈利高）"
TAG_BOTTOM = "周期底（PB便宜+盈利低）"
TAG_CHEAP = "PB 便宜"
TAG_RICH = "PB 偏贵"
TAG_MID = "中性"
TAG_NA = "历史不可比"
TAG_LACK = "数据不足"


@dataclass
class CycRow:
    code: str
    name: str
    industry: str
    chain: str = ""
    main_business: str = ""
    stale: bool = False
    price: Optional[float] = None
    pe: Optional[float] = None
    pe_pct: Optional[float] = None
    pb: Optional[float] = None
    pb_pct: Optional[float] = None
    dy: Optional[float] = None
    profit_yi: Optional[float] = None
    profit_med_yi: Optional[float] = None
    earn_pos: Optional[float] = None
    norm_pe: Optional[float] = None
    years: Optional[int] = None
    gross_margin: Optional[float] = None
    net_margin_vol: Optional[float] = None
    debt_ratio: Optional[float] = None
    ocf_to_profit: Optional[float] = None
    nm_shift: Optional[float] = None
    loss_years: Optional[int] = None
    profit_cv: Optional[float] = None
    cv_vs_industry: Optional[float] = None
    median_rel_se: Optional[float] = None
    profit_reliable: bool = True
    profit_note: str = ""
    market_cap_yi: Optional[float] = None
    comparable: bool = True
    tag: str = ""

    def as_dict(self) -> dict:
        return {k: (round(v, 4) if isinstance(v, float) else v)
                for k, v in self.__dict__.items()}


def percentile_of(series: pd.Series, value: float) -> Optional[float]:
    s = pd.to_numeric(series, errors="coerce").dropna()
    if s.empty or value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    return float((s <= value).mean() * 100.0)


def load_data(data_dir: Optional[Path] = None) -> dict:
    d = data_dir or DATA_DIR
    return {
        "panel": pd.read_parquet(d / "valuation_panel.parquet"),
        "snapshot": pd.read_parquet(d / "snapshot.parquet"),
        "financials": pd.read_parquet(d / "financials.parquet"),
        "company": pd.read_parquet(d / "company.parquet"),
    }


def cyclical_industries(snapshot: pd.DataFrame) -> set:
    out = set()
    for ind in snapshot["industry"].dropna().unique():
        if any(w in str(ind) for w in CYCLICAL_WORDS):
            out.add(str(ind))
    return out


def _quality(fin: pd.DataFrame) -> dict:
    """每只股票的质量指标：毛利率、净利率波动、负债率、现金流/利润。"""
    q = {}
    for code, g in fin.sort_values("end_date").groupby("ts_code"):
        nm = pd.to_numeric(g.get("netprofit_margin"), errors="coerce").dropna()
        gm = pd.to_numeric(g.get("grossprofit_margin"), errors="coerce").dropna()
        da = pd.to_numeric(g.get("debt_to_assets"), errors="coerce").dropna()
        ocf = pd.to_numeric(g.get("ocfps"), errors="coerce").dropna()
        eps = pd.to_numeric(g.get("eps"), errors="coerce").dropna()
        ratio = None
        if len(ocf) and len(eps):
            e = float(eps.iloc[-1])
            if e > 0.01:
                ratio = round(float(ocf.iloc[-1]) / e, 2)
        _pf = pd.to_numeric(g["profit_dedt"], errors="coerce").dropna()
        loss_years = int((_pf < 0).sum())
        _med = float(_pf.median()) if len(_pf) else 0.0
        _sd = float(_pf.std()) if len(_pf) >= 5 else None
        profit_cv = round(_sd / abs(_med), 2) if (_sd is not None and abs(_med) > 0) else None
        nm_shift = None
        if len(nm) >= 4:
            nm_shift = round(float(nm.tail(3).median()) - float(nm.median()), 1)
        q[code] = {
            "gm": round(float(gm.iloc[-1]), 1) if len(gm) else None,
            "nm_vol": round(float(nm.std()), 1) if len(nm) >= 4 else None,
            "debt": round(float(da.iloc[-1]), 1) if len(da) else None,
            "ocf": ratio,
            "nm_shift": nm_shift,
            "loss_years": loss_years,
            "profit_cv": profit_cv,
        }
    return q


def _tag(r: CycRow) -> str:
    if not r.comparable:
        return TAG_NA
    if r.pb_pct is None:
        return TAG_LACK
    low_pb, high_pb = r.pb_pct <= 30, r.pb_pct >= 70
    pos = r.earn_pos
    high_earn = pos is not None and pos >= 1.5
    low_earn = pos is not None and pos <= 0.7
    if not r.profit_reliable:
        high_earn = low_earn = False
    if high_pb and high_earn:
        return TAG_TOP
    if low_pb and low_earn:
        return TAG_BOTTOM
    if low_pb:
        return TAG_CHEAP
    if high_pb:
        return TAG_RICH
    return TAG_MID


def scan(data: Optional[dict] = None, industries: Optional[set] = None,
         min_cap_yi: float = 50.0) -> List[CycRow]:
    data = data or load_data()
    snap, panel, fin, co = (data["snapshot"], data["panel"],
                            data["financials"], data["company"])

    cyc = industries or cyclical_industries(snap)
    uni = snap[snap["industry"].isin(cyc)].copy()
    for c in ("pe_ttm", "pb", "dv_ttm", "total_mv", "close"):
        if c in uni.columns:
            uni[c] = pd.to_numeric(uni[c], errors="coerce")
    if min_cap_yi and "total_mv" in uni.columns:
        uni = uni[uni["total_mv"] / 1e4 >= min_cap_yi]

    pb_panel = panel.pivot_table(index="trade_date", columns="ts_code", values="pb")
    pe_panel = panel.pivot_table(index="trade_date", columns="ts_code", values="pe_ttm")

    # 盈利历史：用扣非净利润而不是 EPS（EPS 会被股本变动扭曲）
    fh = fin.dropna(subset=["profit_dedt"])
    g = fh.sort_values("end_date").groupby("ts_code")
    p_med, p_last, p_n = (g["profit_dedt"].median(), g["profit_dedt"].last(),
                          g["profit_dedt"].count())
    quality = _quality(fin)

    co_map, biz = {}, {}
    if co is not None and not co.empty:
        for _, x in co.iterrows():
            co_map[x["ts_code"]] = x.get("chain", "")
            biz[x["ts_code"]] = str(x.get("main_business", ""))

    out = []
    for _, r in uni.iterrows():
        code = r["ts_code"]
        row = CycRow(
            code=code, name=str(r["name"]), industry=str(r["industry"]),
            chain=co_map.get(code, ""), main_business=biz.get(code, ""),
            price=float(r["close"]) if pd.notna(r.get("close")) else None,
            pe=float(r["pe_ttm"]) if pd.notna(r.get("pe_ttm")) else None,
            pb=float(r["pb"]) if pd.notna(r.get("pb")) else None,
            dy=float(r["dv_ttm"]) if pd.notna(r.get("dv_ttm")) else None,
            market_cap_yi=round(float(r["total_mv"]) / 1e4, 0) if pd.notna(r.get("total_mv")) else None,
        )
        if code in pb_panel.columns:
            s = pb_panel[code].dropna()
            s = s[(s > 0) & (s < 50)]
            if len(s) >= 24 and row.pb:
                row.pb_pct = round(percentile_of(s, row.pb) or 0, 0)
        if code in pe_panel.columns:
            s = pe_panel[code].dropna()
            s = s[(s > 0) & (s < 1000)]
            if len(s) >= 24 and row.pe:
                row.pe_pct = round(percentile_of(s, row.pe) or 0, 0)
        if code in p_n.index:
            row.years = int(p_n[code])
        if code in p_med.index:
            med = float(p_med[code])
            row.profit_med_yi = round(med / 1e8, 1) if med == med else None
            if med == med and med <= 0:
                row.comparable = False
            elif med == med and row.market_cap_yi:
                row.norm_pe = round(row.market_cap_yi * 1e8 / med, 1)
                npl = float(p_last.get(code, float("nan")))
                if npl == npl:
                    pos = npl / med
                    if pos > 20 or pos < -20:
                        row.comparable = False
                    else:
                        row.earn_pos = round(pos, 2)
                        row.profit_yi = round(npl / 1e8, 1)
        if row.main_business:
            from .company import looks_stale
            row.stale = looks_stale(row.main_business, row.industry)
        q = quality.get(code) or {}
        row.gross_margin, row.net_margin_vol = q.get("gm"), q.get("nm_vol")
        row.debt_ratio, row.ocf_to_profit = q.get("debt"), q.get("ocf")
        row.nm_shift = q.get("nm_shift")
        row.loss_years = q.get("loss_years")
        row.profit_cv = q.get("profit_cv")
        if row.profit_cv is not None and row.years:
            row.median_rel_se = round(1.25 * row.profit_cv / (row.years ** 0.5), 2)
        if row.median_rel_se is not None and row.median_rel_se > 0.6:
            row.profit_reliable = False
            row.profit_note = (f"中位数相对标准误 {row.median_rel_se:.0%}"
                               f"（样本 {row.years} 年），中位不可靠")
        elif row.loss_years is not None and row.loss_years >= 5:
            row.profit_reliable = False
            row.profit_note = f"十年里 {row.loss_years} 年扣非亏损，中位不可靠"
        elif row.earn_pos is not None and abs(row.earn_pos) > 10:
            row.profit_reliable = False
            row.profit_note = "盈利位置超过 10 倍，基数失真"
        row.tag = _tag(row)
        out.append(row)
    return out


def sort_rows(rows: List[CycRow], mode: str = "pb_asc") -> List[CycRow]:
    if mode == "pb_desc":
        return sorted(rows, key=lambda x: -(x.pb_pct if x.pb_pct is not None else -1))
    if mode == "earn":
        return sorted(rows, key=lambda x: -(x.earn_pos if x.earn_pos is not None else -99))
    if mode == "pe_asc":
        return sorted(rows, key=lambda x: (x.pe_pct if x.pe_pct is not None else 999))
    return sorted(rows, key=lambda x: (x.pb_pct if x.pb_pct is not None else 999))


def summarize(rows: List[CycRow]) -> str:
    from collections import Counter
    c = Counter(r.tag for r in rows)
    return f"共 {len(rows)} 只 ｜ " + " ｜ ".join(f"{k} {v}" for k, v in c.most_common())


def format_table(rows: List[CycRow], limit: int = 40) -> str:
    head = (f"{'代码':<11}{'名称':<9}{'行业':<7}{'链条':<7}{'判断':<18}"
            f"{'PB':>6}{'PB分位':>7}{'盈利位置':>9}{'正常化PE':>9}"
            f"{'PE':>7}{'PE分位':>7}{'毛利':>5}{'波动':>5}{'负债':>5}{'现金':>6}")
    lines = [head, "-" * 122]

    def f(v, nd=2):
        return f"{v:.{nd}f}" if isinstance(v, (int, float)) else "-"

    for r in rows[:limit]:
        lines.append(
            f"{r.code:<11}{r.name[:8]:<9}{r.industry[:6]:<7}"
            f"{(r.chain or '-')[:6]:<7}{r.tag:<18}"
            f"{f(r.pb):>6}{f(r.pb_pct, 0):>7}{f(r.earn_pos):>9}{f(r.norm_pe):>9}"
            f"{f(r.pe):>7}{f(r.pe_pct, 0):>7}"
            f"{f(r.gross_margin, 0):>5}{f(r.net_margin_vol, 1):>5}"
            f"{f(r.debt_ratio, 0):>5}{f(r.ocf_to_profit):>6}")
    return "\n".join(lines)
