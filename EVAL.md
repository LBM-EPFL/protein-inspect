# Eval Methodology — How to evaluate `protein-inspect`

This document covers (a) how plugin/skill evals are done in the broader
ecosystem, (b) the specific approach I'd recommend for protein-inspect, and
(c) what you need to set up before I can run it.

---

## What evals are actually for

For a skill that produces text+images for Claude to reason over, the question
is **not** "does the skill produce correct output" — schema validation +
the Hallmark suite already cover that. The question is:

> **Does Claude reach better, more accurate, more reliable conclusions about
> a protein when given protein-inspect's output, vs. raw PDB text alone?**

If the answer is "no", the plugin is decoration. If the answer is "yes, with
specific differences X/Y/Z", that's the evidence we put in the README and
the marketplace submission.

The whole point of yesterday's reasoning about LLM-friendly representations
(layered semantic YAML, externalized coordinates, paired images) was that
this should be true. The eval is how we prove it instead of assuming it.

---

## How others do this — landscape

### General-purpose LLM evals
- **HELM** (Stanford), **MMLU**, **BIG-bench** — broad knowledge benchmarks.
  Useful as inspiration; not directly applicable to a domain plugin.
- **lm-evaluation-harness** (EleutherAI) — task-based eval framework. Designed
  for held-out test sets with verifiable answers (multiple-choice, regex match).

### Plugin / agent / skill evals
- **Anthropic's Evals** ([docs.claude.com/evals](https://docs.claude.com/en/api/evals)) —
  a managed product where you upload a dataset and rubric and Claude (or a
  configured judge) scores model outputs. In beta as of early 2026; the
  most natural fit for our case if you have access.
- **LangSmith Evals** (LangChain) — open-source, harness-style: define
  dataset → run chain → grade. Heavy on chains; the dataset layer is the
  reusable part.
- **OpenAI Evals** — same pattern. Lots of templates for different grader
  types (exact match, fuzzy, LLM-as-judge, code-eval).
- **PromptFoo** — CLI-first eval runner. Good for side-by-side comparison
  across prompt variants. Simple and self-hosted; what I'd reach for first
  if Anthropic's Evals product isn't available.

### Domain-specific structural-biology evals
- **CASP** — protein-structure prediction competition. Not applicable but
  worth knowing because it's the gold standard for "is this protein
  structure correct" — runs every two years with curated targets.
- **BENCHFLOW / ProteinGym** — benchmarks for protein-function prediction,
  variant effect, etc. Different problem space (sequence-only) but same
  rigor pattern: held-out test set + standardized scoring + leaderboard.
- **There is no standard benchmark for "LLM reasoning over protein
  structure"** — which is why we have to design our own. v1 of this eval
  could *become* such a benchmark if scoped carefully.

### The pattern that recurs in all of them
1. **Curated test set** — small (20–200) but diverse, with ground-truth answers
2. **Standardized rubric** — checkable claims, not free-form judgement
3. **Multiple conditions** — typically baseline + variants
4. **Reproducible run** — pinned model version, fixed temperature, recorded seed
5. **Scoring is the bottleneck** — either expensive expert humans, or an
   LLM judge with its own validation
6. **Public results** — a table that shows what was compared, what won, by
   how much

---

## Recommended methodology for protein-inspect

### Test set: reuse the 20-PDB Hallmark with hand-curated ground truth

The 20 PDBs in `tests/test_hallmark.py` already span the breadth we care about
(monomers, oligomers, membrane, protein-NA, all five active-site patterns,
all four cofactor classes). For each, we need a small **ground-truth file**
listing what an expert would expect Claude to identify.

Format (one file per PDB):

```yaml
# evals/ground_truth/2zju.yaml
pdb: 2zju
description: |
  Ls-AChBP pentamer in complex with imidacloprid. Soluble structural homolog
  of the extracellular ligand-binding domain of nicotinic acetylcholine
  receptors. Used as a model for nAChR pharmacology and neonicotinoid action.

expected_features:
  fold_class:
    must_mention: ["β-sandwich", "immunoglobulin-like", "Ig fold", "Cys-loop receptor"]
    at_least_one: true
  oligomeric_state:
    correct_answer: "homopentamer"
    acceptable: ["pentamer", "C5", "5-mer"]
  ligand:
    must_identify: "imidacloprid"
    or_correctly_describe: ["neonicotinoid", "nAChR agonist mimic"]
  active_site:
    location: "subunit interface"
    aromatic_cage_residues:
      principal: ["TRP143", "TYR185", "TYR192"]
      complementary: ["TRP53", "TYR113", "TYR164"]
  notable_features:
    must_mention_one:
      - "vicinal disulfide"
      - "Cys-loop"
      - "Loop C"

negative_constraints:
  # Things the response MUST NOT claim
  - "must not call it a kinase"
  - "must not call it a protease (catalytic_triad false-positive guardrail)"
  - "must not claim it is a membrane-spanning protein"
```

