"""确定性归一化引擎：数值 / 单位 / 时间口径对齐。

用途：把「字符串比较」升级成「数值语义比对」——
"30%" 与 "0.3"、"3万辆" 与 "30000辆"、"2024Q1" 与 "2024年一季度"
会被识别为同一个值，避免矛盾检测误报；只有真正数值不同才判矛盾。

这是「确定性门禁」的核心算法层：让防幻觉从「拼写是否一致」升级到「语义是否一致」。
"""

import re
from dataclasses import dataclass
from typing import Optional, Tuple

# 中文数字（用于「三成」「八成」等）
_CN_DIGIT = {
    "零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
}

# 大数单位（万 / 亿）换算到基准
_BIG_UNIT = {"万": 1e4, "亿": 1e8}

# 电力度量单位换算到瓦特（W）
_ENERGY_UNIT = {
    "gw": 1e9, "gwh": 1e9, "mw": 1e6, "mwh": 1e6,
    "kw": 1e3, "kwh": 1e3, "w": 1.0, "wh": 1.0,
}

# 数值前缀匹配（单位前的大数前缀）
_NUM_PREFIX = re.compile(r"^([0-9]+(?:\.[0-9]+)?)\s*(亿|万)?(.*)$")


@dataclass
class NormalizedValue:
    value: float          # 归一到基准单位的数值
    unit: str             # 归一后的单位（"" 表示无量纲）
    is_ratio: bool        # 是否为比例（百分比/成数/分数）

    def key(self) -> Tuple[float, str]:
        """用于可比对的归一化键：数值（容差外）+ 单位。"""
        return (round(self.value, 4), self.unit)


@dataclass
class NormalizedPeriod:
    year: int
    start_month: int
    end_month: int

    def key(self) -> Tuple[int, int, int]:
        return (self.year, self.start_month, self.end_month)


# ----------------------------------------------------------------------
# 数值归一化
# ----------------------------------------------------------------------

def normalize_value(s) -> Optional[NormalizedValue]:
    """把任意数值字符串归一化成标准数值 + 单位。

    支持：百分比、小数、分数、中文成数、万/亿、电力/重量单位前缀。
    返回 None 表示无法归一化（非数值）。
    """
    if s is None:
        return None
    text = str(s).strip().replace(",", "").replace("，", "").replace(" ", "")
    if not text:
        return None
    low = text.lower()

    # 1. 百分比："30%" / "30.5%"
    m = re.match(r"^([0-9]+(?:\.[0-9]+)?)%$", text)
    if m:
        return NormalizedValue(float(m.group(1)) / 100.0, "", True)

    # 2. 分数："1/4" / "2/3"
    m = re.match(r"^([0-9]+)/([0-9]+)$", text)
    if m:
        denom = float(m.group(2))
        return NormalizedValue(float(m.group(1)) / denom, "", True) if denom else None

    # 3. 中文成数："三成" / "八成"
    if text.endswith("成") and text[:-1] in _CN_DIGIT:
        return NormalizedValue(_CN_DIGIT[text[:-1]] / 10.0, "", True)

    # 4. 中文整数："三" / "十三" / "三万" / "三亿"
    cn = _parse_cn_int(text)
    if cn is not None:
        return NormalizedValue(float(cn), "", False)

    # 5. 数字 + 万/亿 + 单位："3万辆" / "30000辆" / "3亿元" / "5GW"
    m = _NUM_PREFIX.match(text)
    if m:
        num = float(m.group(1))
        big = m.group(2)
        unit = m.group(3) or ""
        scale = _BIG_UNIT.get(big, 1.0)
        value = num * scale
        # 单位归一：电力单位换算到 W，其余保留原始单位（去万/亿前缀）
        if unit.lower() in _ENERGY_UNIT:
            return NormalizedValue(value * _ENERGY_UNIT[unit.lower()], "w", False)
        # 重量/数量的「万X」前缀：单位取前缀后的部分
        return NormalizedValue(value, _strip_unit_prefix(unit), False)

    return None


