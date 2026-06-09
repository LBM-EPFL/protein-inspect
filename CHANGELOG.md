# Changelog

All notable changes to `protein-inspect` are documented here. This project
adheres to [Semantic Versioning](https://semver.org/).

## [0.1.0] — 2026-06-09

First public release.

### Added
- **Feature extraction** (gemmi + biotite) — chains, sequence, secondary
  structure, disulfides, ligand classification (cofactors / metals / glycans /
  nucleotides / cryoprotectants / artifacts), nucleic-acid chains, peptide
  ligands, oligomeric state, interface residues, and B-factor or pLDDT
  statistics depending on whether the input is crystal or computed.
- **Codified decision tree** (`skills/protein-inspect/decision_tree.yaml`) —
  ~35 interpretable rules that fire on extracted features and emit flags with
  evidence-quality and priority tiers.
- **Canonical PyMOL view battery** (`skills/protein-inspect/view_battery.yaml`)
  — 13+ conditionally fired views (overview, B-factor/pLDDT cartoon,
  hydrophobic surface, metal/ligand/cofactor/glycan closeups, nucleic-acid and
  peptide interfaces, vicinal-disulfide zooms), composed into a single labeled
  montage to bypass the Claude Code CLI 3-image attachment cap.
- **`--judge-views`** — optional vision-judged best-of-N render loop. Each PNG
  is scored against a per-view rubric by a Claude vision model; failing views
  are re-rendered with pre-declared `retry_knobs`. Per-view scores and the
  judge's complaints land in `summary.yaml#visual[].judge`. Authenticates via
  `ANTHROPIC_API_KEY` or `ANTHROPIC_AUTH_TOKEN`; clean no-op without
  credentials. See `--judge-model` to pick the judge.
- **Eval harness** (`evals/`) — 5 conditions, 29 v1 breadth PDBs + 19
  post-cutoff v2 holdout PDBs, automated ground-truth verifier, refusal-retry
  chain, and 7-criterion / 13-point scoring. The view-battery condition lifts
  Opus 4.7 from 2.4 → ~12.6 / 13 on structures it cannot have memorized.
- **Claude Code plugin packaging** — `SKILL.md`, plugin + marketplace
  manifests, and a `/protein-inspect` slash command.
- Five worked examples (`examples/`): 1mbn, 2por, 9LZM, 1rva, AF-P00533-F1.
- Test suite: 135 tests (133 passing, 2 network-gated tests skipped offline).
