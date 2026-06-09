# `protein-inspect` — A Claude Code Skill for Protein Structure Reasoning

A Claude Code plugin that turns any PDB ID or local structure file into a layered semantic representation Claude can reason over fluently — combining a deterministic PyMOL view battery, tool-derived quantitative features, and a codified inspection decision tree. Output is YAML + a small set of standardized images.

**Repository**: `~/claude_mol_test/` (working dir; not yet pushed to a remote)
**Plugin name**: `protein-inspect`
**License**: MIT
**Phases scoped here**: 0 (scaffolding), 1 (skill v1), 2 (eval), 3 (publish). The MCP server for remote DB access is deliberately out of scope for this plan — see `Out of Scope` at the bottom.

---

## Current status (2026-06-09)

| Phase | Status | Notes |
|---|---|---|
| 0 — Scaffolding | ✅ done | Repo layout, `pyproject.toml`, plugin manifest all present. |
| 1 — Skill v1 | ✅ done, larger than scoped | All four contract files exist (schema, decision tree, view battery, analyze prompt). `features.py` ended up ~1600 lines (vs. 1-day estimate). View battery expanded to 10+ views. Added `ligand_classes.yaml` and a fold-class "hallmark" suite that weren't in the original plan. Test suite: 7 files, ~1.5 K lines. |
| 2 — Eval harness (v1 breadth + v2 holdout) | ✅ done | **v1 breadth set**: 29 famous PDBs (incl. 3 AlphaFold-DB), canonical run `2026-05-14_1140_nogit`, 120/120 cells scored. Useful as a breadth check but ceiling-limited. **v2 holdout set**: 19 PDBs released ≥2026-02-01 (post Opus 4.7 training cutoff), canonical run `2026-05-28_1345_nogit`, 74/76 cells scored (2 cells of 9OVL/extract refused on policy; full 25PV entry was unrecoverable on anthrax-topic refusal and dropped). 4 conditions A/B/C/D. Eval driver at v12: cache-on-disk, resume-aware, rate-limit-aware, content-refusal-aware (with 3-tier academic-context retry). Ground-truth verifier at v1.3 (biological-assembly-aware): **29/29 clean on v1, 19/19 clean on v2.** Results published at `evals/results.md`. |
| 3 — Publication | 🟢 self-publish shipped; official marketplace pending | Canonical repo now `github.com/LBM-EPFL/protein-inspect` (public); gitlab (`origin`) kept as a secondary mirror. `v0.1.0` tagged on both. `plugin.json` + README install URLs point at GitHub. README rewritten around the eval findings; `--judge-views` documented. **Self-publish install path works today.** Remaining for the *official* Anthropic marketplace: add CI, then submit. |

### Eval findings (TL;DR; see `evals/results.md` for the full tables)

**The holdout (post-cutoff) set is where the real signal lives.** Headline means on the 19 holdout PDBs:

| Condition | Mean | Lift vs D |
|---|---|---|
| **D** (no materials, baseline) | **2.42** | — |
| **A** (raw mmCIF) | **12.79** | **+10.37** |
| **B** (`summary.yaml`) | **12.50** | **+10.08** |
| **C** (`summary.yaml` + view battery) | **12.56** | **+10.13** |

Two clean findings:

1. **`protein-inspect` materials provide ~10/13 points of lift on structures Claude doesn't already know.** Without materials, Opus 4.7 scores 2.4/13 on post-cutoff PDBs (essentially just "inference_hygiene" 1pt baseline + occasional partial credit). With any of the three materials conditions, Claude jumps to ~12.6/13. This is the marketplace-headline-grade evidence the original PLAN said we needed.

2. **The "C > B >> A" hypothesis is NOT supported.** A, B, C are statistically tied (Δ ≤ 0.3 points). Three things follow:
   - The decision-tree-driven YAML (B) is essentially equivalent to raw mmCIF (A) for this rubric. The judge can extract identity/oligomer/fold from either.
   - The view battery (C) does not add measurable headline lift over the YAML (B).
   - C and B both have **2 cells with negative-constraint violations vs 0 for A** — the early-warning signal that images may distract more than help in a small fraction of cases (9N97 intrabody is the clearest example: A=13, B=10, C=10, D=6 — the materials *hurt* by 3 points relative to A).

