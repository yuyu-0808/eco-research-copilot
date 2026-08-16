import json
from openai import OpenAI
from src.utils.config import Config
from src.utils.logger import AgentLogger
from src.utils.llm_utils import call_llm
from src.utils.evidence import EvidenceRecord, records_to_text
from src.utils.validator import validate
from src.utils.source_grade import load_source_skill_doc


class AuditorAgent:
    def __init__(self, logger: AgentLogger, ckpt=None):
        self.logger = logger
        self.ckpt = ckpt  # checkpoint 引用：分批提炼时在批边界响应暂停/终止信号
        self.client = OpenAI(api_key=Config.DEEPSEEK_API_KEY, base_url=Config.BASE_URL)
        self.model = Config.MODEL_NAME

    def verify_data(self, plan_data: dict, collect_result, existing_evidence=None) -> dict:
        """
        事实校验（代码级）：LLM 只负责把素材提炼并归属到必答问题，
        「过没过」由 validator 的代码校验决定。

        existing_evidence：上一轮已累积的提炼证据（跨轮只提炼新增、累积结果时传入）。
        """
        # 兼容：新版传 dict（含 evidence），旧版传纯文本
        if isinstance(collect_result, dict):
            raw_context = collect_result.get("raw_context", "")
            raw_evidence = collect_result.get("evidence", [])
        else:
            raw_context = collect_result or ""
            raw_evidence = []

        self.logger.log_event("事实稽核官", "START", "开始提炼证据并做代码校验")

        requirements = plan_data.get("research_requirements", [])
        topic = plan_data.get("topic", "")

        # 1. LLM 提炼：把本轮新增素材提炼成结构化事实，并归属到必答问题（分批提炼）
        extracted = self._extract_evidence(topic, requirements, raw_evidence)

        # 2. 合并：把信源元数据（tier/publisher）从采集结果回填到提炼证据
        new_evidence = self._merge_meta(extracted, raw_evidence)

        # 2.5 累积：已有提炼证据 + 本轮新增（按 URL/标题去重），供 validator 做全局校验
        evidence_list = self._merge_evidence(existing_evidence or [], new_evidence)

        # 3. 代码校验（由代码判定）
        result = validate(plan_data, evidence_list)
        is_pass = result["is_pass"]

        # 4. 组装下游可用的文本 + 反馈
        verified_context = records_to_text(evidence_list)
        feedback = ""
        if not is_pass:
            feedback = "；".join(result["reasons"]) or "证据不达标"

        if is_pass:
            self.logger.log_event("事实稽核官", "SUCCESS", f"代码校验通过，{len(evidence_list)} 条有效证据")
        else:
            self.logger.log_event(
                "事实稽核官", "ACTION",
                f"代码校验未通过（{len(result['reasons'])} 项不达标），打回补充检索"
            )

        return {
            "is_pass": is_pass,
            "feedback": feedback,
            "verified_context": verified_context,
            "evidence": evidence_list,
            "reasons": result["reasons"],
            "coverage": result["coverage"],
            "conflicts": result["conflicts"],
            "warnings": result.get("warnings", []),
            "checks": result.get("checks", {}),
        }

    def _extract_evidence(self, topic: str, requirements: list, raw_evidence: list) -> list:
        """让 LLM 把原始素材提炼成结构化事实，并归属到必答问题。

        分批提炼：把证据切成小批逐批调用 LLM，降低单次 prompt 的认知复杂度，
        避免推理模型思维链过长导致输出为空；每批之间响应暂停/终止请求。
        单批失败不中断整轮，由下游 validator 判不达标后触发下一轮检索。
        """
        if not raw_evidence:
            return []
        req_text = json.dumps(requirements, ensure_ascii=False)
        skill_doc = load_source_skill_doc()
        batch_size = Config.EVIDENCE_BATCH_SIZE

        def _batch_text(batch) -> str:
            lines = []
            for r in batch:
                title = getattr(r, "source_title", "") or ""
                url = getattr(r, "source_url", "") or ""
                excerpt = getattr(r, "excerpt", "") or getattr(r, "claim", "") or ""
                tier = getattr(r, "source_tier", "") or ""
                lines.append(f"【信源 · {tier}级】标题: {title}\n链接: {url}\n摘录: {excerpt}")
            return "\n\n".join(lines)

        all_extracted = []
        batches = [raw_evidence[i:i + batch_size] for i in range(0, len(raw_evidence), batch_size)]
        total = len(batches)
        for idx, batch in enumerate(batches, 1):
            # 每批之间响应暂停/终止请求（协作式，见 Checkpoint.check_pause）
            if self.ckpt is not None:
                self.ckpt.check_pause()

            prompt = f"""
        你是【事实稽核官】的提炼助手。请从下面的原始素材中提炼出高纯度事实，
        并把每条事实归属到对应的必答问题（question_id）。

        【信源评级规范（A-F 六级，必须遵守）】：
        {skill_doc or "A 官方 / B 权威媒体 / C 行业专业 / D 一般 / E 低质 / F 无法判断，E/F 丢弃"}

        课题：{topic}
        【必答问题清单（含 question_id）】：
        {req_text}

        【原始素材（每条含 标题/链接/摘录/信源等级）】：
        {_batch_text(batch)}

        提炼规则：
        1. E 级（低质/营销号）与 F 级（无法判断）素材直接丢弃，不提炼；A/B/C 级优先采信，D 级谨慎；
        2. 每条事实须来自真实素材，严禁编造，并保留原信源的标题与链接；
        3. 若素材是"搜索降级兜底"（不含实时数据），不要作为事实提炼；
        4. 尽量抽取精确数值，填入 value/unit/period（无则留空）。

        严格按 JSON 数组输出（不要代码块标记）：
        [
          {{"question_id": "q1", "claim": "事实主张", "value": "数值", "unit": "单位", "period": "时间", "source_title": "信源标题", "source_url": "链接"}}
        ]
        """
            try:
                parsed = call_llm(self.client, self.model, self.logger, "事实稽核官", prompt, need_json=True)
                if isinstance(parsed, dict):
                    parsed = parsed.get("evidence") or parsed.get("facts") or []
                if isinstance(parsed, list):
                    all_extracted.extend(parsed)
                self.logger.log_event("事实稽核官", "INFO", f"第 {idx}/{total} 批提炼完成，累计 {len(all_extracted)} 条")
            except Exception as e:
                self.logger.log_event("事实稽核官", "WARNING", f"第 {idx}/{total} 批提炼失败: {e}")
        return all_extracted

    def _merge_meta(self, extracted: list, raw_evidence: list) -> list:
        """把采集阶段的信源元数据（source_tier/publisher）回填到 LLM 提炼结果。

        优先按 URL 精确匹配，其次按标题前缀模糊匹配；匹配不到的保留提炼结果、
        按 URL 重新评级兜底。
        """
        from src.utils.source_grade import source_grade
        from src.utils.validator import infer_publisher

        raw_map = {}
        for r in (raw_evidence or []):
            if getattr(r, "source_url", ""):
                raw_map[r.source_url] = r
        raw_by_title = {}
        for r in (raw_evidence or []):
            t = getattr(r, "source_title", "")
            if t:
                raw_by_title[t[:20]] = r

        out = []
        for item in (extracted or []):
            url = item.get("source_url", "") or item.get("url", "")
            title = item.get("source_title", "") or item.get("title", "")
            tier = item.get("source_tier", "")
            publisher = item.get("publisher", "")

            # 回填元数据
            src = raw_map.get(url) or raw_by_title.get(title[:20])
            if src is not None:
                if not tier:
                    tier = src.source_tier
                if not publisher:
                    publisher = src.publisher
            if not tier:
                tier, _ = source_grade(url, title)
            if not publisher:
                publisher = infer_publisher(url)

            out.append(EvidenceRecord(
                claim=item.get("claim", "") or item.get("excerpt", ""),
                value=item.get("value"),
                unit=item.get("unit"),
                period=item.get("period"),
                source_title=title,
                source_url=url,
                source_tier=tier or "D",
                publisher=publisher,
                excerpt=item.get("excerpt", "") or item.get("claim", ""),
                section=item.get("section", ""),
                question_id=item.get("question_id", ""),
            ))

        # 若提炼完全失败，退回采集阶段的原始证据（claim=摘录，等级已标注）
        if not out and raw_evidence:
            out = [EvidenceRecord(
                claim=getattr(r, "excerpt", "") or getattr(r, "claim", ""),
                excerpt=getattr(r, "excerpt", ""),
                source_title=getattr(r, "source_title", ""),
                source_url=getattr(r, "source_url", ""),
                source_tier=getattr(r, "source_tier", "D"),
                publisher=getattr(r, "publisher", ""),
            ) for r in raw_evidence if getattr(r, "source_tier", "") not in ("E", "F")]
        return out

    @staticmethod
    def _merge_evidence(existing: list, new: list) -> list:
        """累积合并提炼证据：已有 + 本轮新增。

        同源聚合（方案 1a）：按 (question_id, source_url) 分组，每组只保留
        信源等级最高的 top-N 条（优先保留 value 不同的数据点），砍掉冗余拆分，
        从源头控制 evidence 总量，避免下游撰写 prompt 过长导致质量下降。
        """
        tier_rank = {"A": 6, "B": 5, "C": 4, "D": 3, "E": 2, "F": 1, "": 0}
        max_per_source = Config.EVIDENCE_PER_SOURCE_MAX

        groups = {}  # (qid, url) -> list[EvidenceRecord]
        for e in list(existing or []) + list(new or []):
            url = getattr(e, "source_url", "") or ""
            title = getattr(e, "source_title", "") or ""
            qid = getattr(e, "question_id", "") or ""
            if not url and not title:
                continue  # 无 URL 且无标题：无法定位，丢弃
            key = (qid, url) if url else (qid, "title:" + title)
            groups.setdefault(key, []).append(e)

        merged = []
        for items in groups.values():
            # 按信源等级降序，等级相同保持原顺序稳定
            items = sorted(items, key=lambda e: tier_rank.get(getattr(e, "source_tier", ""), 0), reverse=True)
            kept = []
            seen_values = set()
            for e in items:
                # value 可能是 int/float（LLM 提炼出纯数字），先 str 再 strip，避免 'int' 无 strip 报错
                v = str(getattr(e, "value", "") or "").strip()
                if v and v in seen_values:
                    continue  # 同组内同数值的冗余条目跳过
                if v:
                    seen_values.add(v)
                kept.append(e)
                if len(kept) >= max_per_source:
                    break
            merged.extend(kept)
        return merged

    def verify_logic(self, topic: str, markdown_report: str, references: list, safe_context: str) -> dict:
        """逻辑校验：论据溯源 + 逻辑矛盾排查，用于撰写-稽核交叉校验循环。"""
        ref_text = "\n".join(f"[{r.get('index')}] {r.get('title')}" for r in (references or [])) or "（无）"
        self.logger.log_event("逻辑稽核", "START", "开始逻辑校验（论据溯源 + 逻辑矛盾排查）")

        prompt = f"""
        你是一位【事实稽核官】，负责对研究报告正文做「逻辑校验」。

        课题：{topic}
        【参考文献清单（正文用 [n] 引用）】：
        {ref_text}

        【待校验正文】：
        {markdown_report}

        【校验规则】：
        1. 论据溯源：正文中的关键数据、结论是否用 [n] 标注了引用编号？引用编号是否都在参考文献清单中存在？若正文出现精确数据却无任何引用来源，视为「疑似编造」，需打回。
        2. 逻辑矛盾：正文前后是否存在数据不一致、结论互相矛盾、因果跳跃等逻辑问题？
        3. 宽容原则：只对「硬伤」打回（无来源的精确数据、明显的逻辑矛盾）。一般性表述、修辞、章节详略不均等非硬伤，应放行。

        请严格按 JSON 输出（is_pass 必须是布尔值）：
        {{
            "is_pass": true,
            "feedback": "仅当 is_pass=false 时填写：指出具体哪一处无溯源或逻辑矛盾，指导撰写师如何修改"
        }}
        """

        try:
            result = call_llm(self.client, self.model, self.logger, "逻辑稽核", prompt, need_json=True)
            is_pass = result.get("is_pass", False)
            if is_pass:
                self.logger.log_event("逻辑稽核", "SUCCESS", "逻辑校验通过，论据溯源完整、无逻辑矛盾。")
            else:
                self.logger.log_event("逻辑稽核", "ACTION", f"逻辑校验发现争议，打回修正。意见: {result.get('feedback')}")
            return result

        except Exception as e:
            self.logger.log_event("逻辑稽核", "FAILED", f"逻辑校验发生异常: {e}")
            raise e
