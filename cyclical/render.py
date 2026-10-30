"""周期行业扫描的 HTML 面板。"""
from __future__ import annotations

import html
from typing import List

from .core import CycRow

TAG_CLASS = {
    "周期顶（PB贵+盈利高）": "t-top",
    "周期底（PB便宜+盈利低）": "t-bottom",
    "PB 便宜": "t-cheap",
    "PB 偏贵": "t-rich",
    "中性": "t-mid",
    "历史不可比": "t-na",
    "数据不足": "t-na",
}

CSS = """
:root{--bg:#0f1115;--card:#161922;--line:#242938;--text:#e6e8ee;--muted:#8b93a7;
--accent:#e8a33d;--green:#4ea36b;--red:#d9534f;--blue:#5b8dd9}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);
font:14px/1.6 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif}
header{padding:16px 28px;border-bottom:1px solid var(--line);display:flex;
justify-content:space-between;align-items:center;position:sticky;top:0;
background:rgba(15,17,21,.97);backdrop-filter:blur(8px);z-index:6}
h1{font-size:16px;margin:0;font-weight:600}
.meta{color:var(--muted);font-size:12px}
.wrap{padding:18px 28px 60px;max-width:1560px}
.bar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:14px}
select,input{background:var(--card);color:var(--text);border:1px solid var(--line);
border-radius:8px;padding:7px 12px;font-size:13px;outline:none;font-family:inherit}
select:focus,input:focus{border-color:var(--accent)}
input{width:190px}
input::placeholder{color:#5b6376}
.count{color:var(--muted);font-size:12.5px;margin-left:auto;
font-variant-numeric:tabular-nums}
.summary{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:16px}
.chip{padding:5px 12px;border-radius:999px;font-size:12.5px;cursor:pointer;
border:1px solid var(--line);background:var(--card);color:var(--muted);
user-select:none;transition:.15s}
.chip:hover{border-color:var(--accent);color:var(--text)}
.chip.on{background:var(--accent);color:#1a1205;border-color:var(--accent);font-weight:600}
.chip.on .tag{background:transparent;color:#1a1205}
.chip .n{opacity:.65;margin-left:5px;font-variant-numeric:tabular-nums}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:8px 10px;text-align:right;border-bottom:1px solid var(--line);
white-space:nowrap}
th:nth-child(-n+4),td:nth-child(-n+4){text-align:left}
.warn{color:#e8a33d;font-weight:700;margin-left:2px}
thead th{position:sticky;top:57px;background:var(--card);color:var(--muted);
font-weight:500;font-size:12px;cursor:pointer;user-select:none;z-index:4}
thead th:hover{color:var(--accent)}
tbody tr:hover{background:#1b1f2b}
td.name{font-weight:500}
td.mono{font-variant-numeric:tabular-nums}
.tag{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11.5px}
.t-top{background:rgba(217,83,79,.16);color:#e8706c}
.t-bottom{background:rgba(78,163,107,.16);color:#5fbf80}
.t-cheap{background:rgba(78,163,107,.10);color:#54a86e}
.t-rich{background:rgba(217,83,79,.10);color:#d4736f}
.t-mid{background:rgba(139,147,167,.14);color:#9aa2b4}
.t-na{background:rgba(139,147,167,.08);color:#6e7686}
.empty{padding:40px;text-align:center;color:var(--muted)}
.note{margin-top:22px;padding:16px 18px;background:var(--card);border-radius:10px;
border:1px solid var(--line);color:var(--muted);font-size:12.5px;line-height:1.9}
.note b{color:var(--text)}
"""

