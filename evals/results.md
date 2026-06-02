# Eval results — `protein-inspect`

## Holdout set — headline

Entries released **after 2026-01-31**, postdating Claude Opus 4.7's training cutoff. The model can't have memorized these structures, so the lift from materials (A / B / C vs the D baseline) reflects the tool's actual contribution rather than recall of famous PDBs.

- **Run directory**: `evals/runs/2026-05-28_1345_nogit`
- **Started**: 2026-05-28T13:45:03.607047+00:00
- **Proteins scored**: 19
- **Subject model**: `claude-opus-4-7` (via `claude -p`)
- **Judge model**: `claude-opus-4-7`
- **Rubric**: 7 criteria, 13 points max, negative-constraint penalties (−2 each)

## Headline: mean score by condition

| Condition | Materials provided | n | Mean | Median | Stdev | Min | Max |
|---|---|---|---|---|---|---|---|
| **A** | raw mmCIF text (truncated at 80 KB) | 19 | **12.79** | 13.00 | 0.54 | 11.00 | 13.00 |
| **B** | protein-inspect `summary.yaml` only | 18 | **12.50** | 13.00 | 0.92 | 10.00 | 13.00 |
| **C** | protein-inspect `summary.yaml` + rendered PyMOL view battery | 18 | **12.56** | 13.00 | 0.86 | 10.00 | 13.00 |
| **D** | no materials — prior knowledge from PDB ID only (baseline) | 19 | **2.42** | 2.00 | 1.71 | 1.00 | 6.00 |

_Score range: 0 to 13 per cell; negative scores are possible when negative constraints are violated._

## Per-criterion mean (out of category max)

| Criterion | Max | A | B | C | D |
|---|---|---|---|---|---|
| `identity` | 2 | 2.00 | 2.00 | 2.00 | 0.00 |
| `oligomer` | 1 | 0.95 | 0.94 | 0.94 | 0.00 |
| `fold_class` | 2 | 2.00 | 1.94 | 2.00 | 0.00 |
| `active_site` | 3 | 2.84 | 2.83 | 2.83 | 0.89 |
| `cofactors_metals_ligands` | 2 | 2.00 | 2.00 | 2.00 | 0.53 |
| `notable_features` | 2 | 2.00 | 2.00 | 2.00 | 0.00 |
| `inference_hygiene` | 1 | 1.00 | 1.00 | 1.00 | 1.00 |
| _negative penalties_ | — | 0.00 | 0.22 | 0.22 | 0.00 |

## Lift from materials (mean Δ vs. baseline D)

Headline lift = mean(condition) − mean(D). Positive = the materials help; negative = the materials hurt (rare, would suggest distraction or hallucination triggered by materials).

| Criterion | A − D | B − D | C − D |
|---|---|---|---|
| `identity` | +2.00 | +2.00 | +2.00 |
| `oligomer` | +0.95 | +0.94 | +0.94 |
| `fold_class` | +2.00 | +1.94 | +2.00 |
| `active_site` | +1.95 | +1.94 | +1.94 |
| `cofactors_metals_ligands` | +1.47 | +1.47 | +1.47 |
| `notable_features` | +2.00 | +2.00 | +2.00 |
| `inference_hygiene` | +0.00 | +0.00 | +0.00 |
| **total** | **+10.37** | **+10.08** | **+10.13** |

## Negative-constraint violations

Counts the number of (pdb, condition) cells where the response triggered at least one ground-truth negative constraint (e.g. "must not call it a kinase"). Lower is better.

| Condition | Cells with ≥1 violation | Total violations |
|---|---|---|
| **A** | 0 | 0 |
| **B** | 2 | 2 |
| **C** | 2 | 2 |
| **D** | 0 | 0 |

## Per-protein final scores

| PDB | A | B | C | D | best |
|---|---|---|---|---|---|
| 21NQ | 13 | 13 | 13 | 4 | **C** |
| 22HH | 13 | 13 | 13 | 4 | **C** |
| 24HR | 13 | 12 | 13 | 1 | **C** |
| 25HN | 13 | 13 | 13 | 1 | **C** |
| 28WL | 13 | 13 | 13 | 1 | **C** |
| 9HZ3 | 13 | 13 | 13 | 1 | **C** |
| 9KKN | 13 | 13 | 13 | 4 | **C** |
| 9LFC | 13 | 13 | 13 | 5 | **C** |
| 9LRN | 12 | 13 | 13 | 1 | **C** |
| 9LVI | 13 | 13 | 13 | 2 | **C** |
| 9LZM | 13 | 13 | 13 | 2 | **C** |
| 9N97 | 13 | 10 | 10 | 6 | **A** |
| 9NI8 | 12 | 11 | 12 | 1 | **C** |
| 9OHN | 11 | 12 | 12 | 1 | **C** |
| 9OII | 13 | 13 | 13 | 5 | **C** |
| 9OKQ | 13 | 13 | 12 | 1 | **B** |
| 9OVL | 13 | — | — | 2 | **A** |
| 9QEB | 13 | 13 | 13 | 1 | **C** |
| 9QNM | 13 | 11 | 11 | 3 | **A** |