Implications for shipping:
- **Headline claim is well-founded**: the tool moves Claude from 2.4 → 12.6 / 13 on novel structures. Write the README around that.
- **Don't oversell C vs B**: the view battery is operationally useful (decision-tree branching, debugging, deposition checks) but doesn't measurably help LLM reasoning on this rubric. Frame it as "for the human user" not "for Claude".
- **Investigate the 9N97 / 9OVL / 9QNM "A beats materials" cases.** Pattern: A wins by 2-3 pts on engineered/designed proteins (9N97 intrabody, 9QNM PHL7 variant) and on viral glycoproteins (9OVL). For 9N97 + 9QNM the engineered context may strip something the YAML loses; for 9OVL the policy refusals leave only A.
- The v1 breadth run is now a *reference* — it tells us the tool doesn't break on famous targets, but doesn't carry the headline.

### Remaining work to ship v0.1

Done since this section was first written:
- ✅ Real gitlab URLs in `.claude-plugin/plugin.json` + `marketplace.json` (no `USER` placeholders).
- ✅ Repo committed and pushed to `origin` (gitlab.epfl.ch).
- ✅ `examples/1mbn/` is a complete demo dir (`summary.yaml` + `montage.png` + `views/` + source `.cif`).
- ✅ README headline written around the **+10.37 / +10.08 / +10.13 holdout lift** with the negative-constraint caveat on C.
- ✅ `--judge-views` vision-judged render loop added and documented (README, SKILL.md, analyze.md).

Still open for the *official* Anthropic marketplace (self-publish already works):
- Tag `v0.1.0` and push the tag.
- ✅ Mirrored to GitHub (`github.com/LBM-EPFL/protein-inspect`, public) — now the canonical home; manifests + README repointed there.
- Add CI to run the test suite on push (nice-to-have; reviewers expect it).
- Optional: investigate the 9N97 / 9QNM "A beats materials" pattern. If a small features.py fix recovers those, the B and C numbers go up; if not, document the limitation in the README.

### Known limitation — Claude Code CLI image-attachment cap

The Claude Code CLI silently caps `@path` attachments at 3 images per non-trivial prompt. See `evals/experiments/cli_image_dropout_findings.md` for the controlled-experiment evidence. The full view battery is usually 5–9 PNGs per protein, so attaching them individually loses 2–6 of them server-side with no visible error — the model receives only 3.

**Current workaround (in v0.1):** `protein-inspect` now also emits a labeled-grid `montage.png` alongside the individual views. `run_eval.py` attaches that single composite for condition C, which bypasses the cap. See `src/protein_inspect/montage.py`.

**Future alternative (post-v0.1):** bypass the CLI entirely by calling the Anthropic SDK directly with explicit `content` blocks per image (`anthropic.Anthropic().messages.create(...)`). Requires an `ANTHROPIC_API_KEY` (the Max-subscription auth used by `claude -p` does not carry over) and a small replumb of `run_eval.py`'s subprocess wrapper. Worth doing if we want per-image cost attribution, scale to many-image conditions, or have any other reason to need full control of the request shape — but not required to ship v0.1.

---

## Architectural Premise

LLMs reason poorly over raw PDB/mmCIF coordinates (token economics, fixed-column formats, no metric closeness in token space). They reason well over:

1. **A semantic YAML summary** — residues with roles, ligands as SMILES, named geometric features, motifs, provenance. This is the precise quantitative layer.
2. **A standardized image battery from PyMOL** — overview, side, B-factor, surface, ligand pocket. This is the spatial-gestalt layer.

Combined, these are an order of magnitude denser per token than coordinates and avoid the failure modes of feeding atomic data into an LLM prompt. The decision of *what to look at* is encoded in the skill (decision tree), not left to ad-hoc Claude judgment per call. That's the whole point of a skill: reproducible inspection, every time, regardless of which thread of reasoning Claude happens to follow first.

---

## Phase 0 — Repo Scaffolding (½ day) — ✅ done

