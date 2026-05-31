"""Unit tests for span application and the length invariant."""
from __future__ import annotations

import pytest

from proofread.apply_errors import (
    ErrorSpan,
    SpanValidationError,
    apply,
    strip_error_tags,
)


def _invariant(original: str, fragment: str) -> None:
    assert strip_error_tags(fragment) == original, (
        f"length-invariant violated:\n  original={original!r}\n  stripped="
        f"{strip_error_tags(fragment)!r}"
    )


def test_no_errors_returns_escaped_original():
    text = "All good here."
    assert apply(text, []) == "All good here."


def test_single_spelling_span():
    text = "The committe meets soon."
    span = ErrorSpan(start=4, end=12, type="spelling", correction="committee")
    out = apply(text, [span])
    assert out == 'The <error type="spelling" correction="committee">committe</error> meets soon.'
    _invariant(text, out)


def test_multiple_non_overlapping_spans_sorted_or_unsorted():
    text = "john works in new york."
    spans = [
        ErrorSpan(14, 22, "capitalization", "New York"),
        ErrorSpan(0, 4, "capitalization", "John"),
    ]
    out = apply(text, spans)
    assert out.startswith('<error type="capitalization" correction="John">john</error> works in ')
    assert out.endswith('<error type="capitalization" correction="New York">new york</error>.')
    _invariant(text, out)


def test_styleguide_includes_reason():
    text = "January, 2024 was the date."
    spans = [
        ErrorSpan(0, 13, "styleguide", "January 2024", "No comma between month and year"),
    ]
    out = apply(text, spans)
    assert 'type="styleguide"' in out
    assert 'reason="No comma between month and year"' in out
    _invariant(text, out)


def test_xml_special_chars_in_text_are_escaped():
    text = "a < b and c > d & e"
    out = apply(text, [])
    # Length invariant must hold even with escaping.
    _invariant(text, out)


def test_xml_special_chars_inside_correction_attribute():
    text = "he said hello"
    span = ErrorSpan(0, 13, "clarity", 'He said "hello"', "Quote direct speech")
    out = apply(text, [span])
    # quoteattr will use single quotes around the value containing ".
    assert "correction=" in out
    _invariant(text, out)


def test_whitespace_preserved():
    text = "  leading and  trailing   spaces  "
    out = apply(text, [])
    _invariant(text, out)


def test_overlapping_spans_rejected():
    text = "abcdefgh"
    spans = [
        ErrorSpan(0, 4, "spelling", "WXYZ"),
        ErrorSpan(2, 6, "spelling", "CDEF"),
    ]
    with pytest.raises(SpanValidationError):
        apply(text, spans)


def test_out_of_range_span_rejected():
    text = "short"
    spans = [ErrorSpan(0, 99, "spelling", "longer")]
    with pytest.raises(SpanValidationError):
        apply(text, spans)


def test_empty_span_rejected():
    text = "hello"
    spans = [ErrorSpan(2, 2, "spelling", "x")]
    with pytest.raises(SpanValidationError):
        apply(text, spans)


def test_unknown_type_rejected():
    text = "hello"
    spans = [ErrorSpan(0, 5, "vibes", "Hello")]  # type: ignore[arg-type]
    with pytest.raises(SpanValidationError):
        apply(text, spans)


def test_adjacent_spans_allowed():
    text = "abcdef"
    spans = [
        ErrorSpan(0, 3, "spelling", "ABC"),
        ErrorSpan(3, 6, "spelling", "DEF"),
    ]
    out = apply(text, spans)
    _invariant(text, out)


def test_full_string_span():
    text = "wholepara"
    spans = [ErrorSpan(0, len(text), "clarity", "Whole paragraph")]
    out = apply(text, spans)
    _invariant(text, out)
