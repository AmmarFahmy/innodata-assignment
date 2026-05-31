# XML Proofread

A CLI that uses a GenAI model (OpenAI) to proofread the `<p>` elements of an
XML file. Each detected issue is wrapped in an
`<error type="..." correction="..." reason="...">original</error>` tag while
the original character count and whitespace of each paragraph are preserved
exactly.

Categories detected: **grammar, spelling, punctuation, capitalization,
clarity**, plus **styleguide** violations (dates, numbers, hyphenation,
currency, preferred word usage — see [`proofread/style_guide.md`](proofread/style_guide.md)).

---

## Quick start (with [uv](https://docs.astral.sh/uv/))

```bash
# 1. Install dependencies (uv reads pyproject.toml)
uv sync

# 2. Configure your OpenAI key
cp .env.example .env
# then edit .env and set OPENAI_API_KEY

# 3. Run the proofreader
uv run proofread example_input.xml --lang en
# -> writes example_input.corrected.xml next to the input
```

That's it. No paths to fiddle with — model, style guide, and concurrency are
all configured via `.env`.

### Try the larger sample

```bash
uv run proofread sample_input.xml --lang en
```

### Run the unit test

```bash
uv run --group dev pytest -q
```

---

## CLI

```
proofread <input.xml> --lang <bcp47>
```

- `<input.xml>` — path to the XML file to proofread.
- `--lang` — BCP-47 language tag (e.g. `en`, `fr`, `de`). Determines the
  proofing conventions sent to the model.

Output is written to `<stem>.corrected.xml` in the same directory as the
input.

## Configuration (`.env`)

| Variable | Default | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | *(required)* | OpenAI API key. |
| `OPENAI_MODEL` | `gpt-4.1-mini` | Model used for proofreading. |
| `STYLE_GUIDE_PATH` | `proofread/style_guide.md` | Style guide injected into the system prompt. |
| `MAX_CONCURRENCY` | `8` | Max simultaneous LLM requests across paragraphs. |

---

## How it works

1. **Parse XML** with `lxml`, preserving namespaces, attributes, comments,
   and CDATA.
2. **Iterate `<p>` elements** in document order (any namespace). Empty or
   whitespace-only paragraphs are skipped.
3. **One LLM call per paragraph**, run concurrently with an `asyncio`
   semaphore (`MAX_CONCURRENCY`). The model is asked for **character-offset
   spans**, not XML, via OpenAI's structured-output JSON schema.
4. **Validate & apply spans deterministically** in `apply_errors.py`. The
   `<error>` tags are spliced in by Python around `original[start:end]`, so
   the text content is preserved by construction. A defensive check confirms
   `strip_error_tags(output) == original` for every paragraph.
5. **Write** `<stem>.corrected.xml`.

Performance metrics (per-paragraph latency, total runtime, token usage, peak
memory) are logged to **stderr**.

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

## Limitations (deliberate, for the 2-day scope)

- **Text-only `<p>` elements.** Paragraphs that already contain child
  elements are passed through unchanged and a warning is logged. The
  provided samples are entirely text-only `<p>`s.
- **One retry on invalid spans.** If the model returns overlapping or
  out-of-range spans twice in a row, the paragraph is left unchanged and a
  warning is logged.
- **`--lang` is plumbed but tested only with `en`** on the provided samples.
- **No batching of paragraphs into a single LLM call.** One paragraph per
  call keeps prompts small, the length invariant trivial, and failures
  isolated. Concurrency makes up for it.

## Notes on the length invariant

The hardest correctness requirement is that, for every `<p>`, stripping
`<error>` tags from the output must yield the original text exactly —
same characters, same whitespace, same length. We guarantee this by:

1. **Never asking the model for text.** It returns spans `(start, end)`
   into the original paragraph string.
2. **Splicing tags in deterministic Python code** in `apply_errors.apply`.
3. **Asserting** `strip_error_tags(fragment) == original` before injecting
   the fragment back into the tree.
