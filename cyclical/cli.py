"""命令行入口：python -m cyclical [选项]"""
import argparse
import sys
from pathlib import Path

from .core import load_data, scan, sort_rows, summarize, format_table
from .render import render_html


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="cyclical", description="A股周期行业估值扫描（PB 分位 + 盈利位置）")
    p.add_argument("--industry", "-i", help="行业名，逗号分隔；省略=全部周期行业")
    p.add_argument("--min-cap", type=float, default=50, help="最小市值（亿），默认 50")
    p.add_argument("--top", "-n", type=int, default=30, help="显示前 N 只")
    p.add_argument("--sort", "-s", default="pb_asc",
                   choices=["pb_asc", "pb_desc", "earn", "pe_asc"],
                   help="pb_asc=最便宜在前 / pb_desc=最贵在前 / earn=盈利位置最高")
    p.add_argument("--html", help="输出 HTML 面板路径")
    p.add_argument("--csv", help="导出 CSV")
    args = p.parse_args(argv)

    data = load_data()
    inds = set(args.industry.split(",")) if args.industry else None
    all_rows = scan(data, industries=inds, min_cap_yi=args.min_cap, include_unsuitable=True)
    excluded = sorted({(r.industry, r.industry_noanswer) for r in all_rows if r.industry_unsuitable})
    rows = sort_rows([r for r in all_rows if not r.industry_unsuitable], args.sort)
    if not rows:
        print("没有符合条件的股票")
        return 1

    print(summarize(rows))
    print()
    print(format_table(rows, limit=args.top))
    print()
    print("说明：PB 分位是主指标；盈利位置 = 最新扣非净利润 / 10 年中位扣非净利润，"
          ">1.5 说明盈利在周期顶，此时 PE 再低也不便宜。")

    if args.html:
        out = Path(args.html)
        out.parent.mkdir(parents=True, exist_ok=True)
        as_of = str(data["panel"]["trade_date"].max())
        out.write_text(render_html(rows, as_of, excluded=excluded), encoding="utf-8")
        print(f"\n已生成面板 {out}")
    if args.csv:
        import pandas as pd
        pd.DataFrame([r.as_dict() for r in rows]).to_csv(args.csv, index=False)
        print(f"已导出 {args.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
