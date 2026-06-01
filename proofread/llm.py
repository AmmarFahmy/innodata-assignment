"""OpenAI client wrapper. One batched call returns spans for all paragraphs."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from openai import AsyncOpenAI

from .apply_errors import (
    ErrorSpan,
    RawError,
    resolve_spans,
    validate_spans,
)
from .prompts import JSON_SCHEMA, build_system_prompt, build_user_prompt

log = logging.getLogger(__name__)


@dataclass
class BatchResult:
    spans_per_paragraph: list[list[ErrorSpan]]
    prompt_tokens: int
    completion_tokens: int


class ProofreaderLLM:
    def __init__(self, api_key: str, model: str, style_guide: str, lang: str):
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model
        self._system = build_system_prompt(lang, style_guide)

    async def proofread_batch(self, paragraphs: list[str]) -> BatchResult:
        """Send all paragraphs in one request. Returns one list of validated
        spans per paragraph, in the same order. Retries once if any returned
        `original` value cannot be located in its referenced paragraph.
        """
        prompt_tokens = 0
        completion_tokens = 0
        retry_note: str | None = None

        for attempt in (1, 2):
            user = build_user_prompt(paragraphs)
            if retry_note:
                user += f"\n\nNOTE: {retry_note}"

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
            by_index: dict[int, list[RawError]] = {}
            try:
                data = json.loads(content)
                results = data.get("results", []) or []
                for item in results:
                    idx = int(item.get("index", -1))
                    if not (0 <= idx < len(paragraphs)):
                        continue
                    by_index[idx] = [
                        RawError(
                            original=str(e["original"]),
                            occurrence=int(e.get("occurrence", 1) or 1),
                            type=str(e["type"]),
                            correction=str(e["correction"]),
                            reason=str(e.get("reason", "")),
                        )
                        for e in (item.get("errors") or [])
                    ]
            except (ValueError, KeyError, TypeError) as exc:
                log.warning("Could not parse batch response on attempt %d: %s",
                            attempt, exc)
                if attempt == 1:
                    retry_note = (
                        "Your previous response could not be parsed. Return a "
                        "JSON object with a 'results' array, one entry per "
                        "paragraph, each with 'index' and 'errors'."
                    )
                    continue

            # Incomplete coverage check: the model is supposed to return one
            # entry per paragraph. If some are missing, retry with feedback.
            missing_indices = [
                i for i in range(len(paragraphs)) if i not in by_index
            ]
            if missing_indices and attempt == 1:
                retry_note = (
                    f"Your previous 'results' array was incomplete. You MUST "
                    f"return EXACTLY {len(paragraphs)} entries (indices 0..{len(paragraphs)-1}). "
                    f"You skipped these paragraph indices: {missing_indices}. "
                    f"Include them with an empty errors array if they have no errors."
                )
                log.warning("Retrying batch: missing indices %s", missing_indices)
                continue

            # Collect any RawErrors whose `original` isn't found verbatim in
            # the referenced paragraph — these will be dropped, and on the
            # first attempt we retry with feedback.
            missing: list[tuple[int, str]] = []
            spans_per_paragraph: list[list[ErrorSpan]] = []
            for i, text in enumerate(paragraphs):
                raw = by_index.get(i, [])
                for r in raw:
                    if r.original and r.original not in text:
                        missing.append((i, r.original))
                spans = validate_spans(text, resolve_spans(text, raw))
                spans_per_paragraph.append(spans)

            if missing and attempt == 1:
                pairs = "; ".join(
                    f"paragraph {i}: {orig!r}" for i, orig in missing[:6]
                )
                retry_note = (
                    f"These 'original' values were not found verbatim in their "
                    f"referenced paragraphs and were dropped: {pairs}. "
                    f"Quote the exact substring from the correct paragraph."
                )
                log.warning("Retrying batch: %d unlocatable error(s)", len(missing))
                continue

            return BatchResult(
                spans_per_paragraph=spans_per_paragraph,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )

        # Both attempts failed to produce parseable / locatable results.
        log.warning("Batch failed twice; leaving all paragraphs unchanged.")
        return BatchResult(
            spans_per_paragraph=[[] for _ in paragraphs],
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
