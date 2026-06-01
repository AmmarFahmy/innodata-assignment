# XML Proofread

A CLI that uses a GenAI model (OpenAI) to proofread the `<p>` elements of an
XML file. Each detected issue is wrapped in an
`<error type="..." correction="..." reason="...">original</error>` tag while
the original character count and whitespace of each paragraph are preserved
exactly.

Categories detected: **grammar, spelling, punctuation, capitalization,
clarity**, plus **styleguide** violations (dates, numbers, hyphenation,
currency, preferred word usage).

---

## Quick start (with [uv](https://docs.astral.sh/uv/))

```bash
# 1. Install dependencies
uv sync

# 2. Configure OpenAI key
cp .env.example .env
# then set OPENAI_API_KEY

# 3. Run the proofreader
uv run proofread example_input.xml --lang en
# -> writes example_input.corrected.xml next to the input
```

### Run the unit test

```bash
uv run --group dev pytest -q
```

---

## CLI

```
proofread <input.xml> --lang <en>
```

- `<input.xml>` — path to the XML file to proofread.
- `--lang` — language tag (e.g. `en`, `fr`, `de`). Determines the
  proofing conventions sent to the model.

Output is written to `<input file name>.corrected.xml` in the same directory as the
input.

## Configuration (`.env`)

| Variable | Default | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | *(required)* | OpenAI API key. |
| `OPENAI_MODEL` | `gpt-4o-mini` | Model used for proofreading. |
| `STYLE_GUIDE_PATH` | `proofread/style_guide.md` | Style guide injected into the system prompt. |

---

## How it works

1. **Parse XML** with `lxml`, preserving namespaces, attributes, comments,
   and CDATA.
2. **Iterate `<p>` elements** in document order (any namespace). Empty or
   whitespace-only paragraphs are skipped.
3. **One batched LLM call for the whole document.** All paragraphs are sent
   in a single request, keyed by integer index, and the model returns one
   result entry per paragraph. This is faster than per-paragraph calls
   and avoids tail-latency amplification (one slow request would
   dominate wall-clock time). The model returns each error by **quoting
   the exact offending substring** (plus an `occurrence` index for
   disambiguation), never offsets, never XML, via OpenAI's structured-
   output JSON schema. LLMs are reliable at quoting text and unreliable at
   counting characters; we play to that strength. A retry kicks in if the
   model skips any paragraph index.
4. **Locate & apply spans deterministically** in `apply_errors.py`. We
   `str.find` each quoted `original` in the paragraph to compute offsets,
   drop any overlaps, then splice `<error>` tags in by Python, so the text
   content is preserved by construction. A defensive check confirms
   `strip_error_tags(output) == original` for every paragraph.
5. **Write** `<output>.corrected.xml`.

### Performance metrics (per-paragraph latency, total runtime, token usage, peak memory) are logged.

### Project layout

```
proofread/
├── __main__.py       # CLI entrypoint
├── config.py         # .env loader
├── xml_io.py         # parse/serialize + paragraph iteration
├── prompts.py        # system/user prompt builders + JSON schema
├── llm.py            # OpenAI async client with one validated retry
├── apply_errors.py   # span -> XML fragment, guarantees length invariant
├── runner.py         # orchestrates everything
└── style_guide.md    # style rules injected into the system prompt
tests/
└── test_apply_errors.py
```

---

## Limitations

- **Text-only `<p>` elements.** Paragraphs that already contain child
  elements are passed through unchanged and a warning is logged. The
  provided samples are entirely text-only `<p>`s.
- **One retry on invalid spans.** If the model returns overlapping or
  out-of-range spans twice in a row, the paragraph is left unchanged and a
  warning is logged.
- **`--lang` is plumbed but tested only with `en`** on the provided samples.
- **All paragraphs share one LLM call.** This keeps wall clock time low
  and matches the "process with minimum time" requirement. The trade-off
  is that a malformed batch response taints the whole run (mitigated by a
  one-shot retry with explicit feedback).

## Notes on the length invariant

The hardest correctness requirement is that, for every `<p>`, stripping
`<error>` tags from the output must yield the original text exactly -
same characters, same whitespace, same length. I guarantee this by:

1. **Never asking the model for text.** It returns spans `(start, end)`
   into the original paragraph string.
2. **Splicing tags in deterministic Python code** in `apply_errors.apply`.
3. **Asserting** `strip_error_tags(fragment) == original` before injecting
   the fragment back into the tree.
