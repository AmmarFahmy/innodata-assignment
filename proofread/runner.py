"""Orchestrates the full proofreading run with a single batched LLM call."""
from __future__ import annotations

import asyncio
import logging
import time
import tracemalloc
from pathlib import Path

from .apply_errors import apply
from .config import Config
from .llm import ProofreaderLLM
from .xml_io import iter_text_paragraphs, load, replace_inner_with_fragment, save

log = logging.getLogger(__name__)


async def run(input_path: Path, lang: str, config: Config) -> Path:
    if not input_path.is_file():
        raise FileNotFoundError(input_path)
    output_path = input_path.with_name(input_path.stem + ".corrected.xml")

    tracemalloc.start()
    log.info("Loading %s", input_path)
    tree = load(input_path)
    paragraphs = list(iter_text_paragraphs(tree))
    log.info("Found %d proofable <p> element(s)", len(paragraphs))

    if not paragraphs:
        save(tree, output_path)
        log.info("Wrote %s (no paragraphs to proofread)", output_path)
        return output_path

    llm = ProofreaderLLM(
        api_key=config.api_key,
        model=config.model,
        style_guide=config.style_guide_text,
        lang=lang,
    )

    texts = [text for _, text in paragraphs]

    t_start = time.perf_counter()
    log.info("Sending batched proofread request (%d paragraph(s))...", len(texts))
    result = await llm.proofread_batch(texts)
    llm_elapsed = time.perf_counter() - t_start
    log.info("LLM round trip: %.2fs", llm_elapsed)

    for i, ((p_element, text), spans) in enumerate(
        zip(paragraphs, result.spans_per_paragraph)
    ):
        if not spans:
            log.info("p[%d]: no errors", i)
            continue
        try:
            fragment = apply(text, spans)
            replace_inner_with_fragment(p_element, fragment)
            log.info("p[%d]: %d error(s) injected", i, len(spans))
        except Exception as exc:
            log.warning("p[%d]: failed to apply spans (%s); leaving unchanged",
                        i, exc)

    save(tree, output_path)

    total_elapsed = time.perf_counter() - t_start
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    log.info("=" * 60)
    log.info("Done in %.2fs (1 batched LLM call for %d paragraph(s))",
             total_elapsed, len(paragraphs))
    log.info("Tokens — prompt: %d, completion: %d, total: %d",
             result.prompt_tokens, result.completion_tokens,
             result.prompt_tokens + result.completion_tokens)
    log.info("Peak Python-allocated memory: %.1f MB", peak_bytes / 1_048_576)
    log.info("Output: %s", output_path)
    return output_path
