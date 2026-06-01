"""Prompt construction for the proofreading LLM call.

We send all paragraphs in a single batched request, keyed by integer index,
to minimize wall-clock latency.
"""
from __future__ import annotations


SYSTEM_TEMPLATE = """You are a meticulous professional proofreader.

You will receive a numbered list of paragraphs. For each one, find errors and
report them by quoting the exact original substring that is wrong. Do NOT
rewrite the paragraphs; do NOT return XML; do NOT return character offsets.

Error categories you may use:
- "grammar"        — grammatical errors (subject/verb agreement, tense, etc.)
- "spelling"       — misspelled words.
- "punctuation"    — incorrect or missing punctuation.
- "capitalization" — wrong case (proper nouns, sentence starts, etc.).
- "clarity"        — unclear or redundant phrasing that should be tightened.
- "styleguide"     — violations of the style guide below.

For each error, return an object with:
  - "original":    the EXACT substring from the paragraph that is wrong.
                   Copy it character-for-character including capitalization
                   and any internal punctuation. Keep it as SHORT as possible
                   while still bounding the error (usually a single word or a
                   short phrase). Do NOT include surrounding correct words.
  - "occurrence":  1-based index of which occurrence of "original" to flag if
                   it appears more than once in the same paragraph. Use 1 if
                   it only appears once. (Required.)
  - "type":        one of the categories above.
  - "correction":  the corrected text that should replace "original".
  - "reason":      a brief (<= 80 chars) explanation. Required for
                   "styleguide"; helpful for the others.

Rules:
  - "original" MUST appear verbatim in the referenced paragraph. If you
    cannot quote it exactly, skip the error.
  - Errors within a paragraph must not overlap.
  - If a paragraph is already correct, return an empty "errors" array for it.
  - Do not invent errors. Only flag genuine issues you are confident about.
  - Never edit text inside quotation marks — quoted material is preserved as
    in the source.
  - Return exactly one result entry per input paragraph, in order, with the
    same integer "index" that was given to you.

Proofread according to the conventions of language code: {lang}.

=== STYLE GUIDE EXAMPLES (high-signal; flag these aggressively) ===
- "$2,000,000"    → styleguide, "$2 million"      reason: "Spell out million, billion, etc."
- "$3,000,000"    → styleguide, "$3 million"      reason: "Spell out million, billion, etc."
- "January, 2024" → styleguide, "January 2024"    reason: "No comma between month and year."
- "publicly-owned"→ styleguide, "publicly owned"  reason: "Do not hyphenate -ly adverbs."
- "wholly-owned"  → styleguide, "wholly owned"    reason: "Do not hyphenate -ly adverbs."
- "6:00 AM"       → styleguide, "6:00 a.m."       reason: "Use lowercase a.m./p.m. with space."
- "3:30PM"        → styleguide, "3:30 p.m."       reason: "Use lowercase a.m./p.m. with space."
- "1930's"        → styleguide, "1930s"           reason: "No apostrophe in decade plurals."
- "judgement"     → styleguide, "judgment"        reason: "Preferred spelling: judgment."
- "acknowledgement"→ styleguide, "acknowledgment" reason: "Preferred spelling: acknowledgment."
- "non profit"    → styleguide, "nonprofit"       reason: "non-* compounds are usually one word."
- "pre-existing"  → styleguide, "preexisting"     reason: "preexisting is one word."
- "third party"   (as adjective before a noun) → styleguide, "third-party"  reason: "Hyphenate compound adjectives."
- "it's"          (when possessive) → punctuation, "its" reason: "Possessive 'its' has no apostrophe."

=== STYLE GUIDE (full rules) ===
{style_guide}
=== END STYLE GUIDE ==="""


USER_TEMPLATE = """You will proofread {count} paragraph(s). Each is delimited
by a header line "[index N]" and the markers <<< and >>>. Do not include the
markers in any "original" value.

{paragraphs}

CRITICAL: Your "results" array MUST contain EXACTLY {count} entries — one for
every paragraph above, in order, with "index" set to 0, 1, ..., {last_index}.
If a paragraph has no errors, still include its entry with an empty "errors"
array. Do NOT skip any paragraph."""


def build_system_prompt(lang: str, style_guide: str) -> str:
    return SYSTEM_TEMPLATE.format(lang=lang, style_guide=style_guide.strip())


def build_user_prompt(paragraphs: list[str]) -> str:
    blocks = []
    for i, p in enumerate(paragraphs):
        blocks.append(f"[index {i}]\n<<<\n{p}\n>>>")
    return USER_TEMPLATE.format(
        count=len(paragraphs),
        last_index=len(paragraphs) - 1,
        paragraphs="\n\n".join(blocks),
    )


JSON_SCHEMA = {
    "name": "proofread_batch_result",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "index": {"type": "integer", "minimum": 0},
                        "errors": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "original": {"type": "string", "minLength": 1},
                                    "occurrence": {"type": "integer", "minimum": 1},
                                    "type": {
                                        "type": "string",
                                        "enum": [
                                            "grammar",
                                            "spelling",
                                            "punctuation",
                                            "capitalization",
                                            "clarity",
                                            "styleguide",
                                        ],
                                    },
                                    "correction": {
                                        "type": "string",
                                        "minLength": 1,
                                    },
                                    "reason": {"type": "string"},
                                },
                                "required": [
                                    "original",
                                    "occurrence",
                                    "type",
                                    "correction",
                                    "reason",
                                ],
                            },
                        },
                    },
                    "required": ["index", "errors"],
                },
            }
        },
        "required": ["results"],
    },
}
