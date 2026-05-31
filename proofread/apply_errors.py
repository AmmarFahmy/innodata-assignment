"""Apply a list of error spans to a paragraph's plain text, producing an
XML fragment with `<error>` tags injected. The length invariant — that
stripping all `<error>` tags from the fragment yields the original text
unchanged — is guaranteed by construction.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable
from xml.sax.saxutils import escape, quoteattr


@dataclass(frozen=True)
class ErrorSpan:
    start: int
    end: int
    type: str
    correction: str
    reason: str = ""


_ALLOWED_TYPES = {
    "grammar",
    "spelling",
    "punctuation",
    "capitalization",
    "clarity",
    "styleguide",
}


class SpanValidationError(ValueError):
    pass


def validate_spans(original: str, spans: Iterable[ErrorSpan]) -> list[ErrorSpan]:
    """Sort spans, validate ranges, non-emptiness, and non-overlap."""
    cleaned = sorted(spans, key=lambda s: (s.start, s.end))
    n = len(original)
    last_end = 0
    out: list[ErrorSpan] = []
    for s in cleaned:
        if s.type not in _ALLOWED_TYPES:
            raise SpanValidationError(f"Unknown error type: {s.type!r}")
        if not (0 <= s.start < s.end <= n):
            raise SpanValidationError(
                f"Span out of range or empty: start={s.start}, end={s.end}, len={n}"
            )
        if s.start < last_end:
            raise SpanValidationError(
                f"Overlapping spans at offset {s.start} (previous ended at {last_end})"
            )
        if not s.correction:
            raise SpanValidationError("`correction` is required and must be non-empty.")
        last_end = s.end
        out.append(s)
    return out


def apply(original: str, spans: Iterable[ErrorSpan]) -> str:
    """Return an XML inner fragment for the `<p>` with `<error>` tags injected
    around each span. The text content (stripped of `<error>` tags) equals
    `original` exactly — same characters, same whitespace, same length.
    """
    sorted_spans = validate_spans(original, spans)
    parts: list[str] = []
    cursor = 0
    for s in sorted_spans:
        if s.start > cursor:
            parts.append(escape(original[cursor:s.start]))
        attrs = f'type="{s.type}" correction={quoteattr(s.correction)}'
        if s.reason:
            attrs += f" reason={quoteattr(s.reason)}"
        parts.append(f"<error {attrs}>{escape(original[s.start:s.end])}</error>")
        cursor = s.end
    if cursor < len(original):
        parts.append(escape(original[cursor:]))
    fragment = "".join(parts)

    # Defensive: confirm the length invariant is held.
    if strip_error_tags(fragment) != original:
        raise SpanValidationError(
            "Length invariant violated after span application (internal bug)."
        )
    return fragment


_ERROR_TAG_RE = re.compile(r"<error\b[^>]*>|</error>")
_ENTITY_RE = re.compile(r"&(amp|lt|gt|quot|apos);")
_ENTITY_MAP = {"amp": "&", "lt": "<", "gt": ">", "quot": '"', "apos": "'"}


def strip_error_tags(fragment: str) -> str:
    """Remove `<error ...>` and `</error>` tags from a fragment and unescape
    XML entities, returning the equivalent plain text.
    """
    without_tags = _ERROR_TAG_RE.sub("", fragment)
    return _ENTITY_RE.sub(lambda m: _ENTITY_MAP[m.group(1)], without_tags)
