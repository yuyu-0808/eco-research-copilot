"""结构化证据模型。

与「一段纯文本带个来源」不同，这里把每一条证据落成强类型数据：
claim / value / unit / period / source_tier / publisher / published_at /
excerpt / section / question_id。

用途：
- 信源研究员采集时，先给每条信源打上 source_tier + publisher（原始素材）；
- 事实稽核官提炼时，补全 claim / value / unit / period，并归属到 section/question_id；
- 确定性校验器（validator）据此做「框架合规性 + 证据匹配度」双重校验；
- 前端溯源面板据此实现「点正文任意一句 → 弹出原文摘录与信源」。
"""

from dataclasses import dataclass, asdict, fields
from typing import Optional

TIER_LABEL = {"A": "一手官方", "B": "权威媒体", "C": "行业专业", "D": "一般来源", "E": "低质来源", "F": "无法判断"}

_TIER_RANK = {"A": 6, "B": 5, "C": 4, "D": 3, "E": 2, "F": 1, "": 0}


@dataclass
class EvidenceRecord:
    claim: str = ""                 # 事实主张（一句话）
    value: Optional[str] = None     # 数值
    unit: Optional[str] = None      # 单位
    period: Optional[str] = None    # 时间口径
    source_title: str = ""          # 信源标题
    source_url: str = ""            # 信源链接
    source_tier: str = "D"          # 信源等级 A-F（A 官方/B 权威/C 行业/D 一般/E 低质/F 无法判断）
    publisher: str = ""             # 发布机构（由域名推断）
    published_at: str = ""          # 发布时间（尽力而为）
    excerpt: str = ""               # 原文摘录
    section: str = ""               # 归属章节
    question_id: str = ""           # 对应必答问题

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "EvidenceRecord":
        valid = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in (d or {}).items() if k in valid})

    def grade_label(self) -> str:
        return TIER_LABEL.get(self.source_tier, "未知信源")

    @property
    def tier_rank(self) -> int:
        return _TIER_RANK.get(self.source_tier, 0)

    def to_text(self) -> str:
        """转成下游可读的一行文本（供 writer 引用）。"""
        seg = [f"【{self.source_tier}级{self.grade_label()}】", self.claim]
        if self.value:
            seg.append(f"（{self.value}{self.unit or ''}" + (f"，{self.period}" if self.period else "") + "）")
        if self.source_title or self.source_url:
            seg.append(f" | 来源：{self.source_title} {self.source_url}".rstrip())
        return "".join(seg)


def records_to_text(records) -> str:
    """把证据列表拼成供下游 writer/renderer 使用的文本块。"""
    lines = []
    for i, r in enumerate(records, 1):
        lines.append(f"{i}. {r.to_text()}")
    return "\n".join(lines)
