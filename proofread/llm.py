"""OpenAI client wrapper. Returns validated `ErrorSpan` lists."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from openai import AsyncOpenAI

from .apply_errors import ErrorSpan, SpanValidationError, validate_spans
from .prompts import JSON_SCHEMA, build_system_prompt, build_user_prompt

log = logging.getLogger(__name__)


@dataclass
class LLMResult:
    spans: list[ErrorSpan]
    prompt_tokens: int
    completion_tokens: int


class ProofreaderLLM:
    def __init__(self, api_key: str, model: str, style_guide: str, lang: str):
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model
        self._system = build_system_prompt(lang, style_guide)

    async def proofread(self, paragraph: str) -> LLMResult:
        """Call the model and return validated spans. Retries once if the
        first response yields invalid spans (e.g. overlap or out-of-range).
        """
        last_err: str | None = None
        prompt_tokens = 0
        completion_tokens = 0

        for attempt in (1, 2):
            user = build_user_prompt(paragraph)
            if last_err:
                user += (
                    f"\n\nYour previous response was rejected: {last_err}\n"
                    "Please return corrected spans."
                )
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": self._system},
                    {"role": "user", "content": user},
                ],
                response_format={"type": "json_schema", "json_schema": JSON_SCHEMA},
                temperature=0,
            )
            if response.usage:
                prompt_tokens += response.usage.prompt_tokens or 0
                completion_tokens += response.usage.completion_tokens or 0
            content = response.choices[0].message.content or "{}"
            try:
                data = json.loads(content)
                raw = data.get("errors", []) or []
                spans = [
                    ErrorSpan(
                        start=int(e["start"]),
                        end=int(e["end"]),
                        type=str(e["type"]),
                        correction=str(e["correction"]),
                        reason=str(e.get("reason", "")),
                    )
                    for e in raw
                ]
                validated = validate_spans(paragraph, spans)
                return LLMResult(
                    spans=validated,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                )
            except (SpanValidationError, ValueError, KeyError, TypeError) as exc:
                last_err = str(exc)
                log.warning("Span validation failed on attempt %d: %s", attempt, exc)

        log.warning("LLM produced invalid spans twice; leaving paragraph unchanged.")
        return LLMResult(
            spans=[],
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
