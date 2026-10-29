"""按主营业务原文判断产业链位置。"""
from __future__ import annotations

from typing import Optional

RESOURCE = ("矿", "采矿", "开采", "勘探", "选矿", "原油", "采掘", "油气",
            "煤炭", "林业", "种植")
SMELTING = ("冶炼", "电解", "氧化铝", "精炼", "炼化", "焦化", "轧制", "铸造")
PROCESSING = ("加工", "制品", "型材", "板带", "板材", "带材", "箔", "管材",
              "棒材", "制造", "组装", "零部件", "配件", "回收", "再生")

TAG_UP, TAG_DOWN, TAG_BOTH = "上游资源", "下游加工", "一体化"
TAG_MID = "中游冶炼"


def classify(main_business: Optional[str]) -> str:
    """判定顺序很重要：先看资源开采，再看冶炼，最后才看加工。

    否则「铝产品的生产、加工、销售」这种通用表述会把冶炼企业误判成加工厂。
    """
    if not isinstance(main_business, str) or not main_business.strip():
        return "未知"
    text = main_business.replace(" ", "")
    res = any(k in text for k in RESOURCE)
    smelt = any(k in text for k in SMELTING)
    proc = any(k in text for k in PROCESSING)
    if res and (smelt or proc):
        return TAG_BOTH
    if res:
        return TAG_UP
    if smelt and proc:
        return TAG_BOTH
    if smelt:
        return TAG_MID
    if proc:
        return TAG_DOWN
    return "未知"


def looks_stale(main_business: Optional[str], industry: Optional[str]) -> bool:
    """主营业务描述和行业对不上——多半是借壳/重组后数据没更新。"""
    if not isinstance(main_business, str) or not isinstance(industry, str):
        return False
    meaningful = {ch for ch in industry.replace(" ", "") if ch not in "品料业制其他"}
    if not meaningful:
        return False
    return not any(ch in main_business for ch in meaningful)