```
claude-protein-tools/
├── README.md
├── LICENSE
├── .claude-plugin/
│   ├── plugin.json                    # plugin manifest
│   └── marketplace.json               # for self-publish path
├── plugins/
│   └── protein-inspect/
│       ├── SKILL.md                   # entry point
│       ├── inspect.py                 # CLI driver
│       ├── pyproject.toml             # uv-managed deps
│       ├── decision_tree.yaml         # codified inspection logic
│       ├── view_battery.yaml          # standardized PyMOL views
│       ├── schema/
│       │   └── summary.schema.json    # YAML output schema
│       ├── prompts/
│       │   └── analyze.md             # how Claude reads the output
│       └── src/protein_inspect/
│           ├── pymol_runner.py        # claudemol socket + render loop
│           ├── features.py            # gemmi/biotite feature extraction
│           ├── decision.py            # walks decision_tree.yaml
│           └── emit.py                # writes summary.yaml
├── evals/
│   ├── proteins.yaml                  # 20 ground-truth structures
│   ├── rubric.yaml                    # scoring criteria
│   └── run_eval.py                    # harness
└── examples/
    └── 1mbn/                          # worked example with screenshots + YAML
```

**Deliverables for Phase 0:**
- Repo created, plugin manifest valid, `.claude-plugin/marketplace.json` registered
- `uv venv` + `pyproject.toml` declaring deps: `gemmi`, `biotite>=1.4`, `pyyaml`, `claudemol`
- `SKILL.md` skeleton with trigger conditions and command shape

---

## Phase 1 — `protein-inspect` Skill v1 (3–5 days) — ✅ done (took longer; more breadth)

**Divergences from the original spec:**
- `features.py` is ~1.6 K lines, well beyond the 1-day estimate. Reality required handling for: AFDB models, biological assembly vs ASU, ligand chemistry classes, multi-cleaved chains (chymotrypsin), protein/NA complexes (Cas9-sgRNA), domain detection fallbacks (CATH via SIFTS + length heuristic), etc.
- `view_battery.yaml` grew from 6 → 10+ views (added `surface_hydrophobic`, `membrane_belt`, per-ligand pocket views with chain selectors).
- Added `ligand_classes.yaml` (chemistry-class lookup, not in the original plan) and a fold-class "hallmark" library at `examples/hallmark/` with 17 reference entries.
- Test suite: 7 files (~1.5 K lines) including `test_hallmark.py` and `test_p1_p2_fixes.py` — the latter indicates iterations beyond v1.0.

The skill takes a PDB ID or local structure path and emits a `summary.yaml` plus an optional rendered view battery. The inspection pipeline is **deterministic** — no LLM in the loop during execution. The LLM enters at the analysis step, reading the YAML + images.

### 1.1 — `summary.yaml` schema

The output schema, locked before any code is written. This is the contract between the skill and the LLM that reads it.