JS = """
const chips=[...document.querySelectorAll('.chip')];
const sel=document.getElementById('ind');
const box=document.getElementById('q');
const cnt=document.getElementById('cnt');
let active=new Set();

function apply(){
  let shown=0;
  document.querySelectorAll('tbody tr').forEach(r=>{
    const okTag=!active.size||active.has(r.dataset.tag);
    const okInd=!sel.value||r.dataset.ind===sel.value;
    const q=box.value.trim().toLowerCase();
    const okQ=!q||r.dataset.key.toLowerCase().includes(q);
    const ok=okTag&&okInd&&okQ;
    r.style.display=ok?'':'none';
    if(ok)shown++;
  });
  cnt.textContent='显示 '+shown+' / '+document.querySelectorAll('tbody tr').length+' 只';
  document.getElementById('none').style.display=shown?'none':'block';
}

chips.forEach(c=>c.onclick=()=>{
  const t=c.dataset.tag;
  if(t===''){active.clear();chips.forEach(x=>x.classList.toggle('on',x.dataset.tag===''));}
  else{
    chips[0].classList.remove('on');
    if(active.has(t))active.delete(t);else active.add(t);
    c.classList.toggle('on',active.has(t));
    if(!active.size)chips[0].classList.add('on');
  }
  apply();
});
sel.onchange=apply;
box.oninput=apply;

document.querySelectorAll('thead th').forEach((th,i)=>{
  let asc=true;
  th.onclick=()=>{
    const tb=th.closest('table').querySelector('tbody');
    const rows=[...tb.rows];
    const val=r=>{const t=r.cells[i].dataset.v;return t===''||t===undefined?-Infinity:parseFloat(t);};
    rows.sort((a,b)=>asc?val(a)-val(b):val(b)-val(a));
    asc=!asc;rows.forEach(r=>tb.appendChild(r));
  };
});
apply();
"""


def _fmt(v, nd=2):
    return f"{v:.{nd}f}" if isinstance(v, (int, float)) else "—"


def render_html(rows: List[CycRow], as_of: str) -> str:
    from collections import Counter

    cnt = Counter(r.tag for r in rows)
    chips = [f'<div class="chip on" data-tag="">全部<span class="n">{len(rows)}</span></div>']
    for tag, n in cnt.most_common():
        cls = TAG_CLASS.get(tag, "t-mid")
        chips.append(f'<div class="chip" data-tag="{html.escape(tag)}">'
                     f'<span class="{cls} tag">{html.escape(tag)}</span>'
                     f'<span class="n">{n}</span></div>')

    inds = sorted({r.industry for r in rows})
    opts = ['<option value="">全部行业</option>'] + [
        f'<option value="{html.escape(i)}">{html.escape(i)}（{sum(1 for r in rows if r.industry == i)}）</option>'
        for i in inds]

    body = []
    warn = '<span class="warn">!</span>'
    for r in rows:
        cls = TAG_CLASS.get(r.tag, "t-mid")
        chain_html = html.escape(r.chain or "—") + (warn if r.stale else "")
        body.append(
            f'<tr data-tag="{html.escape(r.tag)}" data-ind="{html.escape(r.industry)}" '
            f'data-key="{html.escape(r.code + r.name)}">'
            f'<td class="mono">{r.code}</td>'
            f'<td class="name">{html.escape(r.name)}</td>'
            f'<td>{html.escape(r.industry)}</td>'
            f'<td title="{html.escape(r.main_business or "")}">{chain_html}</td>'
            f'<td><span class="tag {cls}">{html.escape(r.tag)}</span></td>'
            f'<td class="mono" data-v="{r.pe if r.pe is not None else ""}">{_fmt(r.pe)}</td>'
            f'<td class="mono" data-v="{r.pe_pct if r.pe_pct is not None else ""}">{_fmt(r.pe_pct, 0)}</td>'
            f'<td class="mono" data-v="{r.pb if r.pb is not None else ""}">{_fmt(r.pb)}</td>'
            f'<td class="mono" data-v="{r.pb_pct if r.pb_pct is not None else ""}">{_fmt(r.pb_pct, 0)}</td>'
            f'<td class="mono" data-v="{r.earn_pos if r.earn_pos is not None else ""}">{_fmt(r.earn_pos)}</td>'
            f'<td class="mono" data-v="{r.norm_pe if r.norm_pe is not None else ""}">{_fmt(r.norm_pe)}</td>'
            f'<td class="mono" data-v="{r.dy if r.dy is not None else ""}">{_fmt(r.dy)}</td>'
            f'<td class="mono" data-v="{r.gross_margin if r.gross_margin is not None else ""}">{_fmt(r.gross_margin, 0)}</td>'
            f'<td class="mono" data-v="{r.net_margin_vol if r.net_margin_vol is not None else ""}">{_fmt(r.net_margin_vol, 1)}</td>'
            f'<td class="mono" data-v="{r.debt_ratio if r.debt_ratio is not None else ""}">{_fmt(r.debt_ratio, 0)}</td>'
            f'<td class="mono" data-v="{r.ocf_to_profit if r.ocf_to_profit is not None else ""}">{_fmt(r.ocf_to_profit)}</td>'
            f'<td class="mono" data-v="{r.nm_shift if r.nm_shift is not None else ""}">{_fmt(r.nm_shift, 1)}</td>'
            f'<td class="mono" data-v="{r.market_cap_yi if r.market_cap_yi is not None else ""}">{_fmt(r.market_cap_yi, 0)}</td>'
            f'</tr>')

    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>周期行业扫描 · {as_of}</title><style>{CSS}</style></head>
