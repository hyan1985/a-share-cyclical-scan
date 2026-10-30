"""公司主营业务与产业链分类。

为什么用这个而不是让大模型"搜资料分类"：
主营业务是招股书/年报里的原文，可核对、可追溯；模型给的分类没有出处，
而且 1000 多家公司逐个判断，准确率和一致性都没法保证。

分类只看原文里的关键词，规则是白盒的，错了能改规则，也能一眼看出为什么错。
"""
from __future__ import annotations

import re
from typing import Optional

import pandas as pd

# 资源开采（最上游）
RESOURCE = ("矿", "采矿", "开采", "勘探", "选矿", "原油", "采掘", "油气",
            "煤炭", "林业", "种植", "养殖", "捕捞")
# 冶炼/精炼（中上游）
SMELTING = ("冶炼", "电解", "氧化铝", "精炼", "炼化", "焦化", "轧制", "铸造",
            "烧结", "焙烧")
# 加工制造（下游）
PROCESSING = ("加工", "制品", "型材", "板带", "板材", "带材", "箔", "管材",
              "棒材", "制造", "组装", "零部件", "配件", "器件", "组件",
              "设备", "机械", "芯片", "半导体", "材料", "制品")
# 运营/服务（不影响商品价格的环节）
SERVICE = ("运输", "航运", "物流", "仓储", "港口", "装卸", "运营", "发电",
           "供电", "物业", "租赁", "开发", "工程建设", "施工")

_TAG_UP, _TAG_DOWN, _TAG_BOTH = "上游资源", "下游制造", "一体化"
_TAG_MID, _TAG_SERV, _TAG_OTHER = "中游冶炼", "运营服务", "其他"


def classify(main_business: Optional[str]) -> str:
    """按主营业务原文判断产业链位置。

    判定顺序很重要：先看有没有资源开采，再看冶炼，然后是加工制造，
    最后才是运营服务。否则「铝产品的生产、加工、销售」这种通用表述
    会把冶炼企业误判成加工厂（神火股份就是这么被分错的）。
    """
    if not isinstance(main_business, str) or not main_business.strip():
        return "未知"
    text = main_business.replace(" ", "")
    res = any(k in text for k in RESOURCE)
    smelt = any(k in text for k in SMELTING)
    proc = any(k in text for k in PROCESSING)
    serv = any(k in text for k in SERVICE)

    if res and (smelt or proc):
        return _TAG_BOTH
    if res:
        return _TAG_UP
    if smelt and proc:
        return _TAG_BOTH
    if smelt:
        return _TAG_MID
    if serv and not proc:
        return _TAG_SERV
    if proc:
        return _TAG_DOWN
    return _TAG_OTHER


def looks_stale(main_business: Optional[str], industry: Optional[str]) -> bool:
    """主营业务描述和所属行业对不上——多半是借壳/重组后数据没更新。

    例：天山铝业（行业=铝）的主营业务写着"泵及控制设备、风机"，
    那是它借壳前那家公司的描述。
    """
    if not isinstance(main_business, str) or not isinstance(industry, str):
        return False
    ind = industry.replace(" ", "")
    # 去掉"品、料、业、制"这类几乎每家都会出现的泛字，只留有辨识度的字
    meaningful = {ch for ch in ind if ch not in "品料业制其他"}
    if not meaningful:
        return False
    return not any(ch in main_business for ch in meaningful)


def load_or_fetch(store, client=None) -> pd.DataFrame:
    """读缓存的 company 表；没有就拉一次并缓存。"""
    cached = store.read_single("company")
    if cached is not None and not cached.empty and "main_business" in cached.columns:
        return cached

    if client is None:
        from .client import TushareClient
        client = TushareClient()

    frames = []
    for ex in ("SSE", "SZSE", "BSE"):
        try:
            d = client.query("stock_company", exchange=ex)
        except Exception:
            continue
        if d is not None and not d.empty:
            frames.append(d)
    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)
    keep = [c for c in ("ts_code", "com_name", "main_business", "business_scope",
                        "province", "employees") if c in df.columns]
    df = df[keep].drop_duplicates("ts_code")
    df["chain"] = df.get("main_business", pd.Series(dtype=str)).map(classify)
    try:
        store.write_single("company", df)
    except Exception:
        pass
    return df


def chain_map(store, client=None) -> dict:
    """ts_code -> 产业链标签。"""
    df = load_or_fetch(store, client)
    if df is None or df.empty:
        return {}
    return dict(zip(df["ts_code"], df["chain"]))