```yaml
# summary.yaml — output contract
entry: 1MBN                           # PDB ID or filename
generated: 2026-05-06T14:32:00Z
schema_version: "1.0"

narrative: |                          # one-paragraph human-readable summary
  Lymnaea stagnalis acetylcholine binding protein (Ls-AChBP)
  in complex with the neonicotinoid imidacloprid. Soluble homo-
  pentameric surrogate for the nAChR ligand-binding domain.

provenance:                           # facts about the structure file itself
  source: rcsb
  resolution: 2.58
  method: X-RAY DIFFRACTION
  space_group: "P 65"
  unit_cell: [74.97, 74.97, 351.01, 90.0, 90.0, 120.0]
  deposition_date: 2008-04-21         # when available

assembly:                             # quaternary structure
  oligomer: pentamer
  symmetry: C5
  chains: [A, B, C, D, E]
  chain_rmsd_max: 0.42                # max RMSD among chains (A is reference)
  interface_contacts:                 # CA-CA at 4 Å, inter-chain
    - { pair: [A, B], n_residues: 6 }
    - { pair: [B, C], n_residues: 5 }
    - { pair: [C, D], n_residues: 7 }
    - { pair: [D, E], n_residues: 6 }
    - { pair: [E, A], n_residues: 6 }

fold:                                 # per-representative-chain
  representative_chain: A
  length: 215
  ss_fractions: { helix: 0.07, sheet: 0.42, loop: 0.51 }
  ss_string: "..."                    # one char per residue (H/E/L)
  bfactor_stats:
    mean: 40.1
    min: 0.0
    max: 90.9
    high_b_regions:                   # residue ranges with B > 1σ above mean
      - { range: [156, 160], avg_b: 81.5, label: "flexible loop" }
      - { range: [187, 188], avg_b: 79.8, label: "vicinal disulfide loop" }

residues:                             # compact per-residue table, repr chain only
  format: "auth_seq_id resn ss b sasa"
  data: |                             # block scalar, parseable by skill not LLM
    -3 GLU L 0.0 -
    -2 ALA L 0.0 -
    ...

ligands:                              # auto-detected from HETATM
  - id: IM4
    name: imidacloprid
    smiles: "Clc1ccc(CN2CCN/C2=N\\[N+](=O)[O-])cn1"
    n_copies: 5                       # total in asymmetric unit
    placement: subunit_interface       # auto-classified
    binding_residues:                 # within 5 Å, grouped by face
      principal:                      # chain providing main contacts
        chain: A
        residues: [TRP143, THR144, TYR185, CYS187, CYS188, TYR192]
      complementary:
        chain: B
        residues: [TRP53, GLN55, LEU102, ARG104, TYR113, TYR164]
    aromatic_cage: true               # ≥3 aromatic residues within 5 Å
    occupancy_pattern: "4/5 sites occupied (B-C interface vacant)"

disulfides:                           # auto-detected by S-S < 2.1 Å
  - residues: [CYS123, CYS136]
    distance_a: 2.04
    type: standard
    annotation: cys_loop_canonical    # tagged by decision tree
  - residues: [CYS187, CYS188]
    distance_a: 2.05
    type: vicinal                     # consecutive in sequence
    annotation: loop_C_alpha_subunit_marker
    flexibility: high                 # both residues > 75 B-factor

motif:                                # only present if --motif passed or auto-found
  name: cys_loop_aromatic_box
  detected_by: decision_tree
  residues:
    aromatic_box:    [TRP143, TYR185, TYR192, TRP53, TYR113, TYR164]
    cys_loop_ss:     [CYS123, CYS136]
    vicinal_ss:      [CYS187, CYS188]
  geometry:
    aromatic_centroids_within_8a: true
    pocket_volume_a3: 412             # via fpocket if available

flags:                                # things the decision tree said deserve attention
  - "Vicinal disulfide CYS187-CYS188 detected (rare structural motif, hallmark of nAChR alpha subunits)"
  - "Asymmetric ligand occupancy: 4/5 binding sites occupied in C5 assembly"
  - "Aromatic cage (≥3 aromatic residues) at ligand binding site"

coords_ref:                           # never inlined
  path: ./1mbn.bcif
  format: bcif

visual:                               # optional, populated when --render-views
  views_dir: ./views/
  battery_version: "1.0"
  rendered:
    - { name: overview_top,    path: 01_top.png,        ray: true }
    - { name: overview_side,   path: 02_side.png,       ray: true }
    - { name: bfactor_chainA,  path: 03_bfactor.png,    ray: true }
    - { name: surface,         path: 04_surface.png,    ray: false }
    - { name: ligand_pocket,   path: 05_pocket.png,     ray: true,
        details: { ligand: IM4, chain: A } }
    - { name: vicinal_ss_zoom, path: 06_vicinal_ss.png, ray: true }
```

### 1.2 — `decision_tree.yaml` (the codified inspection)

This is the heart of the skill — the protocol that runs every time, in the same order, on every structure. Conditions are checked, actions are added to the run plan.

```yaml
# decision_tree.yaml
# Each rule: when CONDITION is true, append ACTIONS to the inspection plan.
# Order matters; rules execute top to bottom.

rules:

  - id: always
    when: true
    actions:
      - render_view: overview_top
      - render_view: overview_side
      - render_view: bfactor_chainA
      - render_view: surface
      - compute: ss_fractions
      - compute: bfactor_stats
      - compute: chain_rmsds

  - id: oligomer_detected
    when: "len(chains) > 1"
    actions:
      - compute: interface_contacts
      - compute: oligomer_state          # n-mer + symmetry from RMSDs/superposition
      - flag_if_asymmetric_ligand_occupancy: true

  - id: ligand_present
    when: "any(ligands)"
    actions:
      - render_view:
          name: ligand_pocket
          per_ligand: true               # one view per unique ligand
      - compute: binding_residues_5a
      - compute: aromatic_cage_check
      - compute: ligand_smiles_via_ccd

  - id: disulfides_present
    when: "any(disulfides)"
    actions:
      - flag: "Disulfide bond(s) detected"
      - render_view: disulfide_overview

  - id: vicinal_disulfide
    when: "any(d.type == 'vicinal' for d in disulfides)"
    actions:
      - flag_priority: high
      - render_view:
          name: vicinal_ss_zoom
          residues_padding: 5
      - annotate: "Vicinal (consecutive) disulfide is a rare motif. Check Cys-loop receptor family, redox switches, lectin alpha subunits."

  - id: high_bfactor_near_ligand
    when: "any(r.bfactor > 70 for r in binding_residues)"
    actions:
      - flag: "Mobile loop(s) at ligand binding site — possible induced fit / Loop C-style closure"

  - id: motif_user_specified
    when: "args.motif is not None"
    actions:
      - compute: motif_geometry
      - render_view: motif_focus

  - id: pentamer_with_pore
    when: "oligomer == 'pentamer' and has_central_cavity"
    actions:
      - annotate: "Pentameric ring with central pore — check for pLGIC (Cys-loop receptor) family, AB5 toxin B-pentamer, or PCNA-class clamp."
      - render_view: surface_top_pore_emphasis
```

