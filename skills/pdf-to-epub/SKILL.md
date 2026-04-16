---
name: pdf-to-epub
description: >-
  Convert a PDF to EPUB via OCR. Primary engine is Mistral OCR (text +
  embedded images, full fidelity). Fallback is OpenRouter free vision
  OCR (text only). Also covers fresh EPUB translation to Traditional
  Chinese plus second/third editorial polish passes that preserve EPUB
  structure.
argument-hint: <input.pdf>
allowed-tools: Bash Read
---

# pdf-to-epub: PDF → EPUB via OCR

Convert a PDF into an EPUB using an OCR pipeline.

| Provider | Model | Coverage | Cost |
|----------|-------|----------|------|
| **mistral** (default) | `mistral-ocr-latest` | text + embedded images | paid, requires `MISTRAL_API_KEY` |
| **openrouter** (fallback) | `google/gemma-4-31b-it:free` | text only — **embedded images are dropped** | free tier, requires `OPENROUTER_API_KEY` |

For image-faithful EPUBs, use `mistral`. Use `openrouter` when you have no Mistral key or when the content is text-only (papers, articles, novels).

## Workflow

1. **Parse input**: take the PDF path from the argument. If none was provided, ask the user for it.
2. **Resolve API keys** — check, in order:
   - Shell environment variables: `MISTRAL_API_KEY`, `OPENROUTER_API_KEY`.
   - If both are missing, look for a `.env` file in the current working directory *and* in the PDF's parent directory. Parse plain `KEY=value` lines. **Never print the key values** to the conversation — just note which keys were found.
   - If no keys are found anywhere, ask the user to provide at least one.
3. **Ask the user** (use `AskUserQuestion` when available, otherwise a plain conversational prompt):
   - **Provider** — `mistral` or `openrouter`. If only one key is available, skip the question and use that provider. If both are available, default to `mistral`.
   - **TOC depth** — `H1 only` or `H1 + H2`.
   - **Cover image** — path to a local image file, or `none`.
4. **Run the script**. Pass the API key through the process environment (NOT as a CLI flag) to keep it out of `ps` output and shell history:

   ```bash
   MISTRAL_API_KEY="$KEY" uv run ~/.claude/skills/pdf-to-epub/scripts/pdf_to_epub.py \
     --pdf /absolute/path/to/input.pdf \
     --provider mistral \
     --toc-depth 1 \
     --cover /absolute/path/to/cover.jpg
   ```

   Replace `MISTRAL_API_KEY` with `OPENROUTER_API_KEY` when using the openrouter provider. Omit `--cover` when the user said `none`. Omit `--output` unless the user gave a custom path — the script defaults the output to `<pdf-stem>.epub` next to the input PDF.

5. **Report** the absolute path of the generated EPUB (printed to stdout by the script). On error, surface the script's stderr to the user and offer to retry with the other provider.

## Post-OCR Translation Workflow

Use this when the user wants the resulting EPUB translated, especially into Traditional Chinese.

### Fresh translation rules

1. If the user asks for a **fresh** translation, translate from the English-source EPUB again.
   Do **not** reuse or clone an older translated EPUB, even if one exists locally.
2. Treat translation as a separate EPUB-to-EPUB step after OCR/output generation.
3. Preserve EPUB structure exactly:
   - keep `id`, `href`, `src`, filenames, anchors, and XML structure unchanged
   - translate visible text only
   - update language metadata to `zh-Hant`
4. Translate `main.xhtml`, `nav.xhtml`, and `toc.ncx`.
   Update `content.opf` title/language metadata.
   Check `main.xhtml` and `cover.xhtml` `<title>` values; they are easy to leave behind as `Main` / `Cover`.

### Recommended translation strategy

Do not send the whole `main.xhtml` in one request. Split by heading-bounded sections and translate in source order.

- Use `<h1>` / `<h2>` boundaries as the default chunking strategy.
- Ignore leading blank lines before the first heading; otherwise you can create a fake empty section and misalign source vs translated sections.
- Translate smaller sections first to sample tone and terminology before launching the full run.
- For `zh-Hant`, explicitly instruct the model to use Taiwan-style astrology terms.

### Required validation after translation

After rebuilding the EPUB:

