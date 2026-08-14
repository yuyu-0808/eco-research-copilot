"""统一的 LLM 调用工具：重试、空值判断、JSON 提取与修复、速率限制。

供各 Agent 复用，避免重复实现，根治 JSON 解析类问题（空返回、未闭合字符串等）。
"""
import json
import re
import time

from src.utils.config import Config

_last_api_call_time = 0.0


def fix_json(broken_json: str):
    """尝试修复不完整的 JSON：补右括号、补未闭合的引号"""
    if not broken_json:
        return None
    try:
        open_braces = broken_json.count('{')
        close_braces = broken_json.count('}')
        if open_braces > close_braces:
            broken_json += '}' * (open_braces - close_braces)

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

        open_braces = broken_json.count('{')
        close_braces = broken_json.count('}')
        if open_braces > close_braces:
            broken_json += '}' * (open_braces - close_braces)
        return broken_json
    except Exception:
        return None


def parse_json_response(raw_content: str):
    """从模型输出中提取并解析 JSON（容忍代码块、前后杂讯、不完整 JSON）"""
    if not raw_content or not raw_content.strip():
        raise ValueError("模型返回空内容")
    cleaned = raw_content.strip()
    match = re.search(r'\{.*\}', cleaned, re.DOTALL)
    if match:
        cleaned = match.group(0)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        fixed = fix_json(cleaned)
        if fixed:
            try:
                return json.loads(fixed)
            except json.JSONDecodeError:
                pass
        raise


def call_llm(client, model, logger, agent_name, prompt, need_json=True, max_retries=3, temperature=0.5):
    """统一调用大模型：重试 + 指数退避 + 速率限制 + 空值判断 + JSON 解析"""
    global _last_api_call_time
    last_err = None
    for attempt in range(max_retries):
        try:
            logger.log_event(agent_name, "ACTION", f"第 {attempt+1} 次请求大模型...")

            if attempt > 0:
                wait = 2 ** attempt
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
                temperature=temperature
            )
            raw = response.choices[0].message.content

            if need_json:
                return parse_json_response(raw)
            if not raw or not raw.strip():
                raise ValueError("模型返回空内容")
            return raw.strip()

        except Exception as e:
            last_err = e
            logger.log_event(agent_name, "WARNING", f"调用异常，准备重试: {e}")

    raise ValueError(f"大模型多次调用失败，重试耗尽: {last_err}")
