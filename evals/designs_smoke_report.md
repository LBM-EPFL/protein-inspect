# Designed-protein smoke test (no-annotation pathway)

**Goal**: confirm `protein-inspect` produces a meaningful `summary.yaml` + complete PyMOL view battery on de novo designed proteins where there is **no literature, no UniProt, no functional annotation** to lean on. The decision-tree-codified structural reasoning has to carry the whole interpretation.

**Sources tested**:

1. **ModelArchive** (modelarchive.org) — the primary requested source. The catalog is dominated by AlphaFold predictions of natural proteins, and de novo designs are extremely rare: a full sweep of all 1220 post-2023 entries' procedures + abstract fields turned up only **5 entries** with design-tool keywords (RFdiffusion, ProteinMPNN, hallucination, "de novo design"). The molstar-viewer-style URL `https://modelarchive.org/doi/10.5452/<id>.cif` proved to be the working download path (the canonical `/depositions/...` path returns the React SPA shell). Three entries were verified as actual designs and tested.
2. **PDB post-cutoff de novo designs** — RCSB has 58 entries released after 2026-02-01 explicitly tagged "de novo designed". Five were chosen for diversity (different oligomer states, ligand classes, secondary structure, experimental method).

**Method**: each CIF was run through

```bash
python -m protein_inspect.cli /path/to/<id>.cif --no-narrative --render-views --out /tmp/<id>
```

`--no-narrative` skips the RCSB title fetch, so `summary.yaml`'s `narrative` is null — simulating a deposition with zero literature context.

## Results table — what the pipeline produced (after fixes)

### ModelArchive de novo designs

| ID | Title (suppressed in YAML) | Length | Method | Views | Key YAML signal |
|---|---|---|---|---|---|
| **ma-rgcer** | De novo designed coiled-coil with diversified heptad repeats | 83 aa | (no resolution → AF-like) | 4 | 1-chain monomer, 94% helix; correctly classified as computed model + `plddt_stats`; `plddt_not_bfactor` rule fires; `no_narrative` rule fires. |
| **ma-0qerv** | DEDid/FADD model | 82 aa | (computed) | 5 | 2-chain hetero-dimer, 96% helix; `plddt_stats`; both `plddt_not_bfactor` and `no_narrative` flags fire. |
| **ma-q5t03** | DEDid/procaspase-8 DED1 model | 88 aa | (computed) | 5 | Same pattern as ma-0qerv. |

### PDB post-cutoff de novo designs