The negative constraints are critical — protein-inspect's known false positives
(catalytic_triad_geometry firing on AChBP, membrane_likely firing on the
membrane-interface beta-sheet) test whether Claude correctly *contradicts*
the over-eager flag based on other evidence.

### Conditions to compare

| Label | What Claude sees in the prompt |
|---|---|
| **A** (baseline) | Raw PDB text (~50k tokens for medium proteins). Question: "Analyze this protein." |
| **B** (skill, text only) | `summary.yaml` only, no images. Same question. |
| **C** (skill, full) | `summary.yaml` + the canonical PyMOL view battery. Same question. |
| **D** (control) | PDB ID only ("Tell me about 2ZJU"). Tests how much of Claude's answer is recall vs. extraction. |

The crucial comparison is **B vs A** (does the YAML help?) and **C vs B** (do
the images add value beyond the text?). D vs A is a sanity check — if D is
already strong because the structure is famous, the lift from the skill on
that entry doesn't generalize.

### Rubric

Each prediction is scored against the ground-truth file. Use a fixed point
system; LLM-as-judge fills in the marks.

| Category | Points | Pass criterion |
|---|---|---|
| Identity / function | 2 | The response correctly names the protein OR (if narrative is null) correctly identifies the functional family from structure |
| Oligomeric state | 1 | Correct N-mer and (where applicable) symmetry |
| Fold class | 2 | Matches `expected_features.fold_class.must_mention` |
| Active site / mechanism | 3 | Correctly identifies catalytic residues, mechanism class, and pocket location |
| Cofactors / metals / ligands | 2 | Correctly identifies what's bound (with chemistry, not family) |
| Notable features | 2 | Catches family-defining motifs (vicinal disulfide, Fe-S cluster, etc.) |
| Negative constraints | -2 each | Hard penalty for false-positive claims |
| Inference hygiene | 1 | For unannotated structures, response marks inferences as inferences |

Total: 13 points possible. Pass = ≥9. Strong = ≥11.

### Judging

I'd recommend a **two-step LLM judge**:
1. **Extraction step** — small fast model (Haiku) extracts structured claims
   from the free-form Claude response: "what did the response say about
   oligomer, fold, catalytic residues, etc."
2. **Scoring step** — same fast model compares each extracted claim against
   the ground-truth file. Scoring is deterministic given the extraction.

This is more reliable than asking a single model to read both the response
and the rubric and emit a number. Separating extraction from scoring also
lets you spot-check the extraction independently.

**Sanity-check**: hand-score 3–5 entries yourself and confirm the judge
agrees within 1 point per category. If not, the rubric or extraction prompt
needs tightening.

### Reporting

A single markdown table:

```
| PDB  | A (raw PDB) | B (YAML)    | C (YAML+imgs) | D (ID only) | best ground-truth |
|------|-------------|-------------|---------------|-------------|-------------------|
| 1ubq | 6.5/13      | 11/13       | 12/13         | 9/13        | 13 (manual)       |
| 2zju | 5/13        | 10/13       | 12/13         | 7/13        | 12                |
| ...  | ...         | ...         | ...           | ...         | ...               |
| MEAN | 6.1         | 10.4        | 11.7          | 7.8         | 12.4              |
```

Plus 3–5 per-PDB qualitative examples showing where C wins, where C
matches B, and where the skill flags a false positive that Claude needs to
contradict.

---

## What you need to set up before I run the eval

### 1. Ground-truth files (the bottleneck)

20 small YAML files like the example above. **This is the hardest part — it
needs domain knowledge.** Two ways to get them:

**Option A — fast, lower-quality**: I draft all 20 ground-truth files from
PDB titles, UniProt entries, and my training-data recall. You spend ~30
minutes reviewing each, flagging anything you'd phrase differently. Total
your time: ~5–8 hours of focused review.

**Option B — slow, higher-quality**: You write them from scratch with
literature in front of you. Two hours per entry → ~40 hours total. Higher
fidelity, especially for the negative constraints.

For v1 submission, Option A is sufficient. The eval just has to be
*reproducible* and *honest about its methodology*, not perfect.

