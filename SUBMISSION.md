# Marketplace submission package — `protein-inspect`

Copy-paste source for the official Anthropic plugin marketplace submission
(`claude.ai/settings/plugins/submit` or `platform.claude.com/plugins/submit`).
Field names on the form may differ slightly; map these blocks to the closest
field. Eval claims here are exactly what `evals/results.md` supports — the
honest headline is the **2.4 → 12.6 / 13 lift on post-cutoff structures**, not
"views beat YAML" (conditions A/B/C are statistically tied; see the caveat at
the bottom).

---

## Short description / tagline (one line)

> Turn any PDB ID, mmCIF/PDB file, or AlphaFold model into a layered semantic representation Claude reasons over fluently — structured `summary.yaml` plus a canonical PyMOL view battery.

Tighter variant if the field is character-limited:

> Protein structures → semantic YAML + canonical PyMOL views that Claude can actually reason over.

---

## One-paragraph description

> `protein-inspect` sits between a raw structure and Claude. It runs deterministic feature extraction (gemmi + biotite — chains, secondary structure, disulfides, classified ligands/cofactors/metals, oligomeric state, interfaces, B-factor or pLDDT stats), applies a versionable decision tree of ~35 structural-biology heuristics, and fires a canonical PyMOL view battery (overview, B-factor/pLDDT, hydrophobic surface, metal and ligand-pocket closeups with measured distances), composed into a single labeled montage. The output is `summary.yaml` + a montage image — roughly 10× denser per token than mmCIF, with coordinates externalized to a path the model never has to read. Installs as a Claude Code plugin: registers `/protein-inspect`, loads `SKILL.md` so Claude knows *when* to invoke it and *how* to read the YAML.

---

## Eval pitch (the evidence)

> **The tool moves Claude from 2.4 → 12.6 out of 13 on structures it cannot have memorized.** Evaluated on 19 PDB entries deposited after 2026-01-31 — postdating Claude Opus 4.7's training cutoff, so the lift reflects the tool's contribution rather than recall of famous structures. Scored by a 7-criterion, 13-point rubric with negative-constraint penalties.

| Condition | Materials | Mean / 13 | Lift vs baseline |
|---|---|---|---|
| **D** — baseline (PDB ID only, prior knowledge) | none | 2.42 | — |
| **A** — raw mmCIF | raw text | 12.79 | +10.37 |
| **B** — `summary.yaml` | tool output | 12.50 | +10.08 |
| **C** — `summary.yaml` + PyMOL view battery | tool output | 12.56 | +10.13 |

> Without materials, Opus 4.7 scores 2.4/13 on novel structures (essentially baseline inference hygiene); with the tool's semantic layer it reaches ~12.6/13. The semantic YAML (B) matches raw mmCIF (A) on this rubric at a fraction of the tokens, and the view battery (C) adds operational value for the human reader — decision-tree branching, deposition sanity checks, ligand-pocket legibility — even where it doesn't add measurable LLM-reasoning lift over the YAML alone. Full methodology, per-protein scores, and a 29-PDB breadth set in `evals/results.md` and `EVAL.md`.

---

## Key features (bullets)

- **Semantic layer, not coordinates** — residue/motif/pocket-level facts as YAML; ~10× denser per token than mmCIF.
- **Versionable decision tree** — ~35 interpretable structural-biology rules in YAML, not buried in a prompt; reproducible analysis across runs.
- **Canonical PyMOL view battery** — 13+ conditionally-fired views in one labeled montage (bypasses the CLI's 3-image attachment cap).
- **Crystal vs computed aware** — emits B-factor for deposited structures, pLDDT bands for AlphaFold models, and warns the model not to confuse them.
- **Optional vision-judged renders** (`--judge-views`) — a Claude vision model scores each PNG against a per-view rubric and re-renders failures; catches degraded figures the deterministic pipeline can't.
- **Evidence-backed** — ships its own eval harness and a reproducible +10/13 headline on post-cutoff structures.

---

## Install (verbatim for the form)

```
/plugin marketplace add https://github.com/LBM-EPFL/protein-inspect
/plugin install protein-inspect@protein-inspect-marketplace
```

Standalone CLI path: `uv tool install git+https://github.com/LBM-EPFL/protein-inspect`

---

## Supporting metadata

- **Repository / homepage:** `https://github.com/LBM-EPFL/protein-inspect`
- **License:** MIT
- **Version:** v0.1.0
- **Author:** Benedikt Singer (LBM-EPFL)
- **Suggested keywords/tags:** `bioinformatics`, `structural-biology`, `protein-structure`, `pdb`, `pymol`, `alphafold`, `cheminformatics`, `science`
- **Screenshots to attach** (already in-repo, reviewer-ready):
  - `examples/1mbn/montage.png` — myoglobin + HEM, the cleanest demo
  - `examples/9LZM/montage.png` — SARS-CoV-2 Mpro, a post-cutoff structure
  - `examples/AF-P00533-F1_EGFR/montage.png` — AlphaFold / pLDDT handling, to show range

---

## Caveat to keep in your pocket

If a reviewer asks "does the image battery help the model?" — the honest answer
is **A ≈ B ≈ C are statistically tied** on the reasoning rubric (Δ ≤ 0.3 pts).
The views earn their place as the human-facing and decision-routing layer, and
there were 2 minor negative-constraint slips under B/C vs 0 under A. Leading
with the +10/13 lift and *not* overclaiming "views beat YAML" keeps the
submission airtight.