---

# Reference: breadth set

## Breadth set — pre-cutoff PDBs (reference, ceiling-limited)

29 well-studied structures, mostly deposited well before the training cutoff. The headline means here are squashed near the rubric ceiling because Claude already knows these proteins from prior knowledge alone. Treat as a *breadth check* (does the tool work on the famous targets?), not a lift measurement. The low-prior-knowledge subset below isolates the entries where the eval still has signal.

- **Run directory**: `evals/runs/2026-05-14_1140_nogit`
- **Started**: 2026-05-14T11:40:11.486825+00:00
- **Proteins scored**: 30
- **Subject model**: `claude-opus-4-7` (via `claude -p`)
- **Judge model**: `claude-opus-4-7`
- **Rubric**: 7 criteria, 13 points max, negative-constraint penalties (−2 each)

## Headline: mean score by condition

| Condition | Materials provided | n | Mean | Median | Stdev | Min | Max |
|---|---|---|---|---|---|---|---|
| **A** | raw mmCIF text (truncated at 80 KB) | 30 | **12.67** | 13.00 | 0.76 | 10.00 | 13.00 |
| **B** | protein-inspect `summary.yaml` only | 30 | **12.40** | 13.00 | 0.89 | 10.00 | 13.00 |
| **C** | protein-inspect `summary.yaml` + rendered PyMOL view battery | 30 | **12.37** | 13.00 | 1.22 | 8.00 | 13.00 |
| **D** | no materials — prior knowledge from PDB ID only (baseline) | 30 | **12.17** | 13.00 | 1.86 | 6.00 | 13.00 |

_Score range: 0 to 13 per cell; negative scores are possible when negative constraints are violated._

## Per-criterion mean (out of category max)

| Criterion | Max | A | B | C | D |
|---|---|---|---|---|---|
| `identity` | 2 | 1.87 | 1.93 | 1.80 | 1.80 |
| `oligomer` | 1 | 0.97 | 0.93 | 0.97 | 0.90 |
| `fold_class` | 2 | 2.00 | 1.93 | 2.00 | 1.87 |
| `active_site` | 3 | 2.83 | 2.60 | 2.67 | 2.80 |
| `cofactors_metals_ligands` | 2 | 2.00 | 2.00 | 2.00 | 2.00 |
| `notable_features` | 2 | 2.00 | 2.00 | 2.00 | 1.87 |
| `inference_hygiene` | 1 | 1.00 | 1.00 | 1.00 | 1.00 |
| _negative penalties_ | — | 0.00 | 0.00 | 0.07 | 0.07 |

## Lift from materials (mean Δ vs. baseline D)

Headline lift = mean(condition) − mean(D). Positive = the materials help; negative = the materials hurt (rare, would suggest distraction or hallucination triggered by materials).

| Criterion | A − D | B − D | C − D |
|---|---|---|---|
| `identity` | +0.07 | +0.13 | +0.00 |
| `oligomer` | +0.07 | +0.03 | +0.07 |
| `fold_class` | +0.13 | +0.07 | +0.13 |
| `active_site` | +0.03 | -0.20 | -0.13 |
| `cofactors_metals_ligands` | +0.00 | +0.00 | +0.00 |
| `notable_features` | +0.13 | +0.13 | +0.13 |
| `inference_hygiene` | +0.00 | +0.00 | +0.00 |
| **total** | **+0.50** | **+0.23** | **+0.20** |

## Negative-constraint violations

Counts the number of (pdb, condition) cells where the response triggered at least one ground-truth negative constraint (e.g. "must not call it a kinase"). Lower is better.

| Condition | Cells with ≥1 violation | Total violations |
|---|---|---|
| **A** | 0 | 0 |
| **B** | 0 | 0 |
| **C** | 1 | 1 |
| **D** | 1 | 1 |

## Per-protein final scores

