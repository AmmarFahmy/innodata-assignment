"""Orchestrates the full proofreading run."""
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


async def _process_one(
    llm: ProofreaderLLM,
    sem: asyncio.Semaphore,
    index: int,
    p_element,
    text: str,
) -> tuple[int, int, int, float]:
    """Returns (index, prompt_tokens, completion_tokens, elapsed_seconds)."""
    async with sem:
        t0 = time.perf_counter()
        result = await llm.proofread(text)
        elapsed = time.perf_counter() - t0
        if result.spans:
            try:
                fragment = apply(text, result.spans)
                replace_inner_with_fragment(p_element, fragment)
                log.info(
                    "p[%d]: %d error(s) injected (%.2fs)",
                    index, len(result.spans), elapsed,
                )
            except Exception as exc:
                log.warning("p[%d]: failed to apply spans (%s); leaving unchanged", index, exc)
        else:
            log.info("p[%d]: no errors (%.2fs)", index, elapsed)
        return index, result.prompt_tokens, result.completion_tokens, elapsed


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
    sem = asyncio.Semaphore(config.max_concurrency)

    t_start = time.perf_counter()
    tasks = [
        _process_one(llm, sem, i, p, text)
        for i, (p, text) in enumerate(paragraphs)
    ]
    results = await asyncio.gather(*tasks)
    total_elapsed = time.perf_counter() - t_start

    save(tree, output_path)

    prompt_tok = sum(r[1] for r in results)
    completion_tok = sum(r[2] for r in results)
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    log.info("=" * 60)
    log.info("Done in %.2fs (concurrency=%d)", total_elapsed, config.max_concurrency)
    log.info("Paragraphs proofread: %d", len(paragraphs))
    log.info("Tokens — prompt: %d, completion: %d, total: %d",
             prompt_tok, completion_tok, prompt_tok + completion_tok)
    log.info("Peak Python-allocated memory: %.1f MB", peak_bytes / 1_048_576)
    log.info("Output: %s", output_path)
    return output_path