<body>
<header>
  <h1>周期行业扫描</h1>
  <div class="meta">{as_of} · 点表头可排序</div>
</header>
<div class="wrap">
  <div class="bar">
    <select id="ind">{''.join(opts)}</select>
    <input id="q" placeholder="搜代码或名称…">
    <span class="count" id="cnt"></span>
  </div>
  <div class="summary">{''.join(chips)}</div>
  <table>
    <thead><tr>
      <th>代码</th><th>名称</th><th>行业</th><th>链条</th><th>判断</th>
      <th>PE</th><th>PE分位</th><th>PB</th><th>PB分位</th>
      <th>盈利位置</th><th>正常化PE</th><th>股息率</th>
      <th>毛利率</th><th>盈利波动</th><th>负债率</th><th>现金流</th><th>利润率变化</th>
      <th>市值(亿)</th>
    </tr></thead>
    <tbody>{''.join(body)}</tbody>
  </table>
  <div class="empty" id="none" style="display:none">没有符合条件的股票</div>
  <div class="note">
    <b>怎么读这张表</b><br>
    · <b>PB 分位</b>是主指标——净资产不像盈利那样大起大落，能反映真实位置。<br>
    · <b>盈利位置</b> = 最新扣非净利润 ÷ 该公司自己的 10 年中位扣非净利润。
    用净利润而不是 EPS，因为 EPS 会被股本变动（增发、回购、转增）扭曲。
    &gt;1.5 说明盈利在自己历史上偏高，此时 PE 再低也不便宜。<br>
    · <b>正常化 PE</b> = 总市值 ÷ 10 年中位扣非净利润，回答"如果盈利回到常态，这价格是多少倍"。<br>
    · <b>「历史不可比」</b>：中位净利润为负或接近 0（重组、壳公司、连年亏损），
    任何纵向比较都不成立。比如宏桥控股重组前几乎不赚钱，算出"盈利位置 147 倍"就是假象。<br>
    <br>
    <b>链条</b>（上游资源 / 中游冶炼 / 下游加工 / 一体化）按主营业务原文关键词判定，
    把鼠标放在链条上能看到原文。<span class="warn">!</span> 表示描述与行业对不上，
    多半是借壳或重组后数据没更新（例如天山铝业的主营业务仍写着"泵及控制设备"）。<br>
    <br>
    <b>利润率变化</b> = 近 3 年净利率中位 − 全期中位（百分点）。
    大幅为正说明行业结构变了（比如电解铝 2017 年产能封顶后，5 家公司净利率中位抬升 2~16pp），
    此时「盈利位置」和「正常化 PE」会高估当前的周期顶部程度——因为拿 10 年中位（含低利润年份）当基准。<br>
    <br>
    <b>毛利率 / 盈利波动 / 负债率 / 现金流</b>：前两个用来分辨产业链位置——
    <b>高毛利率 + 高盈利波动 = 上游资源型</b>（利润跟着商品价格走）；
    <b>低毛利率 + 低波动 = 下游加工型</b>（赚加工费，商品贵的时候反而被挤压）。
    铝行业实测：加工型毛利 3~15%、波动 1~3；电解铝毛利 20~25%、波动 3~10。
    后两个是风险：负债率越高、现金流/净利润越低，周期下行时越危险。<br>
    <br>
    <b>重要提醒</b>：这里比较的是<b>每家公司股价相对它自己历史</b>的位置，
    不是"整个行业处在周期的哪一段"。同一行业里"一个在高位、一个在低位"往往是
    <b>产业链位置不同</b>——上游在商品涨价时先受益，下游的毛利同时被挤压，
    所以两者的估值分位天然反向。
  </div>
</div>
<script>{JS}</script>
</body></html>"""
