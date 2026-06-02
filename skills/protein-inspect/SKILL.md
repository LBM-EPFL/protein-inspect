---
name: protein-inspect
description: Use this skill when the user wants to analyze, reason about, or understand a protein structure — given a PDB ID, a local structure file (.pdb/.cif/.bcif), or after running structure prediction. Produces a layered semantic representation (summary.yaml + canonical PyMOL view battery) that Claude reads to identify fold, oligomeric state, ligand binding sites, disulfides, motifs, and notable structural features. Triggers when the user mentions a PDB code, asks "what is this protein", asks about active sites or ligands in a structure, or wants to compare/triage multiple structures. Do not use for sequence-only analysis (use BLAST/HMMER tools), or for binding-affinity / molecular-dynamics calculations.
---

# protein-inspect

Standardized inspection pipeline for protein structures. Combines deterministic feature extraction (gemmi, biotite, DSSP), a codified decision tree of structural-biology heuristics, and a fixed PyMOL view battery. Output is `summary.yaml` plus optional rendered images.

## When to invoke

- User mentions a PDB ID (e.g. "1ubq", "look at 6vxx")
- User passes a structure file path (`.pdb`, `.cif`, `.bcif`)
- User asks "what does this protein look like / do / bind"
- User wants triage across multiple structures (RFdiffusion outputs, AF3 predictions)
- User asks about disulfides, oligomeric state, binding sites, or motifs in a structure

## Usage

```bash
# basic — fetch from PDB and emit summary.yaml only
protein-inspect 1mbn

# with rendered view battery (slower, requires running PyMOL with claudemol plugin)
protein-inspect 1mbn --render-views

# local file
protein-inspect /path/to/design.pdb --render-views

# with named motif for catalysis-focused analysis
protein-inspect 1kxj --motif His153,Asp166,Ser142 --render-views

# output directory
protein-inspect 1mbn --out ./analysis/1mbn/
```

## Output layout

```
<out_dir>/
├── summary.yaml          # the semantic layer Claude reads
├── 1mbn.bcif             # coordinates, externalized
└── views/                # only when --render-views
    ├── 01_top.png
    ├── 02_side.png
    ├── 03_bfactor.png
    ├── 04_surface.png
    ├── 05_pocket_<lig>_<chain>.png
    └── 06_vicinal_ss_<chain>_<a>-<b>.png  # if vicinal disulfide present
```

## How Claude should read the output

After invoking, read `prompts/analyze.md` and follow it. The prompt walks through the YAML and images in a fixed order so that analyses are reproducible across calls.

## Requirements

- PyMOL running with the claudemol socket plugin (port 9880) — only needed for `--render-views`
- Python 3.12+ with deps from `pyproject.toml`

## What this skill does NOT do

- Compute binding affinities (use FEP / MM-GBSA tools)
- Predict structure (use AlphaFold / Boltz / Chai)
- Detect novel spatial features outside the precomputed view battery
- Replace the deposition paper for mechanistic detail (it gives you the structural facts; biological interpretation still comes from literature or an MCP-backed annotation database)