This file is **opinionated structural-biologist domain knowledge**, not generic logic. It encodes things like "vicinal disulfides are noteworthy" and "mobile loops at ligand sites suggest induced fit." Adding rules is the primary mode of improving the skill.

### 1.3 — `view_battery.yaml` (standardized PyMOL views)

```yaml
# view_battery.yaml
# Each view is a fully-specified PyMOL command sequence with named output.
# Reused across structures — never tailored per-protein.

defaults:
  bg_color: white
  ray: true
  size: [1200, 900]
  ray_shadows: 1

views:

  overview_top:
    setup:
      - hide: everything
      - show: cartoon
      - util.cbc: true                 # color by chain
      - orient: ""
    output: 01_top.png

  overview_side:
    setup:
      - hide: everything
      - show: cartoon
      - util.cbc: true
      - orient: ""
      - turn: { axis: x, angle: 90 }
    output: 02_side.png

  bfactor_chainA:
    setup:
      - hide: everything
      - show: { rep: cartoon, sel: "chain A" }
      - color: { color: gray70, sel: "not chain A" }
      - spectrum: { expr: b, palette: blue_white_red, sel: "chain A" }
      - orient: chain A
    output: 03_bfactor.png

  surface:
    setup:
      - hide: everything
      - show: { rep: surface, sel: "polymer" }
      - util.cbc: true
      - set: { name: transparency, value: 0.1 }
    output: 04_surface.png
    ray: false                         # surfaces ray-trace slowly, skip

  ligand_pocket:                       # parameterized per ligand
    parameters: [ligand_resn, chain]
    setup:
      - hide: everything
      - show: { rep: cartoon, sel: "byres polymer within 8 of (resn {ligand_resn} and chain {chain})" }
      - show: { rep: sticks, sel: "(byres polymer within 5 of (resn {ligand_resn} and chain {chain})) and sidechain" }
      - show: { rep: sticks, sel: "resn {ligand_resn} and chain {chain}" }
      - color: { color: yellow, sel: "resn {ligand_resn}" }
      - label: { sel: "(byres polymer within 5 of (resn {ligand_resn} and chain {chain})) and name CA", expr: "resn+resi" }
      - orient: "resn {ligand_resn} and chain {chain}"
      - zoom: { sel: "resn {ligand_resn} and chain {chain}", padding: 8 }
    output: 05_pocket_{ligand_resn}_{chain}.png

  vicinal_ss_zoom:
    parameters: [chain, resi_a, resi_b]
    setup:
      - hide: everything
      - show: { rep: cartoon, sel: "chain {chain}" }
      - show: { rep: sticks, sel: "chain {chain} and resi {resi_a}-{resi_b}" }
      - color: { color: orange, sel: "chain {chain} and resi {resi_a}+{resi_b} and resn CYS" }
      - zoom: { sel: "chain {chain} and resi {resi_a}-{resi_b}", padding: 6 }
      - label: { sel: "chain {chain} and resi {resi_a}+{resi_b} and name CA", expr: "resn+resi" }
    output: 06_vicinal_ss_{chain}_{resi_a}-{resi_b}.png
```

### 1.4 — `prompts/analyze.md` (the LLM-facing read prompt)

Stable per-skill template. Same questions, same order, every call. This makes Claude's analysis reproducible across structures.

