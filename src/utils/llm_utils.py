"""统一的 LLM 调用工具：重试、空值判断、JSON 提取与修复、速率限制。

供各 Agent 复用，避免重复实现，根治 JSON 解析类问题（空返回、未闭合字符串等）。
"""
import json
import time

from src.utils.config import Config
from src.utils import db

_last_api_call_time = 0.0


def _record_usage(logger, agent_name, response):
    """把每次 LLM 调用的 Token 消耗写入统计表（失败静默，不影响主流程）。"""
    usage = getattr(response, "usage", None)
    if not usage:
        return
    try:
        db.stats_record_tokens(
            getattr(logger, "project_name", ""),
            agent_name,
            getattr(usage, "prompt_tokens", 0) or 0,
            getattr(usage, "completion_tokens", 0) or 0,
            getattr(usage, "total_tokens", 0) or 0,
        )
    except Exception:
        pass


def fix_json(broken_json: str):
    """尝试修复不完整的 JSON：补右括号/方括号、补未闭合的引号"""
    if not broken_json:
        return None
    try:
        in_string = False
        escape_next = False
        for char in broken_json:
            if escape_next:
                escape_next = False
                continue
            if char == '\\':
                escape_next = True
                continue
            if char == '"':
                in_string = not in_string
        if in_string:
            broken_json += '"'

        for open_ch, close_ch in (('{', '}'), ('[', ']')):
            n_open = broken_json.count(open_ch)
            n_close = broken_json.count(close_ch)
            if n_open > n_close:
                broken_json += close_ch * (n_open - n_close)
        return broken_json
    except Exception:
        return None


def parse_json_response(raw_content: str):
    """从模型输出中提取并解析 JSON（容忍代码块、前后杂讯、不完整 JSON，支持对象与数组）"""
    if not raw_content or not raw_content.strip():
        raise ValueError("模型返回空内容")
    cleaned = raw_content.strip()

    # 定位最外层 JSON：第一个 { 或 [（谁更靠前谁就是最外层结构）
    brace = cleaned.find("{")
    bracket = cleaned.find("[")
    if bracket != -1 and (brace == -1 or bracket < brace):
        open_ch, close_ch = "[", "]"
        start = bracket
    elif brace != -1:
        open_ch, close_ch = "{", "}"
        start = brace
    else:
        raise ValueError("模型输出中未找到 JSON")

    # 括号平衡匹配，跳过字符串内的同名括号，截取完整的最外层结构
    depth = 0
    in_str = False
    escape = False
    end = -1
    for i in range(start, len(cleaned)):
        c = cleaned[i]
        if in_str:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                end = i
                break

    candidate = cleaned[start:end + 1] if end != -1 else cleaned[start:]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        fixed = fix_json(candidate)
        if fixed:
            try:
                return json.loads(fixed)
            except json.JSONDecodeError:
                pass
        raise


def call_llm(client, model, logger, agent_name, prompt, need_json=True, max_retries=3, temperature=0.2, max_tokens=None):
    """统一调用大模型：重试 + 指数退避 + 速率限制 + 截断检测 + 空值判断 + JSON 解析 + 备用模型降级"""
    global _last_api_call_time
    last_err = None
    if max_tokens is None:
        max_tokens = getattr(Config, 'MAX_TOKENS', 16384)
    for attempt in range(max_retries):
        try:
            logger.log_event(agent_name, "ACTION", f"第 {attempt+1} 次请求大模型...")

            if attempt > 0:
                wait = 2 ** attempt
                max_wait = getattr(Config, 'MAX_RETRY_WAIT_SECONDS', 30) or 30
                wait = min(wait, max_wait)
                logger.log_event(agent_name, "INFO", f"限流保护：等待{wait}秒后重试...")
                time.sleep(wait)

            # 速率限制
            elapsed = time.time() - _last_api_call_time
            rate_limit = getattr(Config, 'API_RATE_LIMIT_SECONDS', 5)
            if elapsed < rate_limit:
                time.sleep(rate_limit - elapsed)
            _last_api_call_time = time.time()

            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens
            )
            _record_usage(logger, agent_name, response)
            raw = response.choices[0].message.content
            finish = getattr(response.choices[0], "finish_reason", "")

            # 输出被截断（撞到 max_tokens 上限）：内容不完整，不可采用，抛异常触发重试
            if finish == "length":
                raise ValueError(f"输出被截断（finish_reason=length，max_tokens={max_tokens}）")

            if need_json:
                return parse_json_response(raw)
            if not raw or not raw.strip():
                raise ValueError("模型返回空内容")
            return raw.strip()

        except Exception as e:
            last_err = e
            logger.log_event(agent_name, "WARNING", f"调用异常，准备重试: {e}")

    # 主模型重试耗尽 → 尝试备用模型（容错降级）
    backup = getattr(Config, 'BACKUP_MODEL', '') or ''
    if backup and backup != model:
        logger.log_event(agent_name, "WARNING", f"主模型 {model} 重试耗尽，切换备用模型 {backup} 再试")
        try:
            elapsed = time.time() - _last_api_call_time
            rate_limit = getattr(Config, 'API_RATE_LIMIT_SECONDS', 5)
            if elapsed < rate_limit:
                time.sleep(rate_limit - elapsed)
            _last_api_call_time = time.time()

            response = client.chat.completions.create(
                model=backup,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens
            )
            _record_usage(logger, agent_name, response)
            raw = response.choices[0].message.content
            finish = getattr(response.choices[0], "finish_reason", "")

            if finish == "length":
                raise ValueError(f"输出被截断（finish_reason=length，max_tokens={max_tokens}）")

            if need_json:
                return parse_json_response(raw)
            if not raw or not raw.strip():
                raise ValueError("模型返回空内容")
            return raw.strip()

        except Exception as e:
            last_err = e
            logger.log_event(agent_name, "WARNING", f"备用模型调用也失败: {e}")

    raise ValueError(f"大模型多次调用失败，重试耗尽: {last_err}")
