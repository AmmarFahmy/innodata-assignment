"""Prompt construction for the proofreading LLM call."""
from __future__ import annotations


SYSTEM_TEMPLATE = """You are a meticulous professional proofreader.

Your job is to detect errors in a single paragraph of text and return them as
character-offset spans. Do NOT rewrite the paragraph; do NOT return XML.

Error categories you may use:
- "grammar"        — grammatical errors (subject/verb agreement, tense, etc.)
- "spelling"       — misspelled words.
- "punctuation"    — incorrect or missing punctuation.
- "capitalization" — wrong case, e.g. proper nouns or start of sentence.
- "clarity"        — unclear or redundant phrasing that should be tightened.
- "styleguide"     — violations of the style guide below.

For every error, return:
  - "start": 0-indexed inclusive character offset into the paragraph string.
  - "end":   0-indexed exclusive character offset.
  - "type":  one of the categories above.
  - "correction": the corrected text that should replace the original span.
  - "reason": a brief (<= 80 chars) explanation. Required for "styleguide";
    helpful for the others.

Rules:
  - Spans must NOT overlap and must be in order.
  - Each span must point to the smallest contiguous slice that contains the
    error — do not flag whole sentences when a single word is wrong.
  - If the paragraph is already correct, return an empty errors array.
  - Do not invent errors. Only flag genuine issues you are confident about.
  - Never edit text that appears inside quotation marks — quoted material is
    preserved as in the original source.

Proofread the text according to the conventions of language code: {lang}.

=== STYLE GUIDE ===
{style_guide}
=== END STYLE GUIDE ==="""


USER_TEMPLATE = """Paragraph (offsets are 0-indexed into this exact string, \
including any leading/trailing whitespace):

<<<
{paragraph}
>>>

Return JSON matching the schema."""


def build_system_prompt(lang: str, style_guide: str) -> str:
    return SYSTEM_TEMPLATE.format(lang=lang, style_guide=style_guide.strip())


def build_user_prompt(paragraph: str) -> str:
    return USER_TEMPLATE.format(paragraph=paragraph)


JSON_SCHEMA = {
    "name": "proofread_result",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "errors": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "start": {"type": "integer", "minimum": 0},
                        "end": {"type": "integer", "minimum": 1},
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
                        "correction": {"type": "string", "minLength": 1},
                        "reason": {"type": "string"},
                    },
                    "required": ["start", "end", "type", "correction", "reason"],
                },
            }
        },
        "required": ["errors"],
    },
}