```markdown
# Protein Structure Analysis Prompt

You are reading the output of `protein-inspect`. Inputs:
- A `summary.yaml` (structured facts from gemmi/biotite/PyMOL)
- A directory of standardized PyMOL views (overview_top, overview_side,
  bfactor_chainA, surface, ligand_pocket, vicinal_ss_zoom if applicable)

Walk through the structure in the following fixed order. For each section,
ground claims in either a YAML field (cite the path: `summary.yaml#assembly.oligomer`)
or an image (cite the filename). Do not introduce numbers or residue identities
not present in the YAML.

1. **Identity & function**
   Use `narrative` and `provenance.source`. If `narrative` is empty (designed
   structure or unannotated PDB), say so explicitly.

2. **Quaternary structure**
   Read `assembly`. Confirm with `01_top.png` and `02_side.png`. Note any
   asymmetry (e.g. ligand occupancy mismatched with symmetry).

3. **Fold and flexibility**
   Read `fold.ss_fractions`, `fold.bfactor_stats`. Use `03_bfactor.png` to
   identify which regions are mobile. Connect mobile regions to functional
   sites if `flags` mentions overlap.

4. **Ligands and binding sites**
   For each entry in `ligands`: read placement, binding residues, aromatic
   cage status. Inspect `05_pocket_*.png`. Identify the chemistry class of
   the binding pocket (aromatic cage → cation-π / sugar binding; hydrophobic
   → lipid / steroid; charged → phosphate / nucleotide).

5. **Disulfides**
   List all `disulfides`. For any flagged `type: vicinal`, treat as a primary
   feature — these are rare and family-defining (Cys-loop receptors, certain
   lectins). Cross-reference `06_vicinal_ss_*.png`.

6. **Flags**
   Address every entry in `flags` — these are the decision tree's
   priority items.

7. **Hypotheses & follow-ups**
   Based on the above, propose: (a) likely functional class if not given,
   (b) what mutagenesis or follow-up experiment would test the inferred
   mechanism, (c) what a useful inhibitor pharmacophore would look like.

