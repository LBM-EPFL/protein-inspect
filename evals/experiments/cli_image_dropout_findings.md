# `claude -p` @-path image-attachment dropout — investigation

## TL;DR

When you pass `claude -p` more than 3 image attachments via the `@path` syntax inside a "typical" prompt (anything multi-sentence, or with paragraph structure, or longer than ~50 chars before the `@`-block), **the CLI silently caps delivery at the first 3 images**. The model receives only 3 and explicitly reports "image N was not rendered to me" for the rest. The cost report reflects the truncated payload (~$0.08, consistent with 3 images), not the attempted payload.

This is the actual source of the `9V4L / E` 4/13 score from the earlier ablation: the labeled metal closeup never reached the model. The labels themselves work fine — when the metal closeup was one of three attachments, Claude read `ZN`, `HIS54`, `1.9 Å`, etc. correctly from the image.

## Reproduction

Run `/tmp/cli_image_dropout_test.py` and `/tmp/cli_image_position_test.py` in the repo (`.venv/bin/python …`).

## Controlled experiment results

### Image-count sweep (1–5 attached), two prompt styles

| prompt | attached | reported | cost | input_tokens |
|---|---|---|---|---|
| short | 1 | 1 | $0.070 | 6 |
| short | 2 | 2 | $0.073 | 6 |
| short | 3 | 3 | $0.078 | 6 |
| short | 4 | **3** | $0.078 | 6 |
| short | 5 | **3** | $0.083 | 6 |
| long | 1 | 1 | $0.109 | 6 |
| long | 2 | 2 | $0.111 | 6 |
| long | 3 | 3 | $0.118 | 6 |
| long | 4 | **3** | $0.115 | 6 |
| long | 5 | **3** | $0.126 | 6 |

Both "short" and "long" prompts here are multi-sentence instructions ending with `\n\n` + the `@`-block. The cap is exactly 3 in both.

### Prompt-structure sweep (always 5 images attached)

| prompt structure | reported | cost | notes |
|---|---|---|---|
| `Count and describe each image briefly: @1 @2 @3 @4 @5` (one short sentence, `@`s immediately after a colon) | **5** | $0.109 | works |
| Same text, then `\n\n@1 @2 @3 @4 @5` | **5** | $0.112 | works |
| Same text, then `\n\n@1\n@2\n@3\n@4\n@5` (one per line) | **5** | $0.111 | works |
| Same text, comma-separated `@1, @2, @3, @4, @5` | **5** | $0.113 | works |
| Text + `@s` + more text after | **3** | $0.078 | text after `@`-block triggers cap |
| Multi-sentence text + `@s` (3+ periods in user prompt) | **3** | $0.085 | multi-sentence triggers cap |
| Same text moved to `--system-prompt`, short user prompt with `@s` | **3** | $0.203 | system-prompt workaround doesn't help — system prompt is just expensive |

### Threshold sweep — what exactly triggers the cap?

| case | sentences | reported | cost |
|---|---|---|---|
| 40 chars, 1 sentence (`: @...`) | 1 | **3** | $0.026 |
| 100 chars, 1 sentence (`: @...`) | 1 | **5** | $0.111 |
| 180 chars, 1 sentence (`: @...`) | 1 | **5** | $0.114 |
| 60 chars, 2 sentences (`. @...`) | 2 | **3** | $0.083 |
| 120 chars, 3 sentences | 3 | **3** | $0.082 |
| 300 chars, 1 long sentence (`: @...`) | 1 | **3** | $0.106 |

The cap behavior is not a clean monotonic function of length. The robust signal is: **periods / multiple sentences before the `@`-block reliably trigger the 3-image cap.** Single-sentence prompts ending in `: @...` mostly deliver all 5, with some inconsistency at the extremes.

The `input_tokens` field in the CLI's JSON output is consistently `6` regardless of actual prompt size — it's not a usable signal for diagnosing what was sent.

## Mechanism (inferred)

From official docs (researched via Claude Code agent):

- The Anthropic API supports **100–600 images per request** for Opus 4.7 — so the limit is **not** server-side.
- The Claude Code CLI's `@path` syntax expands attachments into image content blocks before sending.
- There are open GitHub issues about silent multi-image dropout: [#39708](https://github.com/anthropics/claude-code/issues/39708) (drag-and-drop drops all but first), [#53170](https://github.com/anthropics/claude-code/issues/53170) (dimension-limit failure isn't graceful), [#14107](https://github.com/anthropics/claude-code/issues/14107) (image-size regression).
- **No documented per-image flag** (no `--image <path>` for one-per-call attachment); no documented way to verify image-count server-side from CLI output.

Most likely root cause: the CLI's prompt-parser caps `@path` expansion at 3 when the surrounding text looks like a "real prompt" (multiple sentences / paragraphs) rather than a bare attachment list. This is undocumented but reproducible.

## Implication for the eval

Our condition C in the v2 holdout eval attached **5–9 PyMOL views per protein** to a ~600-word structural-analysis prompt. **All but the first 3 were silently dropped.** That means:

- The condition C result of `12.56` mean (vs B's `12.50`, A's `12.79`) on the holdout was effectively *"3 views + YAML"* not *"full view battery + YAML"*.
- The earlier 9V4L/E 4/13 image-only result was *"top + side + B-factor only"* — the labeled metal closeup never reached the model.
- The view battery additions from the last round (labeled cofactor / glycan / NA / peptide closeups) won't be visible to Claude under condition C without a workaround.

## Workarounds — ranked

1. **Truncate per-protein attachments to ≤3 images at submit time, prioritizing the most informative views.** Easiest. Sketch:
   - Always include `01_top.png`.
   - If a labeled close-up exists (`metal`, `cofactor`, `ligand_pocket`, `peptide_interface`, `na_interface`, `glycan`), include the highest-priority one (per decision-tree priority).
   - Fill the third slot with `04_surface_hydrophobic.png` if no chemistry close-up, else `02_side.png`.
   - Costs: minor accuracy regression on multi-feature structures where two close-ups would help. No code rework.

2. **Render a montage**: combine 4–9 views into one 2400×1800 PNG with the view names burned in. Then the CLI only handles a single attachment that won't hit the cap. Implementation: a new view-battery post-step that PIL-pastes the rendered PNGs into a grid. Trade-off: each panel is now ~600×450 inside the montage, so the label-size bump we did earlier may need another increase.

3. **Switch to the Anthropic SDK** with an API key (not Max-subscription) and explicit `content` block construction in Python. Bypasses the CLI's prompt parser. Requires the user to set `ANTHROPIC_API_KEY` and replumb `run_eval.py` to use `anthropic.Anthropic().messages.create(...)` directly. Cleanest architecturally but needs auth setup.

4. **Try `--input-format stream-json`** with a manually constructed messages JSON over stdin. Untested here but worth checking — same effective bypass as (3) without leaving the CLI.

## Recommendation

Land #1 (3-image truncation with priority ranking) immediately as a defensive default in `run_eval.py`'s `build_prompt_for_condition`. It makes the eval results honest about what the model actually received. Then evaluate #2 (montage) as a follow-on if we want richer per-condition-C information without rewriting the auth layer.
