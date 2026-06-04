from __future__ import annotations

import json
import logging
from typing import AsyncIterator

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import settings
from app.core.chunker import count_tokens

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_RAG = """\
你是一个精准的阅读助手，需要根据参考资料回答用户的问题。

## 回答步骤（请按顺序思考）：

1. **分析问题**：用户想知道什么？是事实查询、情节回忆、还是比较分析？
2. **筛选资料**：逐条检查参考资料，找出与问题直接相关的部分。标注相关度等级（高度相关 / 部分相关 / 无关）
3. **交叉验证**：如果多条资料涉及同一问题，对比它们是否一致。如有冲突，以更详细或更可信的来源为准，并指出存在不同说法
4. **组织回答**：基于相关参考资料给出答案，确保每个关键陈述都有来源依据

## 回答要求：

- **来源引用**：每个事实陈述后标注来源编号，例如：「叶默是主角[来源1][来源2]」
- **准确性**：只回答参考资料中明确提到的内容。如果资料只有部分信息，如实说明「参考资料中只提到……」
- **不确定性**：如果答案不完全确定，使用「可能」「参考资料显示」等措辞，不要编造
- **冲突处理**：如果参考资料之间不一致，说明「来源X说……而来源Y说……」，并给出综合判断
- **简洁性**：先给出直接答案，再补充细节。避免长篇摘抄原文

参考资料：
{contexts}"""

SYSTEM_PROMPT_GENERAL = """\
你是一个智能AI助手。请直接回答用户的问题。

要求：
1. 回答清晰、准确、简洁
2. 如果问题超出你的知识范围，如实说明
3. 不确定时使用"可能""据我所知"等措辞"""


class Generator:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ):
        self.api_key = api_key or settings.deepseek_api_key
        self.model = model or settings.deepseek_chat_model
        self.base_url = (base_url or settings.deepseek_base_url).rstrip("/")
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(300.0, connect=30.0),
            )
        return self._client

    MAX_CONTEXT_TOKENS = 6000

    @staticmethod
    def build_rag_prompt(question: str, contexts: list[str]) -> tuple[str, str]:
        if contexts:
            # Build source blocks with priority ordering (already sorted by score)
            blocks = []
            total_est = 0
            overflow = False
            for i, c in enumerate(contexts):
                est = count_tokens(c)
                if total_est + est > Generator.MAX_CONTEXT_TOKENS and blocks:
                    overflow = True
                    break
                blocks.append(f"[来源 {i+1}]\n{c}")
                total_est += est

            formatted = "\n\n---\n\n".join(blocks)
            if overflow:
                formatted += f"\n\n（注：共检索到 {len(contexts)} 条参考资料，以上展示了最相关的 {len(blocks)} 条）"

            system = SYSTEM_PROMPT_RAG.format(contexts=formatted)
        else:
            system = SYSTEM_PROMPT_GENERAL
        return system, question

    async def generate(
        self,
        question: str,
        contexts: list[str],
        history: list[dict] | None = None,
    ) -> AsyncIterator[str]:
        system_prompt, user_prompt = self.build_rag_prompt(question, contexts)
        messages = [{"role": "system", "content": system_prompt}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_prompt})

        @retry(
            retry=retry_if_exception_type((httpx.NetworkError, httpx.TimeoutException, httpx.HTTPStatusError)),
            stop=stop_after_attempt(settings.api_retry_times),
            wait=wait_exponential(multiplier=settings.api_retry_backoff, min=1, max=10),
            reraise=True,
        )
        async def _start_stream():
            client = await self._get_client()
            resp = await client.send(
                client.build_request(
                    "POST",
                    "/v1/chat/completions",
                    json={
                        "model": self.model,
                        "messages": messages,
                        "stream": True,
                    },
                ),
                stream=True,
            )
            resp.raise_for_status()
            return resp

        try:
            resp = await _start_stream()
        except Exception:
            logger.exception("Chat API request failed after retries")
            yield "[错误: API 请求失败，请稍后重试]"
            return

        try:
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        delta = chunk["choices"][0]["delta"]
                        content = delta.get("content", "")
                        if content:
                            yield content
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
        except Exception:
            logger.exception("Stream interrupted")
            yield "\n[错误: 连接中断]"

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
