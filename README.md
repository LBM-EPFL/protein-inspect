# protein-inspect

A Claude Code plugin that turns any PDB ID, mmCIF/PDB file, or AlphaFold model into a layered semantic representation Claude can reason over fluently — `summary.yaml` describing fold, ligands, cofactors, interfaces, and predicted-confidence regions, plus a labeled grid of PyMOL views composed into a single image.

![montage example](examples/1mbn/montage.png)

*Example: `protein-inspect 1mbn --render-views` — myoglobin with a HEM cofactor closeup, hydrophobic surface, and overview panels.*

## What it does

Three layers wired together:

1. **Feature extraction** (gemmi + biotite) — chains, sequence, secondary structure, disulfides, ligands (classified into cofactors / metals / glycans / nucleotides / cryoprotectants / artifacts via a curated table), nucleic-acid chains, peptide ligands, oligomeric state, interface residues, B-factor or pLDDT statistics depending on whether the input is crystal or computed.
2. **A codified decision tree** (`skills/protein-inspect/decision_tree.yaml`) — small interpretable rules that fire on the extracted features. *"If multi-chain and asymmetric ligand occupancy → flag for inspection."* *"If method == AlphaFold → emit pLDDT bands and warn the LLM not to confuse it with B-factor."* *"If 3 aromatics within 5 Å of a small-molecule ligand → aromatic cage detected (nicotinic-receptor-like)."* Roughly 35 rules at v0.1.
3. **A canonical PyMOL view battery** (`skills/protein-inspect/view_battery.yaml`) — 13+ views fired conditionally: overview top/side, pLDDT or B-factor colored cartoon, hydrophobic surface, metal closeup with coordinating residues + distances, ligand pocket closeup with measured H-bond distances, cofactor closeup, glycan closeup, nucleic-acid interface, peptide-ligand interface, interface views, vicinal-SS zooms. Composed into a single labeled montage to bypass the Claude Code CLI's 3-image attachment cap.

Output: `<entry>/summary.yaml` + `<entry>/views/*.png` + `<entry>/montage.png`. Raw coordinates stay on disk and are referenced by path; the LLM-facing layer is structured text and a single composed image.

## Why

Raw PDB/mmCIF text is hostile to LLM reasoning: token-inefficient, no metric closeness, fixed-column formatting. This plugin produces ~10× denser per-token information by operating at the residue / motif / pocket level and externalizing coordinates to a path the LLM doesn't have to read.

The decision tree is hand-curated structural-biology knowledge — the equivalent of a junior biologist's checklist when first looking at a new structure — encoded in YAML so it's versionable, testable, and inspectable, rather than buried in a model's prior.

## Install

This is a Claude Code plugin. Once published to a marketplace:

```
/plugin marketplace add benedikt.singer/protein-inspect
/plugin install protein-inspect
```

Or for local development:

```bash
git clone https://gitlab.epfl.ch/benedikt.singer/protein-inspect
cd protein-inspect
uv sync
```

### Runtime dependencies

The Python side (`uv sync`) handles gemmi, biotite, pillow, jsonschema, pyyaml. Two extra things for `--render-views`:

- **PyMOL** (open-source build is fine) running with the [claudemol](https://github.com/anthropics/claudemol) socket plugin listening on `127.0.0.1:9880`. Without this, the CLI runs feature extraction and writes `summary.yaml` but skips rendering.
- **Optional**: [Merizo](https://github.com/psipred/Merizo) for ML-based domain segmentation. Install separately; the CLI falls back to a CATH-and-length heuristic if absent.

## Quick start

```bash
# A deposited crystal structure
uv run protein-inspect 2zju --render-views --out 2zju/

# A local file (mmCIF or PDB)
uv run protein-inspect /path/design.cif --render-views --out design/

# An AlphaFold model (downloaded from AF-DB)
uv run protein-inspect AF-P00533-F1.cif --render-views --out egfr/

# Highlight a specific motif
uv run protein-inspect 1kxj --motif His153,Asp166,Ser142 --render-views
```

Outputs land under `<out>/`:

```
<entry>/
├── 2zju.cif              # coords (copied / fetched)
├── summary.yaml          # the LLM-facing semantic layer
├── montage.png           # single labeled grid of all views
└── views/                # individual view PNGs (1200×900)
    ├── 01_top.png
    ├── 02_side.png
    ├── 03_bfactor_chain_A.png
    ├── 04_surface_hydrophobic.png
    ├── 05_pocket_IM4_A.png
    └── ...
```

Then point Claude at it:

```
/protein-inspect Look at summary.yaml and montage.png and tell me what's
in this structure, what its likely function is, and what's noteworthy.
```

## Examples

Five worked examples ship in `examples/`, each chosen to exercise distinct decision-tree rules:

| example | what it demonstrates |
|---|---|
| [`1mbn`](examples/1mbn/)  | myoglobin + HEM — cofactor classification, heme-chemistry tag, hydrophobic surface around the pocket |
| [`2por`](examples/2por/)  | bacterial porin — aspartate dyad geometry, metals, crystallographic-artifact triage |
| [`9LZM`](examples/9LZM/)  | SARS-CoV-2 main protease (post-cutoff PDB) — Cys/His dyad geometry, multi-domain, post-training-cutoff |
| [`1rva`](examples/1rva/)  | EcoRV + DNA — nucleic-acid interface views, phosphate-binding-loop motif |
| [`AF-P00533-F1_EGFR`](examples/AF-P00533-F1_EGFR/) | AlphaFold-DB EGFR — pLDDT-not-bfactor handling, low-pLDDT region flagging, disulfide-rich extracellular domain |

Each directory contains the full pipeline output (`summary.yaml`, `montage.png`, `views/`, source `.cif`). Open the montage in any of them for a quick visual; open the YAML to see what the decision tree extracted.

## Eval framework

The skill ships with its own evaluation harness in `evals/` — 5 conditions (raw mmCIF / YAML only / YAML+views / baseline / images-only), 29 v1 PDBs + 20 post-cutoff v2 PDBs with hand-written ground truth, automated ground-truth verifier, refusal-retry chain, and aggregate scoring against a 7-criterion 13-point rubric. See `EVAL.md` for the methodology.

V2 holdout (post-2024 cutoff) showed condition C (YAML + view battery + montage) lifts model accuracy by ~10 points over the baseline on structures the model can't have memorized. See `evals/results.md`.

## Repo layout

```
src/protein_inspect/           # feature extractor, decision engine, PyMOL runner, CLI
skills/protein-inspect/        # SKILL.md, decision_tree.yaml, view_battery.yaml, ligand_classes.yaml
schema/summary.schema.json     # JSON Schema for summary.yaml
examples/                      # 5 worked examples (above)
evals/                         # evaluation harness + ground-truth sets + results
tests/                         # 148 pytest tests
.claude-plugin/                # plugin.json, marketplace.json
PLAN.md                        # architectural notes, design decisions, open questions
EVAL.md                        # eval methodology
```

## Status

v0.1.0 — actively developed. Test suite: 148/148 green. See `PLAN.md` for open work items.

## License

MIT.

## Acknowledgements

PyMOL access via [claudemol](https://github.com/anthropics/claudemol). Structural parsing by [gemmi](https://gemmi.readthedocs.io/) and [biotite](https://www.biotite-python.org/). Build inspired by the broader Anthropic [skills](https://github.com/anthropics/skills) effort.
