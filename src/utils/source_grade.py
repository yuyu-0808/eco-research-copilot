"""信源分级：根据域名 + 标题启发式，判定信源等级 S/A/B/D。

- S 官方：政府 / 国际组织 / 官方统计，最高可信，优先采信
- A 权威：权威媒体 / 行业头部媒体，采信
- B 一般：其他正常网站，谨慎对待
- D 低质：营销号 / 内容农场 / 震惊体，直接丢弃

供「信源研究员」采集时评级、「事实稽核官」分级采信使用。
"""

# S 级：官方 / 权威机构
_SOURCE_S = [
    "gov", "edu", "oecd", "un.org", "worldbank", "imf.org", "who.int",
    ".ac.cn", "stats", "mofcom", "ndrc", "nea.gov", "miit", "court.gov",
]

# A 级：权威媒体
_SOURCE_A = [
    "xinhua", "people.com", "caixin", "reuters", "bloomberg", "ft.com",
    "wsj.com", "eastmoney", "36kr", "ifeng", "sina.com", "163.com",
    "chinanews", "ce.cn", "yicai", "cls.cn", "thepaper",
]

# D 级：低质 / 内容农场域名（保守，只放明确低质）
_SOURCE_D = [
    "360doc", "wenzhang", "jingyan.baidu", "zhidao.baidu",
]

# D 级：营销号标题特征词（震惊体）
_D_TITLE_WORDS = [
    "震惊", "速看", "不看后悔", "竟然", "万万没想到", "揭秘", "真相",
    "深度好文", "转疯了", "删前速看", "出大事了", "紧急通知",
]


def source_grade(url: str = "", title: str = "") -> tuple:
    """返回 (等级, 标签)。等级为 S/A/B/D。"""
    u = (url or "").lower()
    t = (title or "").lower()

    # D 级：低质域名 或 营销号标题
    if any(k in u for k in _SOURCE_D) or any(w in t for w in _D_TITLE_WORDS):
        return "D", "低质信源"
    if any(k in u for k in _SOURCE_S):
        return "S", "官方信源"
    if any(k in u for k in _SOURCE_A):
        return "A", "权威信源"
    return "B", "一般信源"