1. Run an archive integrity check (`ZipFile.testzip()` or equivalent).
2. Parse `main.xhtml`, `nav.xhtml`, `toc.ncx`, `content.opf`, and `cover.xhtml` as XML/XHTML.
3. Search for obvious leftover English in `main.xhtml` (`The `, chapter headings, `All Rights Reserved`, etc.).
4. Spot-check early, middle, and late chapters against the English source.
5. Check metadata titles inside XHTML files, not just the package title.

## Second And Third Editorial Passes

If the first translation is understandable but still stiff, do editorial passes against the English source.

### Second pass: line-level polish

Goal: smoother Traditional Chinese while preserving meaning and EPUB markup.

Workflow:

1. Compare each English section with the already-translated Chinese section.
2. Ask the model to **polish the Chinese**, not retranslate from scratch.
3. Keep the Chinese fragment's structure exactly: same tags, attributes, anchors, and filenames.
4. Run this pass section by section, the same way as the translation pass.

Use this pass to fix:

- literal or machine-like phrasing
- awkward romance/sexual wording
- repetitive constructions across neighboring paragraphs
- clunky TOC / nav wording

### Third pass: narrower tone pass

Goal: reduce stiffness and repetition without reopening broad translation drift.

Narrow the prompt to:

- Taiwanese nonfiction-book tone
- more natural editorial phrasing
- less repetition of verbs like `代表`, `顯示`, `揭示`, `象徵`
- no added explanation, hype, or promotional wording

This pass should be conservative. It is a prose refinement pass, not a content-rewrite pass.

## Structural Guards For Editorial Passes

When polishing XHTML/XML fragments, reject and retry outputs that alter structure.

Minimum checks:

- tag counts must match
- critical attributes must match in order:
  `id`, `href`, `src`, `alt`, `title`, `epub:type`, `role`, `aria-hidden`, `xmlns`, `lang`, `xml:lang`

If a fragment changes structure, retry that fragment instead of restarting the entire book.

## Lessons Learned

- Do not assume an existing translated EPUB is acceptable when the user explicitly asks for a fresh translation.
- Split by real document structure, not arbitrary byte size, when quality matters.
- Sample a few fragments before full-book runs; prompt flaws are cheaper to fix early.
- Front matter often triggers false “still English” heuristics because of names, filenames, and mixed-language metadata. Check visible text, not raw markup.
- Leading whitespace in XHTML bodies can create fake sections and break section alignment.
- Editorial passes need stricter structural checks than first-pass translation.
- After polishing, validate both archive integrity and XML parseability, then spot-check representative chapters.
- Targeted cleanup of recurring phrasing after the full run is faster than rerunning the whole book blindly.

## CLI reference (script flags)

| Flag | Default | Meaning |
|------|---------|---------|
| `--pdf` (required) | — | Input PDF path |
| `--provider` (required) | — | `mistral` or `openrouter` |
| `--toc-depth` | `1` | `1` (H1 only) or `2` (H1 + H2 nested) |
| `--cover` | — | Path to a cover image file |
| `--output` | `<pdf-stem>.epub` | Output EPUB path |
| `--title` | `<pdf-stem>` | Book title |
| `--author` | `Unknown` | Author name |
| `--dpi` | `150` | Page rasterization DPI (openrouter only) |

API keys come from environment variables, not flags.

## Known limitations

- **openrouter fallback drops embedded images**. The fallback vision-OCR path returns transcribed text for each rasterized page, but there is no positional mapping back to the PDF's embedded image streams, so the pipeline does not splice them back in. For image-faithful output, use the `mistral` provider.
- **openrouter free tier is rate-limited**. Long PDFs may hit the rate limit mid-run. If that happens, wait and retry, or switch to Mistral.
- **Math / LaTeX** is preserved via pandoc's `--mathml` output. Readers that don't support MathML (older Kindle formats) will render equations as plain text.
- **Skill text and script may diverge over time**. Before quoting the fallback model name, inspect `scripts/pdf_to_epub.py` rather than trusting stale prose in the skill.

## Verification

After running, sanity-check the output:

```bash
# Unzip the EPUB (it's a zip) and inspect
unzip -l /path/to/output.epub

# Or open in a reader
open /path/to/output.epub   # macOS → Apple Books

# Strict validation (optional)
epubcheck /path/to/output.epub
```
