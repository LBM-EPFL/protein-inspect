# protein-inspect

A Claude Code plugin that turns any PDB ID or structure file into a layered semantic representation Claude can reason over fluently.

## What it does

Combines three things:

1. **Standardized feature extraction** (gemmi + biotite + DSSP) — chains, secondary structure, B-factor stats, disulfides, ligand binding residues, interface contacts, oligomeric state.
2. **A codified decision tree** of structural-biology inspection rules — "if vicinal disulfide → flag as Cys-loop family marker", "if asymmetric ligand occupancy in symmetric oligomer → flag", etc.
3. **A canonical PyMOL view battery** — top, side, B-factor, surface, ligand pocket, vicinal disulfide zoom. Same six views every time.

Output is `summary.yaml` + a small set of standardized PNGs. Coordinates stay on disk; the LLM-facing layer is text and images only.

## Why

Raw PDB/mmCIF coordinates are bad for LLM reasoning (token economics, fixed-column formatting, no metric closeness in tokens). This plugin produces ~10× denser per-token information by operating at the residue/motif level and externalizing coordinates.

## Quick start

```bash
# install (when published)
/plugin marketplace add USER/protein-inspect
/plugin install protein-inspect

# usage
protein-inspect 2zju --render-views
```

See `PLAN.md` for the full architectural plan and `skills/protein-inspect/SKILL.md` for usage details.

## Status

v0.1 — under active development. See `PLAN.md` for phases.

## License

MIT
