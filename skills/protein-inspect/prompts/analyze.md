# Protein Structure Analysis — Read Prompt (v1.1)

You are reading the output of `protein-inspect`. Your inputs:

- `summary.yaml` — structured facts (the precise quantitative layer, schema v1.1)
- A directory of standardized PyMOL views (the spatial gestalt layer)

## Rules of engagement

1. **Cite or don't claim.** Every quantitative claim must trace to a YAML field — cite as `summary.yaml#path.to.field`. Every spatial claim must trace to an image filename. If neither supports a claim, do not make it.
2. **Don't read numbers off images.** Distances, B-factors, pLDDT — those come from YAML. Images give topology, shape, pocket presence, hydrophobic patch location.
3. **`flags` carry `evidence_quality` AND `priority`.** Address every flag, but weight them differently:
   - `confirmed` flags (S–S distances, CCD codes, chain composition) → treat as fact.
   - `strong` flags (aromatic cage, interface ligand) → treat as fact.
   - `geometric_only` flags (catalytic_triad_geometry, asp_dyad_geometry, cys_his_dyad_geometry, phosphate_binding_loop) → these are PATTERN MATCHES, not proofs. Require fold + cofactor + ligand context to corroborate before accepting the family implication. If those don't agree, explicitly call out the flag as a likely geometric coincidence.
   - `heuristic` flags (membrane_likely, multi_domain_likely) → hypotheses requiring independent support.
   Address each by `rule_id`. Don't skip any.
4. **Respect the ligand triage.** `ligands.bio_ligand` is the only class you should treat as functional. `ligands.buffer/cryoprotectant/detergent/heavy_atom_phasing` are crystallographic artifacts — note their presence in passing but do not assign them functional roles.
5. **Cofactor chemistry, not cofactor family.** A flag of "NAD present" tells you 2-electron redox chemistry. It does NOT tell you "Rossmann-fold oxidoreductase" — many non-Rossmann proteins use NAD. Family hypotheses must combine cofactor + fold + active-site pattern.
6. **`narrative: null` means designed/unannotated.** Mark function statements as inference, not fact.
7. **Computed models** (`model_quality.is_computed: true`) lack metals/cofactors/modified residues. Do not infer absence; assume "not modeled." Treat low-pLDDT regions (<70) as unreliable for residue-level claims.
8. **Image-quality scores when present.** If `summary.yaml#visual[].judge` is populated, the figure was scored 0–5 by a vision judge. Treat scores ≥4 as trustworthy, score 3 as usable with light hedging, and scores ≤2 as a signal *not* to make confident spatial claims from that image — fall back to the YAML or caveat the claim explicitly. The `judge.issues` list tells you exactly what the judge flagged (e.g. "ligand not visible", "labels unreadable"). When `judge` is absent, the image was not scored — fall back to your own visual assessment.

## Output structure

Markdown report with these section headers, in this order. Total length 400–800 words.

### 1. Identity & status
- Use `narrative` and `provenance.source`. State `provenance.resolution_class` and `model_quality.is_computed`.
- If null narrative or computed model: state plainly. The rest of the analysis is structure-derived only.

### 2. Macromolecular composition
- `macromolecule_type` — protein only / protein-DNA / protein-RNA / protein-glycan / mixed.
- If nucleic acids: cite `nucleic_acids` field, inspect `07_protein_na.png`.

### 3. Quaternary structure
- `assembly.oligomer`, `assembly.symmetry`, `assembly.homo_or_hetero`, `assembly.chain_rmsd_max`.
- Confirm topology against `01_top.png` and `02_side.png`.
- If multi-chain: inspect `08_interface_*.png` for residue-level interface.
- Note any asymmetry (e.g. ligand occupancy not matching assembly symmetry).

### 4. Fold & flexibility / confidence
- `fold.ss_fractions` → fold class hint (helical / β-rich / mixed).
- **Deposited structures** (`model_quality.confidence_metric == "bfactor"`): read `fold.bfactor_stats` + `03_bfactor_*.png` for mobile regions. High mean B → more disordered / flexible loops.
- **Computed models** (`model_quality.confidence_metric == "plddt"`): read `fold.plddt_stats` (NOT `bfactor_stats` — it is intentionally absent) + `03_plddt_*.png`. Values are pLDDT 0–100, higher = MORE confident. **High mean pLDDT means a well-predicted model, NOT a flexible one.** Use `fraction_very_low` / `fraction_low` and `model_quality.plddt_summary.low_confidence_regions` to identify regions the model is uncertain about — those are where structural claims should be flagged as inference.
- If `domains.count > 1`: identify domains from `09_domains_*.png` and discuss separately.

### 5. Functional moieties (descriptive)
For each present:
- **Bio-ligands** — chemistry class (aromatic cage → cation-π; hydrophobic → lipid/steroid; charged → phosphate/nucleotide). For each, `05_pocket_*.png`.
- **Metals** — list with coordinating residues. Use `metals[].context` for catalytic-vs-structural heuristic. Inspect `06_metal_*.png`.
- **Cofactors** — list with chemistry class. Do NOT name family from cofactor alone.
- **Iron-sulfur clusters** — flag explicitly (electron-transfer / radical chemistry).
- **Glycosylation / lipids / free nucleotides** — note each, link to functional implication.
- **Crystallographic artifacts** — one sentence acknowledging their presence, no functional discussion.

### 6. Active site & structural features
For each entry in `active_site_patterns`:
- Catalytic triad → cite residues, geometry, candidate roles (hydrolase/transferase). Family inference deferred to section 8.
- Cys-His dyad → cysteine-protease-class mechanism candidates.
- Asp dyad → aspartyl-protease vs glycosidase distinction depends on whether they activate water or substrate.
- Phosphate-binding loop → nucleotide-binding family hint.
- Aromatic cage → cation-π or carbohydrate recognition.

For disulfides: list all, with subtype (standard/vicinal/interchain). Vicinal gets its own paragraph — these are family-defining.

### 7. Decision-tree flags
Address every entry in `flags`, in priority order. Cite `rule_id`. If a flag seems incorrect (e.g., the YAML data contradicts it), say so — flags are heuristics.

### 8. Hypotheses & follow-ups (mark as INFERENCE)
Combining the above, propose:
- (a) Likely functional class — cite the structural evidence (fold + cofactor + active-site pattern + assembly together).
- (b) One mutagenesis or biochemical experiment that would test the inferred mechanism.
- (c) Inhibitor pharmacophore sketch if a binding site is present.

Mark all of section 8 explicitly as inference.

## Failure modes to avoid

- ❌ "This is a P450" because heme is present (heme is in many enzyme classes).
- ❌ "This is a serine protease" because Ser-His-Asp triad is present (lipases, esterases, peptidases, transferases all share this geometry).
- ❌ "This is a Rossmann-fold oxidoreductase" because NAD is present.
- ❌ Discussing glycerol or PEG as a "small-molecule binder."
- ❌ Reading distances off images.
- ❌ Confident family claims for designed/unannotated structures.
- ❌ Skipping flags because they "seem covered" — address each by `rule_id`.
- ❌ Treating low-pLDDT regions of a computed model as if they were resolved.
