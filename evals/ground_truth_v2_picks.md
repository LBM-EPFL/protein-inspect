# Holdout set v2 — 20 PDB picks

All entries released on or after **2026-02-01**, postdating Claude Opus 4.7's knowledge cutoff (January 2026). The set is intended to be the canonical headline number for `protein-inspect`: Claude can't have memorized any of these, so D-condition scores reflect zero prior knowledge and the lift from A / B / C measures the materials' actual contribution.

Discovery: `evals/discover_holdouts.py` → `evals/holdout_candidates.json` (150 candidates).

## Picks (20)

### 5 monomers — enzymes & transporters
| PDB | Method | Res | Title | Why |
|---|---|---|---|---|
| 9LRN | X-ray | 2.5 Å | PDE2A with inhibitor 13t | Phosphodiesterase + drug. Tests `active_site.metal-coord` + ligand pocket reading. |
| 9QNM | X-ray | 1.1 Å | Polyester Hydrolase Leipzig 7 (PHL7) variant R2M2 | α/β hydrolase, Ser-His-Asp triad. Hot topic (PET-degrading enzymes). Atomic resolution. |
| 9KKN | cryo-EM | 2.7 Å | Human VAChT in complex with ACh | Membrane transporter + neurotransmitter. Tests membrane fold + classical substrate. |
| 21NQ | cryo-EM | 2.8 Å | Human SLC37A4-apo | Sugar phosphate transporter, **apo state** — tests the "no ligand fabrication" negative-constraint path. |
| 22HH | X-ray | 1.5 Å | β-1,2-glucan-binding protein with linear β-1,2-glucan | Carbohydrate-binding domain. Tests glycan-recognition fold + non-catalytic binding site. |

### 5 dimers — drug targets & enzymes
| PDB | Method | Res | Title | Why |
|---|---|---|---|---|
| 9LZM | X-ray | 1.9 Å | SARS-CoV-2 main protease + Pomotrelvir | Cysteine protease dyad (Cys145-His41) + new covalent inhibitor. Tests Cys-His chemistry. |
| 28WL | X-ray | 1.6 Å | Human MAO B + inhibitor | Flavin-dependent oxidase. Tests FAD cofactor recognition + drug pocket. |
| 9HZ3 | X-ray | 1.4 Å | PCSK9 + AZD0780 | Cardiovascular drug target, atomic-resolution co-crystal. Tests serine-protease-fold + non-catalytic prodomain. |
| 24HR | X-ray | 2.1 Å | Human KRAS G12D + macrocyclic peptide AP6252 | Oncogene, "undruggable" GTPase + peptide drug. Tests P-loop + nucleotide pocket. |
| 9LFC | cryo-EM | 3.6 Å | Human bradykinin receptor B1R + antagonist R715 | GPCR — 7TM fold + antagonist. Tests membrane-protein fold recognition. |

### 3 trimers — viral glycoproteins & toxins
| PDB | Method | Res | Title | Why |
|---|---|---|---|---|
| 9LVI | cryo-EM | 2.9 Å | SARS-CoV-2 spike | Class I viral fusion, prefusion trimer. Tests glycoprotein recognition (no co-crystal). |
| 9OVL | cryo-EM | 1.7 Å | HCoV-OC43 spike + 9-O-acetyl GD3 sialoglycan | Different coronavirus, **with ligand** — sialic-acid recognition. Tests glycan binding + viral fusion. |
| 25PV | cryo-EM | 3.0 Å | Anthrax protective antigen + neutralizing Ab | Bacterial toxin, AB-toxin architecture, antibody-bound. Tests toxin + Fab complex reading. |

### 3 tetramers / larger oligomers
| PDB | Method | Res | Title | Why |
|---|---|---|---|---|
| 9OKQ | cryo-EM | 2.9 Å | E. coli ZnuB-ZnuC ABC transporter, wild-type | Heteromeric ABC transporter, zinc importer. Tests heterodimer of dimers + metal substrate. |
| 9OHN | cryo-EM | 2.5 Å | Human p97/VCP + inhibitor GND-135 | AAA+ ATPase hexamer (modeled as 12-mer in the assembly). Tests ATP-binding fold + ring assembly. |
| 9OII | cryo-EM | 3.2 Å | Type III ABri amyloid filaments from familial British dementia brain | Amyloid fibril (15-meric stack of cross-β protofilaments). Tests filament/repeat recognition + disease context. |

### 3 complexes / machinery
| PDB | Method | Res | Title | Why |
|---|---|---|---|---|
| 25HN | cryo-EM | 2.3 Å | Native Rubisco from Nitrosospira multiformis | Form III rubisco (hexadecameric). Tests classic enzyme fold + climate-relevant context. |
| 9QEB | cryo-EM | 2.3 Å | RNA polymerase II elongation complex | Massive protein/NA machine. Tests Pol II fold + DNA/RNA recognition + ligand-free complex. |
| 9NI8 | cryo-EM | 3.2 Å | PI3K α / KRas complex on POPC/POPS nanodiscs | Cancer signaling complex + lipid bilayer mimetic. Tests lipid-context + heterodimer. |

### 1 designed / synthetic biology
| PDB | Method | Res | Title | Why |
|---|---|---|---|---|
| 9N97 | X-ray | 1.4 Å | Cysteine-free anti-UTag intrabody | Designed binder, engineered scaffold. Tests designed-protein analysis path (paired with `1qys` / `5l33` in v1). |

## Coverage check against rubric

- **identity**: All 20 have clear titles → must-mention phrases are derivable.
- **oligomer**: 5 monomer / 6 dimer / 3 trimer / 3 tetramer / 3 larger. Full range.
- **fold_class**: Enzymes (hydrolase, oxidase, GTPase, AAA+, Pol II), receptors (GPCR), transporters (ABC, MFS), viral fusion (class I), antibody, designed scaffold, amyloid. Covers all major fold families.
- **active_site**: Dyad (Mpro), triad-style (PHL7), metal-coord (PDE2A, ZnuBC), nucleotide-binding (KRAS, p97), none (transporters, glycan binders, designed scaffold, spike). Mix.
- **cofactors_metals_ligands**: FAD (MAO B), ATP/ADP (p97, ZnuBC), Zn (ZnuBC), GDP (KRAS), drugs (×7), substrates (ACh, glucan, sialoglycan), apo (SLC37A4, possibly designed). Mix.
- **notable_features**: Cys-His dyad, Ser-His-Asp triad, AAA+ ring, cross-β fibril, 7TM bundle, P-loop, β-1,2-glucan binding cleft, FAD-binding domain. Diverse.
- **inference_hygiene**: Several entries (PI3K-KRas, ABri filaments, intrabody) reasonably require uncertainty markers when reasoning beyond observed density.

## Notes

- 13 cryo-EM + 7 X-ray. Reflects modern deposition mix.
- Resolution range 1.1 Å (PHL7) to 3.7 Å (TWIK-2 if substituted). All adequate for sidechain reasoning.
- All entries have at least one nonpolymer ligand except 21NQ (apo) and 9LVI (spike, no inhibitor — selected intentionally to test the "no ligand fabrication" path).
- 8-character PDB IDs (10BU, 11RN, etc.) appear in the candidate pool but were not selected for v2 — the 4-character ones in this list are easier to reason about and well-supported by tooling.