| PDB | Title (suppressed in YAML) | Length | Method | Views | Key YAML signal |
|---|---|---|---|---|---|
| **9V4L** | De novo designed Zn-binding protein ZK2 | 70 aa | X-ray | 5 | 1-chain monomer, 98.5% helix; `metals: ZN coordinating ASP11/ASP45/HIS54/HIS7 → context: catalytic_likely`; `asp_dyad` pattern at ASP11/ASP45 (3.06 Å). Rules fired: `metals_present`, `aspartate_dyad_geometry` (geometric_only), `no_narrative`. |
| **9V39** | De novo designed serotonin binder SROb2_30 | 116 aa | X-ray | 7 | Dimer, 98% helix; ligand **SRO (serotonin)** correctly flagged as `bio_ligand`, **EPE (HEPES)** correctly flagged as buffer; **aromatic cage** detected at TYR84/TYR91/PHE113 — exactly the serotonin binding pocket. |
| **9R7K** | De novo designed enzyme for Morita-Baylis-Hillman, MBH61 | 206 aa | X-ray | 6 | Tetramer, 96% helix; no ligand or active-site pattern. Membrane false positive **resolved by fix #1**. |
| **29SB** | Solution structure of inhibitor (6-NBT)-bound Kemp eliminase KABLE2.5 | 126 aa | NMR | 5 | Monomer, 99% helix; **6NT (the 6-NBT inhibitor) correctly flagged as bio_ligand**. NMR-as-AF misclassification **resolved by fix #2** (`is_computed: False`). |
| **9R2B** | De novo-designed α-helical barrel | 177 aa | X-ray | 9 | Dimer, 98% helix; Mg correctly flagged as `structural_likely`; **P6G now correctly classified as cryoprotectant** (fix #3); membrane false positive **resolved by fix #1**. |

## Answer to the user's question

**The structural-only pathway is robust.** With `narrative: null` and zero literature input:

1. **Provenance, assembly, fold, SS, B-factors / pLDDT** all populate from coordinates alone.
2. **Metals, ligands, disulfides, aromatic cages, asp dyads, P-loops** are detected from geometry. The Zn-coordination case (9V4L) and the serotonin-aromatic-cage case (9V39) are particularly clean — the YAML carries enough to reconstruct the binding chemistry without any external annotation.
3. **AF/computed models are correctly distinguished from deposited structures** — `is_computed: true` triggers `plddt_stats` (not `bfactor_stats`) and the `plddt_not_bfactor` rule that teaches Claude the inversion ("high pLDDT ≠ flexible").
4. **The `no_narrative` rule fires** on every test case and explicitly tells Claude: *"Functional-class statements must be flagged as inference and grounded in structural features only."*
5. **Every flag carries `evidence_quality: geometric_only` or `confirmed`** so a downstream reader can distinguish a high-confidence observation from a guess.
6. **The view battery rendered 4–9 views per design** including ligand pockets, metal closeups, B-factor/pLDDT maps, surface, and overviews. PyMOL handles designs identically to deposited proteins.

## Bugs caught and fixed in this round

### Fix #1 — `membrane_likely` false positives on soluble α-bundles ✅ done

The original heuristic A fired on any single 22-residue window at >55% hydrophobic (using a broad set including alanine). This caught soluble enzymes throughout the v1 set (1adc, 1ajs, 1tim, 4hhb, 1hsg, …) and designed all-α bundles (9R7K, 9R2B).

**Fix** (`features.py:extract_membrane_features`):
- Require **≥3 distinct hydrophobic stretches** of ≥18 residues each (or ≥2 stretches when the assembly has ≥3 chains, to preserve KcsA-like 2-TM/chain tetramers).
- Use a **strict hydrophobic set** that excludes alanine (I/L/V/F/M/W/P only). Baker-style designed proteins are alanine-dense by construction — using the broad set was scoring designed alanine helices as TM-like. Real TM helices use I/L/V/F/M as their hydrophobic match to the bilayer.
- Threshold 55% strict-hydrophobic per window.

**Validation (23 entries, 0 errors):**
- 7/7 real membrane proteins (KcsA 1bl8, bacteriorhodopsin 1c3w, β2AR 2rh1, OmpF 2omf, VAChT 9KKN, B1R 9LFC, ZnuBC 9OKQ) still trip the flag.
- 11/11 soluble enzymes/proteins (1adc, 1ajs, 1aon, 1asy, 1atp, 1tim, 4hhb, 1hsg, 1nr0, 1ubq, 1mbn) no longer trip.
- 5/5 designs (the table above) no longer trip falsely.

### Fix #2 — NMR structures misclassified as computed models ✅ done

`extract_model_type` flagged `is_computed: true` when (resolution=None AND B-factor range in [0,100]). NMR ensembles satisfy both conditions because (a) NMR doesn't report a resolution, and (b) the B-factor column carries ensemble RMSD or zero, both in [0,100].

**Fix** (`features.py:extract_model_type`): also require `method` to NOT contain "NMR", "EPR", "FIBER", or "NEUTRON". The mmCIF `exptl.method` field is unambiguous.

**Validation**: 29SB (NMR Kemp eliminase) now reports `is_computed: False`, `confidence_metric: bfactor`, `method: SOLUTION NMR`.

### Fix #3 — PEG/glycol additives misclassified as bio_ligand ✅ done

P6G (hexaethylene glycol, a common PEG-fraction crystallization additive) was tagged as `bio_ligand` because it wasn't in `ligand_classes.yaml`'s cryoprotectant list.

**Fix**: extended `ligand_classes.yaml` with the missing PEG CCD codes (P6G, PE6, PE7, 6PG, 8PG, M2M).

**Validation**: 9R2B now correctly emits `ligands.cryoprotectant: [P6G]` with bio_ligand list empty.

## Confirmation

- 148/148 unit tests still pass after all three fixes.
- All 5 PDB designs + all 3 ModelArchive designs produce meaningful YAML and complete view batteries with `--no-narrative`.
- Every false positive originally observed in the first smoke test is eliminated, with no new false positives introduced on the v1 reference set.

## Implications for shipping

This is now clean evidence for the README's "works on designed / unannotated proteins" claim:

- **Coordinate-derived signal** (metals, geometric patterns, aromatic cages, disulfides, SS, B-factor / pLDDT) populates the YAML correctly even when there is zero text annotation.
- **The `no_narrative` flag** explicitly cues Claude to mark functional inference appropriately.
- **The view battery renders identically** on designs as on deposited proteins.
- **AF vs experimental detection** correctly handles the post-cutoff design ecosystem (X-ray crystal structures of designs, NMR solution structures, and AlphaFold-deposited ModelArchive designs).

The next eval-relevant step would be running the full A/B/C/D eval rubric on a small designed-protein set to measure whether materials provide lift on this class — the smoke test only confirms the pipeline produces correct output, not whether Claude's reasoning improves from it.
