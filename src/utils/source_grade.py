"""信源分级：根据域名 + 标题启发式，判定信源等级 A-F（行研专属六级）。

借鉴 NATO Admiralty Code「双维度」评估思想，本模块实现「来源可靠性」维度：
- A 一手官方：政府 / 国际组织 / 官方统计 / 公司公告，最高可信，优先采信
- B 权威媒体：有严格编辑审核的主流媒体，采信
- C 行业专业：行业协会 / 专业研究机构 / 垂直行业媒体，行研数据与格局的优质来源
- D 一般来源：其他正常网站，无明确背书，谨慎对待
- E 低质来源：营销号 / 内容农场 / 震惊体，直接丢弃
- F 无法判断：匿名 / 无法追溯发布者 / 无 URL，不采信

「信息可信度」维度由代码校验器（validator）承载：证据数 + 信源等级门槛
+ 数值归一化 + 矛盾检测 + 口径契约，不在此处重复实现。

供「信源研究员」采集时评级、「事实稽核官」分级采信使用。
"""

# A 级：一手官方 / 权威机构
_SOURCE_A = [
    "gov", "edu", "oecd", "un.org", "worldbank", "imf.org", "who.int",
    ".ac.cn", "stats", "mofcom", "ndrc", "nea.gov", "miit", "court.gov",
    # 各国非 gov 命名的政府域名（避免海外课题一手官方信源被误评）
    ".go.th", ".go.jp", ".go.kr", ".go.id", ".gob.mx", ".gouv.fr",
    ".gob.ar", ".gob.pe", ".gob.cl", ".gob.es", ".bund.de",
    # 国际组织 / 权威机构（投研常用）
    "europa.eu", "wto.org", "adb.org", "asean.org", "bis.org",
    "unesco.org", "ilo.org", "unctad.org", "fao.org", "iea.org",
]

# B 级：权威媒体（有严格编辑审核）
_SOURCE_B = [
    "xinhua", "people.com", "caixin", "reuters", "bloomberg", "ft.com",
    "wsj.com", "eastmoney", "36kr", "ifeng", "sina.com", "163.com",
    "chinanews", "ce.cn", "yicai", "cls.cn", "thepaper",
]

# C 级：行业专业（行业协会 / 专业研究机构 / 垂直行业媒体）
_SOURCE_C = [
    # 行业协会
    "caam", "cpcaauto", "csia", "ceia",
    # 专业研究机构 / 市场咨询
    "counterpoint", "canalys", "idc.com", "gartner", "trendforce", "semi.org",
    # 垂直行业媒体
    "ijiwei", "jwview", "laoyaoba", "eet-china", "ledinside",
]

# E 级：低质 / 内容农场域名（保守，只放明确低质）
_SOURCE_E = [
    "360doc", "wenzhang", "jingyan.baidu", "zhidao.baidu", "wenku.baidu",
    "sohu.com/a", "k.sina", "zhihu.com/question", "tianya", "19lou",
]

# E 级：营销号标题特征词（震惊体）
_E_TITLE_WORDS = [
    "震惊", "速看", "不看后悔", "竟然", "万万没想到", "揭秘", "真相",
    "深度好文", "转疯了", "删前速看", "出大事了", "紧急通知",
]


def source_grade(url: str = "", title: str = "") -> tuple:
    """返回 (等级, 标签)。等级为 A-F 六级。

    - 无 URL → F（无法判断）
    - 低质域名 / 营销号标题 → E（低质来源）
    - 官方域名 → A（一手官方）
    - 权威媒体域名 → B（权威媒体）
    - 行业专业域名 → C（行业专业）
    - 其他 → D（一般来源）
    """
    u = (url or "").lower()
    t = (title or "").lower()

    if not u:
        return "F", "无法判断"
    if any(k in u for k in _SOURCE_E) or any(w in t for w in _E_TITLE_WORDS):
        return "E", "低质来源"
    if any(k in u for k in _SOURCE_A):
        return "A", "一手官方"
    if any(k in u for k in _SOURCE_B):
        return "B", "权威媒体"
    if any(k in u for k in _SOURCE_C):
        return "C", "行业专业"
    return "D", "一般来源"


def load_source_skill_doc() -> str:
    """加载行研信源评级规范 skill 文档（skills/source_verification/SKILL.md），供 prompt 注入。"""
    import os
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    path = os.path.join(root, "skills", "source_verification", "SKILL.md")
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return f.read()
        except OSError:
            pass
    return ""