Respond as Markdown with the section headers above. Length: 400–800 words.
```

### 1.5 — Implementation order within Phase 1

| Day | Deliverable |
|-----|-------------|
| 1   | `pyproject.toml`, `pymol_runner.py` (claudemol wrapper), basic `inspect.py` CLI taking a PDB ID and producing a stub YAML |
| 2   | `features.py`: gemmi-based extraction (chains, SS via DSSP, B-factor stats, disulfide auto-detection, ligand auto-detection, interface contacts) |
| 3   | `decision.py`: walk `decision_tree.yaml`, apply rules, produce action list. Implement actions: `compute`, `flag`, `render_view`, `annotate` |
| 4   | View battery: implement all standard views in `view_battery.yaml` against running PyMOL via claudemol. Test on 5 different proteins |
| 5   | `emit.py`: produce final `summary.yaml` matching the schema. Validate against `summary.schema.json` (JSON Schema) |

**Phase 1 acceptance criteria:**
- Run `protein-inspect 1mbn --render-views` end to end without manual intervention
- Output `summary.yaml` validates against schema
- All 6 standard images render
- Re-running on the same input produces byte-identical YAML (modulo timestamps) and pixel-identical PNGs (modulo PyMOL nondeterminism flagged separately)
- Output captures everything I (Claude) found by hand on 1MBN today, without any of it living in my head

---

## Phase 2 — Eval Harness (2 days) — ✅ done; scope larger than planned

**Divergences from the original spec:**
- **29 ground-truth structures**, not 20. Includes 3 AlphaFold-DB models (`af_p00558`, `af_p02769`, `af_q9un36`) — touches v2 (designed/predicted) territory described later in the versioning roadmap.
- **4 conditions A/B/C/D**, not 3 (added D = no materials, prior-knowledge baseline). D is essential for separating the lift of materials from Claude's memorization of famous PDBs.
- Ground-truth files are individual YAMLs at `evals/ground_truth/*.yaml`, not a single `proteins.yaml`.
- Rubric is enforced by a Claude-as-judge two-stage pipeline (extract → score) rather than a Python-evaluated YAML check.
- `evals/verify_ground_truth.py` (388 lines) cross-checks every ground truth file against the deposited PDB: catalytic residues exist at the named positions, expected CCD codes appear, claimed oligomer matches the biological assembly from RCSB, etc. As of 2026-05-28 it reports **29/29 fully clean, 0 warnings, 0 failures.**
- The eval driver is at v12: per-prompt SHA16 disk cache, resume-from-state.json, exponential backoff on rate limits, content-refusal-aware retry with academic-context system prompt (for responses about pesticide chemistry, drug pockets, etc. that occasionally trip the CLI's content filter).
- Canonical run: `evals/runs/2026-05-14_1140_nogit/` — 120/120 cells scored, results aggregated at `evals/results.md`.

### 2.1 — `evals/proteins.yaml` — 20 ground-truth structures

Curated set spanning fold types, mechanisms, and edge cases:

```yaml
# 20 structures × known facts
- pdb: 1mbn
  expected:
    oligomer: pentamer
    fold_class: cys_loop_receptor_extracellular_domain
    has_vicinal_disulfide: true
    ligand_class: neonicotinoid_agonist
    notable_features: [aromatic_cage, asymmetric_ligand_occupancy]

- pdb: 1ubq
  expected: { oligomer: monomer, fold_class: ubiquitin, ... }

- pdb: 6vxx                    # SARS-CoV-2 spike
  expected: { oligomer: trimer, fold_class: viral_glycoprotein, ... }

# … 17 more covering: enzymes (with M-CSA mechanism), antibodies,
# membrane proteins, GPCRs, kinases, lectins, nucleic acid complexes,
# de novo designs (RFdiffusion outputs), cryo-EM low-res, virus capsids
```

### 2.2 — `evals/rubric.yaml` — fixed scoring

```yaml
criteria:
  - id: oligomer_correct
    points: 1
    check: "result.assembly.oligomer == expected.oligomer"

  - id: fold_class_identified
    points: 2
    check: "fold_class in result.narrative.lower() or fold_class in result.flags"

  - id: vicinal_ss_caught
    points: 2                  # high-value catch
    check: "expected.has_vicinal_disulfide → 'vicinal' in result.flags"

  - id: ligand_class_correct
    points: 1

  - id: notable_features_listed
    points: 0.5_per_feature
```

### 2.3 — `evals/run_eval.py` — three conditions (now four)

For each protein, run Claude (via API) on:
- **A**: raw PDB pasted into prompt
- **B**: `summary.yaml` only
- **C**: `summary.yaml` + image battery
- **D**: no materials — prior-knowledge baseline (added during implementation)

Score against the rubric. **Original hypothesis** (PLAN v1): **C > B >> A**, with the gap between B and C concentrated in spatial-gestalt criteria (oligomer, fold class) and the gap between A and B essentially everything.

**Actual headline results (see `evals/results.md`):** Means cluster within 0.5 points (A=12.67, B=12.40, C=12.37, D=12.17). The original ranking is *not* supported on the full set due to a ceiling effect — most eval PDBs are famous enough that Claude scores ~13/13 from prior knowledge alone. On the low-prior subset (D<12, n=6), materials clearly help (B−D = +2.83) — but C does not beat B, contradicting the spatial-lift prediction. Two action items: (1) tighten the README claim, (2) consider eval v2 with sealed-knowledge judge or holdout PDBs.

### 2.4 — Eval acceptance criteria — ✅ met

- ✅ Reproducible: same proteins, same prompts, same scoring → same numbers (cache makes re-runs free)
- ✅ Published in repo as `evals/results.md` with the full table (regenerated via `python evals/build_results.py`)
- ⚠️ Commit hash pinning — pending (no git commits yet); skill version is pinned via `pyproject.toml` = 0.1.0

---

## Phase 3 — Publication (1 day across both tracks) — 🟢 self-publish shipped

**Status as of 2026-06-09:** the original blockers (1–5 below) are all cleared.
Self-publish works today (canonical repo `github.com/LBM-EPFL/protein-inspect`,
`v0.1.0` tagged; gitlab kept as a mirror). What remains for the
official-marketplace track: add CI, then submit.

Original blockers, now resolved:
1. ✅ `.claude-plugin/plugin.json` carries the real gitlab URL (no `USER` placeholder).
2. ✅ Repo committed — `git log` has the full history.
3. ✅ Remote exists (`git@gitlab.epfl.ch:benedikt.singer/protein-inspect.git`); pushed. Tag `v0.1.0` still to do.
4. ✅ `examples/1mbn/` is a complete demo dir (`summary.yaml` + montage + views + `.cif`).
5. ✅ README headline reflects the actual eval findings (A≈B≈C tied at ~12.6, not the original "C > B >> A").

### 3.1 — Self-publish (immediate, no review)

1. Push repo to `github.com/<user>/claude-protein-tools`
2. Confirm `.claude-plugin/marketplace.json` valid
3. Test install from clean machine: `/plugin marketplace add <user>/claude-protein-tools` → `/plugin install protein-inspect`
4. Tag `v0.1.0`

Anyone can install from this point.

### 3.2 — Submit to official Anthropic marketplace

Submit at one of:
- claude.ai/settings/plugins/submit
- platform.claude.com/plugins/submit

Submission package:
- Plugin manifest (`plugin.json`) with: name, description, version, author, homepage (link to repo), repository, license
- README.md with: install instructions, usage examples, **eval results table from Phase 2**, screenshots of YAML output and a sample image
- LICENSE (MIT)
- Working install path verified
- Demo/examples directory (`examples/1mbn/` from this work, ready-made)

Once approved → `/plugin install protein-inspect@claude-plugins-official`.

---

## What This Does and Doesn't Do

**Does:**
- Turn any PDB ID into a layered semantic representation in seconds
- Render a fixed canonical image battery for spatial reasoning
- Encode structural-biology inspection knowledge in a versionable YAML decision tree
- Make Claude's structure analysis reproducible across calls
- Give Claude a much better representation than raw coordinates without inventing chemistry

**Does not:**
- Replace tools that compute physics (binding affinity, ΔΔG, MD)
- Generate designs (RFdiffusion etc. remain separate)
- Detect novel spatial features outside the precomputed view battery
- Cover all protein classes equally — opinionated toward enzymes, receptors, oligomeric assemblies. Membrane proteins, IDRs, ribosomes, and capsids may need additional view types.
- Substitute for fetching authoritative annotations from databases (M-CSA mechanism, UniProt features, PDBe-KB conservation). That is the MCP layer's job — see Out of Scope.

---

## Out of Scope for This Plan

**Phase originally labeled "MCP server (`structure-databases`)"** — Biotite-backed wrappers for RCSB / UniProt / AlphaFold + custom clients for M-CSA / PDBe-KB / RCSB Data API.

Skipped here per scope decision: storage cost (cached structure files accumulate), additional dependency surface (httpx, biotite, server runtime), and not strictly required for v1 — the skill works on any PDB ID by fetching directly via gemmi at run time. The MCP becomes valuable later when annotation enrichment (mechanism, conservation, family) is the bottleneck. Revisit after the skill v1 is in use and we can see whether annotation enrichment actually changes outcomes on the eval set.

---

## Two Non-Negotiables

1. **Inspection logic lives in `decision_tree.yaml`, not in Claude's head.** If the same protein gets different analyses across runs, that's a bug. Adding a rule beats writing a longer prompt. — ✅ holds.
2. **Eval before submission.** `evals/results.md` must be in the repo, with reproducible numbers, before either marketplace submission. Without it, the contribution is decoration. — ✅ done; `evals/results.md` is present with a 29-protein × 4-condition table. The headline claim has been updated to match what the numbers actually show.

---

## Total Estimate

- Phase 0: 0.5 day
- Phase 1: 3–5 days
- Phase 2: 2 days
- Phase 3: 1 day

**~1.5 weeks of focused work** for a v1 worth submitting to both self-published and official marketplaces.

---

## Versioning Roadmap (post-v1)

**v1** — deposited proteins. CATH via PDBe SIFTS (~95% of PDB) + length heuristic fallback. Optional Merizo plumbed but off by default. **Current ship target.**

**v2** — de novo designed proteins (RFdiffusion / Boltz / Chai outputs). Merizo becomes the default domain detector for non-PDB-ID inputs (local files), since CATH won't have entries for designs. Other detectors may gain design-aware variants. Merizo is the priority because accurate domain boundaries matter for analyzing designs.

**v3** — protein design quality metrics: clash detection, packing scores, designability (ProteinMPNN consistency, AF-confidence-on-design comparisons), Rosetta energy, etc. Explicitly out of scope for v1 and v2.

These are clean version boundaries — adding v2 features to v1 risks scope creep, and design-quality metrics (v3) are a different problem space than structure inspection.

## First Concrete Step

Lock the schemas before writing code. Order:
1. Finalize `summary.yaml` schema (the LLM-facing contract)
2. Finalize `decision_tree.yaml` initial rule set (covers ~80% of the structures in the eval set)
3. Finalize `view_battery.yaml` (the 6 standard views above)
4. THEN start Phase 1 implementation