### 2. Auth — Max plan via claude-agent-sdk (no API key needed)

**LOCKED:** the eval driver uses the official `claude-agent-sdk` Python
package, which authenticates against the user's Claude.ai login (the same
mechanism Claude Code itself uses). Usage counts against the Max plan's
rate limit instead of API billing, so no `ANTHROPIC_API_KEY` is required.

```bash
# nothing extra to set — Claude Code's existing login is reused
uv add claude-agent-sdk
```

Practical implications:
- **No setup cost**: already authenticated if Claude Code works.
- **Rate-limit awareness**: Opus 4.7 is the most expensive model against the
  Max plan budget. The driver runs with small concurrency (4 in-flight),
  exponential backoff on 429s, and caches every (prompt → response) pair
  to disk so re-runs only re-call what changed. Expect a full run to take
  ~30–60 minutes wall time.

### 3. Models — LOCKED

- **Model under test (subjects A/B/C/D)**: claude-opus-4-7
- **Judge model (extraction + scoring)**: claude-opus-4-7

Rationale (per user choice 2026-05-11): Opus is the most capable model and
gives the tightest signal on whether protein-inspect's outputs change
Claude's reasoning. Slower / higher rate-limit burn than the original
Haiku-judge proposal, but the eval has to be defensible for the
marketplace submission and Opus-judging is the strongest available
option without paying for OpenAI/Gemini as cross-judges.

### 4. Time budget for review

After I run the eval, you'll want ~2 hours to:
- Spot-check 5 judge scores against your own reading
- Read the qualitative examples
- Confirm the headline numbers are honest before they go in the README

### 5. Decide where eval lives in the repo

I'd suggest:
```
evals/
├── ground_truth/        # 20 YAML files (your curation)
│   ├── 1ubq.yaml
│   ├── 2zju.yaml
│   └── ...
├── prompts/
│   ├── system.md        # the system prompt for the eval runs
│   ├── question.md      # the question Claude is asked
│   └── judge_extract.md # extraction prompt for the judge
│   └── judge_score.md   # scoring prompt for the judge
├── runs/                # one subdir per run, dated + commit-hashed
│   └── 2026-05-11_abc123/
│       ├── condition_A/
│       ├── condition_B/
│       ├── condition_C/
│       ├── condition_D/
│       └── scores.csv
├── results.md           # the headline table, regenerated each run
└── run_eval.py          # the driver script
```

The `results.md` is what goes in the README as the eval evidence.

---

## Estimated effort once you've set up (1) above

| Task | Who | Time |
|---|---|---|
| Write `run_eval.py` + judge prompts | me | 2 days |
| Run the first eval | me | ~1 hour wall, ~$1–10 API |
| Review judge calibration | you | 1 hour |
| Iterate on rubric if needed | me | 0.5 day |
| Final eval run | me | 1 hour |
| Write the results.md | me | 1 hour |

**Total: ~4 days of my work + 1 day of your review, after the ground-truth
files exist.**

---

## What I'd recommend right now

1. **Pick Option A** (I draft ground truth, you review) unless you have
   strong reasons for Option B.
2. **Confirm the rubric** above (point values, categories) — these are
   load-bearing for the headline numbers. Edit it before I draft anything.
3. **Decide on Sonnet-4-6 as the model under test** unless you want to
   include Opus.

Once those three things are settled, I:
1. Draft the 20 ground-truth files
2. You review them (the long step on your side)
3. I write the eval driver + judge prompts
4. I run the eval, you spot-check, we publish the table

Then Phase 3 (marketplace submission) becomes trivial — we just point at
the eval results.

---

## Honest caveats about this whole approach

1. **The judge is also a Claude model.** Self-judging has bias risks. The
   mitigation is the extraction/scoring split + your spot-check, but for a
   marketplace submission someone could reasonably ask for a non-Claude
   judge. PromptFoo supports OpenAI and Gemini as judges if we want to
   add that.

2. **20 proteins is small.** It's enough to detect large effects (A vs B)
   but probably not enough to distinguish B from C at p<0.05. The
   bootstrap CIs will be wide. Honest framing: this is an indicative
   eval, not a definitive one.

3. **Ground truth from a single curator (you) has its own bias.** v2
   could solicit secondary review from 1–2 other structural biologists if
   you want a stronger evidence claim.

4. **The eval doesn't test downstream task performance** — e.g., "did
   Claude help the user design a better inhibitor?" That's a much harder
   eval requiring real user studies. Out of scope for v1 marketplace
   submission; potentially relevant for a paper.