| PDB | A | B | C | D | best |
|---|---|---|---|---|---|
| 1a9n | 10 | 10 | 10 | 10 | **D** |
| 1adc | 13 | 13 | 13 | 13 | **D** |
| 1ajs | 13 | 13 | 13 | 13 | **D** |
| 1aon | 13 | 11 | 11 | 12 | **A** |
| 1asy | 12 | 11 | 11 | 11 | **A** |
| 1atp | 13 | 13 | 13 | 13 | **D** |
| 1bl8 | 13 | 11 | 13 | 13 | **D** |
| 1c3w | 13 | 13 | 13 | 13 | **D** |
| 1cdw | 13 | 13 | 13 | 13 | **D** |
| 1fxd | 12 | 12 | 12 | 11 | **C** |
| 1hsg | 13 | 13 | 11 | 11 | **B** |
| 1igy | 13 | 13 | 13 | 13 | **D** |
| 1mbn | 13 | 12 | 13 | 13 | **D** |
| 1nr0 | 11 | 13 | 11 | 6 | **B** |
| 1qys | 13 | 13 | 13 | 13 | **D** |
| 1tim | 12 | 13 | 13 | 12 | **C** |
| 1ubq | 13 | 13 | 13 | 13 | **D** |
| 2omf | 13 | 13 | 13 | 13 | **D** |
| 2rh1 | 13 | 13 | 13 | 13 | **D** |
| 2zju | 13 | 13 | 13 | 6 | **C** |
| 3grs | 13 | 12 | 13 | 13 | **D** |
| 4hhb | 13 | 11 | 13 | 13 | **D** |
| 5cha | 13 | 12 | 13 | 13 | **D** |
| 5pep | 13 | 13 | 13 | 13 | **D** |
| 6lu7 | 13 | 13 | 13 | 13 | **D** |
| 6vxx | 13 | 13 | 13 | 13 | **D** |
| 7rsa | 13 | 13 | 13 | 13 | **D** |
| AF-P00558-F1 | 11 | 12 | 11 | 13 | **D** |
| AF-P02769-F1 | 13 | 13 | 13 | 13 | **D** |
| AF-Q9UN36-F1 | 13 | 11 | 8 | 13 | **D** |

## Low-prior-knowledge subset (D < 12)

Where the eval has signal. The full-set means above mostly reflect a ceiling effect: famous PDBs (1ubq, 6lu7, 6vxx, 1tim, …) score near 13/13 regardless of materials. This subset isolates the 6 entries where Claude's prior-knowledge baseline (condition D) leaves clear room to improve.

| PDB | A | B | C | D |
|---|---|---|---|---|
| 1a9n | 10 | 10 | 10 | 10 |
| 1asy | 12 | 11 | 11 | 11 |
| 1fxd | 12 | 12 | 12 | 11 |
| 1hsg | 13 | 13 | 11 | 11 |
| 1nr0 | 11 | 13 | 11 | 6 |
| 2zju | 13 | 13 | 13 | 6 |
| **mean** | **11.83** | **12.00** | **11.33** | **9.17** |

- Subset lift **A − D** = +2.67
- Subset lift **B − D** = +2.83
- Subset lift **C − D** = +2.17

## How to read these numbers

- **D (baseline)** asks Claude to reason about a PDB ID with no materials provided. This measures pure prior knowledge — for famous structures (1ubq, 2zju, 6vxx, 6lu7) this is high; for obscure or recent entries it should be low.
- **A (raw mmCIF)** tests whether Claude can extract structural facts from coordinates directly. The architectural premise of the project is that this should be the *worst* performing materials condition.
- **B (`summary.yaml`)** is the layered semantic representation — residues with roles, ligands with SMILES, flagged features.
- **C (`summary.yaml` + view battery)** adds the standardized PyMOL images. The lift from B → C should concentrate in spatial-gestalt criteria (`oligomer`, `fold_class`, and qualitative `notable_features`).

### Findings vs. the PLAN.md hypothesis

The PLAN.md prediction was **C > B >> A**, with the A → B gap essentially everything and the B → C gap concentrated in spatial criteria. The full-set means above do not support that ranking: A, B, C, and D all cluster within ~0.5 points. Two structural reasons explain why, and both are signal-relevant:

1. **Ceiling effect from famous PDBs.** The eval set is biased toward well-studied structures (1ubq, 6lu7, 6vxx, 1tim, 4hhb, …). Claude already gets ~13/13 on these from the PDB ID alone — there is no headroom for materials to help. The low-prior-knowledge subset above isolates the cases where the eval *does* have signal.
2. **Judge sees the same prior knowledge.** The judge (also Opus 4.7) reads the response AND has full prior knowledge of the structure. A response that says "this is ubiquitin" satisfies the rubric whether the reasoning came from materials or memorization. To separate the two, the eval would need to either swap to a sealed-knowledge judge or use only PDBs that postdate the model's training cutoff.

Both are real limitations of v1 of the eval. They should be addressed before any stronger headline claim is made in the marketplace README.
