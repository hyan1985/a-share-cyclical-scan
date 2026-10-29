"""刷新数据并重建面板。

两种模式：
  默认（每日）：只拉当天快照，重算分位，重建 HTML。不写 parquet 面板，
                避免每天提交 6.7MB 让仓库爆炸。
  --full（每月）：额外刷新财务与主营业务，并把当月样本并入估值面板。

用法：
  python tools/refresh.py --token $TUSHARE_TOKEN
  python tools/refresh.py --token $TUSHARE_TOKEN --full
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DATA = ROOT / "data"
DOCS = ROOT / "docs"

SNAPSHOT_COLS = ["ts_code", "name", "industry", "pe_ttm", "pb", "dv_ttm", "total_mv", "close"]


def _pro(token: str):
    import tushare as ts
    return ts.pro_api(token)


def _latest_trade_date(pro) -> str:
    cal = pro.trade_cal(exchange="SSE", is_open="1",
                        start_date=pd.Timestamp.now().strftime("%Y%m%d"))
    cal = cal[cal["cal_date"] <= pd.Timestamp.now().strftime("%Y%m%d")]
    if cal.empty:
        raise SystemExit("拿不到交易日历")
    return str(cal["cal_date"].max())


def fetch_snapshot(pro, date: str) -> pd.DataFrame:
    db = pro.daily_basic(trade_date=date,
                         fields="ts_code,pe_ttm,pb,dv_ttm,total_mv")
    px = pro.daily(trade_date=date, fields="ts_code,close")
    if db is None or db.empty:
        raise SystemExit(f"{date} 没有 daily_basic 数据（可能还没更新）")
    return db.merge(px, on="ts_code", how="left")


def refresh_snapshot(pro, date: str) -> pd.DataFrame:
    old = pd.read_parquet(DATA / "snapshot.parquet")
    basis = old[["ts_code", "name", "industry"]].drop_duplicates("ts_code")
    new = fetch_snapshot(pro, date).merge(basis, on="ts_code", how="left")
    # 新股没有名称/行业时补拉一次基础信息
    if new["name"].isna().any():
        basic = pro.stock_basic(fields="ts_code,name,industry")
        new = new.drop(columns=["name", "industry"], errors="ignore").merge(
            basic, on="ts_code", how="left")
    new = new[[c for c in SNAPSHOT_COLS if c in new.columns]]
    new.to_parquet(DATA / "snapshot.parquet", index=False, compression="zstd")
    return new


def append_panel(pro, date: str) -> None:
    """把当天样本并入估值面板（每月只做一次）。"""
    panel = pd.read_parquet(DATA / "valuation_panel.parquet")
    if (panel["trade_date"].astype(str).str[:6] == date[:6]).any():
        print(f"  面板已有 {date[:6]} 的样本，跳过")
        return
    db = pro.daily_basic(trade_date=date, fields="ts_code,pb,pe_ttm,dv_ttm")
    if db is None or db.empty:
        print("  当天没有估值数据，跳过面板")
        return
    db = db.assign(trade_date=int(date))
    panel = pd.concat([panel, db], ignore_index=True)
    cutoff = int((pd.Timestamp(date) - pd.DateOffset(years=11)).strftime("%Y%m%d"))
    panel = panel[panel["trade_date"].astype(int) >= cutoff]
    panel.to_parquet(DATA / "valuation_panel.parquet", index=False, compression="zstd")
    print(f"  面板 +1 期，共 {panel['trade_date'].nunique()} 个月")


def refresh_financials(pro) -> None:
    fin = pd.read_parquet(DATA / "financials.parquet")
    last = str(fin["end_date"].max())
    periods = [f"{y}1231" for y in range(int(last[:4]), pd.Timestamp.now().year + 1)]
    periods += [f"{y}{m}" for y in range(int(last[:4]), pd.Timestamp.now().year + 1)
                for m in ("0331", "0630", "0930")]
    rows = []
    for p in sorted(set(periods)):
        try:
            d = pro.fina_indicator(period=p,
                                   fields="ts_code,end_date,ann_date,profit_dedt,eps,"
                                          "grossprofit_margin,netprofit_margin,"
                                          "debt_to_assets,ocfps")
        except Exception:
            continue
        if d is not None and not d.empty:
            rows.append(d)
    if not rows:
        print("  没有新的财务数据")
        return
    add = pd.concat(rows, ignore_index=True)
    merged = pd.concat([fin, add], ignore_index=True)
    merged = merged.sort_values("ann_date").drop_duplicates(
        ["ts_code", "end_date"], keep="last")
    merged.to_parquet(DATA / "financials.parquet", index=False, compression="zstd")
    print(f"  财务数据 {len(fin):,} → {len(merged):,} 行")


def refresh_company(pro) -> None:
    frames = []
    for ex in ("SSE", "SZSE", "BSE"):
        try:
            d = pro.stock_company(exchange=ex, fields="ts_code,main_business")
        except Exception:
            continue
        if d is not None and not d.empty:
            frames.append(d)
    if not frames:
        print("  没有主营业务数据")
        return
    df = pd.concat(frames, ignore_index=True).drop_duplicates("ts_code")
    from cyclical.company import classify
    df["chain"] = df["main_business"].map(classify)
    df.to_parquet(DATA / "company.parquet", index=False, compression="zstd")
    print(f"  主营业务 {len(df):,} 家")


def build_html(date: str) -> None:
    from cyclical.core import load_data, scan, sort_rows
    from cyclical.render import render_html

    rows = sort_rows(scan(load_data()), "pb_asc")
    DOCS.mkdir(exist_ok=True)
    html = render_html(rows, date)
    (DOCS / "index.html").write_text(html, encoding="utf-8")
    print(f"  面板已生成 {len(rows)} 只")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", required=True)
    ap.add_argument("--date", help="YYYYMMDD，默认取最近交易日")
    ap.add_argument("--full", action="store_true", help="同时刷新财务/主营业务/面板")
    ap.add_argument("--no-html", action="store_true")
    args = ap.parse_args()

    pro = _pro(args.token)
    date = args.date or _latest_trade_date(pro)
    print(f"交易日 {date}")

    print("[1/4] 快照")
    refresh_snapshot(pro, date)

    if args.full:
        print("[2/4] 财务与主营业务")
        refresh_financials(pro)
        refresh_company(pro)
        print("[3/4] 估值面板")
        append_panel(pro, date)
    else:
        print("[2/4] 跳过财务刷新（非 --full）")

    if not args.no_html:
        print("[4/4] 面板")
        build_html(date)
    return 0


if __name__ == "__main__":
    sys.exit(main())