def _parse_cn_int(text: str) -> Optional[int]:
    """解析简单中文整数：三 / 十三 / 二十 / 一百 / 三万 / 三亿。"""
    if not text:
        return None
    total = 0
    section = 0
    number = 0
    for ch in text:
        if ch in _CN_DIGIT:
            number = _CN_DIGIT[ch]
        elif ch == "十":
            section += (number or 1) * 10
            number = 0
        elif ch == "百":
            section += (number or 1) * 100
            number = 0
        elif ch == "千":
            section += (number or 1) * 1000
            number = 0
        elif ch == "万":
            total += (section + number) * 10000
            section = 0
            number = 0
        elif ch == "亿":
            total += (section + number) * 100000000
            section = 0
            number = 0
        else:
            return None  # 含无法识别的字符
    total += section + number
    return total if total > 0 else None


def _strip_unit_prefix(unit: str) -> str:
    """把「万辆/万吨/亿元」里的万/亿前缀剥离，保留基准单位。"""
    if unit in ("辆", "吨", "元", "台", "家", "人", "户", "千瓦", "度", "台套"):
        return unit
    # 万X / 亿X → X
    m = re.match(r"^(?:万|亿)(.+)$", unit)
    return m.group(1) if m else unit


# ----------------------------------------------------------------------
# 时间口径归一化
# ----------------------------------------------------------------------

_QUARTER_MAP = {
    "一季度": (1, 3), "二季度": (4, 6), "三季度": (7, 9), "四季度": (10, 12),
    "第一季度": (1, 3), "第二季度": (4, 6), "第三季度": (7, 9), "第四季度": (10, 12),
    "q1": (1, 3), "q2": (4, 6), "q3": (7, 9), "q4": (10, 12),
}


def normalize_period(s) -> Optional[NormalizedPeriod]:
    """把时间口径归一化成 (year, start_month, end_month)。

    支持：2024年 / 2024 / 24年 / 2024Q1 / 2024年一季度 / 2024年上半年 / 2024年1-3月。
    """
    if s is None:
        return None
    text = str(s).strip().replace(" ", "")
    if not text:
        return None

    # 提取年份
    m = re.search(r"((?:19|20)\d{2})年?", text)
    if not m:
        return None
    year = int(m.group(1))

    # 半年度
    if "上半年" in text or "h1" in text.lower() or "h2" in text.lower():
        if "上半年" in text or "h1" in text.lower():
            return NormalizedPeriod(year, 1, 6)
        return NormalizedPeriod(year, 7, 12)

    # 季度
    low = text.lower()
    for q in ("第一季度", "第二季度", "第三季度", "第四季度", "一季度", "二季度", "三季度", "四季度", "q1", "q2", "q3", "q4"):
        if q in low or q in text:
            sm, em = _QUARTER_MAP[q]
            return NormalizedPeriod(year, sm, em)

    # 月份范围："2024年1-3月"
    m = re.search(r"(\d{1,2})\s*[-~至]\s*(\d{1,2})月", text)
    if m:
        sm = int(m.group(1))
        em = int(m.group(2))
        if 1 <= sm <= 12 and 1 <= em <= 12:
            return NormalizedPeriod(year, sm, em)

    # 单月："2024年3月"
    m = re.search(r"(\d{1,2})月", text)
    if m:
        mo = int(m.group(1))
        if 1 <= mo <= 12:
            return NormalizedPeriod(year, mo, mo)

    # 全年
    return NormalizedPeriod(year, 1, 12)


# ----------------------------------------------------------------------
# 可比对判断
# ----------------------------------------------------------------------

def values_equal(v1, v2) -> bool:
    """判断两个数值归一化后是否「语义相等」（同值同单位）。

    用于矛盾检测：语义相等则不判矛盾，语义不同才判矛盾。
    """
    n1 = normalize_value(v1)
    n2 = normalize_value(v2)
    if n1 is None or n2 is None:
        # 无法归一化时，退回字符串比较
        return str(v1).strip() == str(v2).strip()
    return n1.key() == n2.key()


def periods_overlap(p1, p2) -> bool:
    """判断两个时间口径是否有重叠（用于时间维度的一致性判断）。"""
    n1 = normalize_period(p1)
    n2 = normalize_period(p2)
    if n1 is None or n2 is None:
        return False
    return not (n1.end_month < n2.start_month or n2.end_month < n1.start_month)
