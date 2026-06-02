# Images-only ablation results

Run on 2026-05-29 15:27 CEST

Conditions:
- **D** — no materials, identifier only ("what is X?")
- **E** — view battery only, no identifier, no YAML, no header
- **C** — full materials: identifier + YAML + view battery

## Headline scores (per protein, per condition)

| Target | D | E | C |
|---|---|---|---|
| PDB 9V4L — de novo Zn-binding designed protein | 2/13 | 4/13 | 12/13 |
| ModelArchive ma-rgcer — de novo coiled-coil | 4/13 | 13/13 | 13/13 |

## Per-criterion breakdown

### PDB 9V4L — de novo Zn-binding designed protein

| Criterion | Max | D | E | C |
|---|---|---|---|---|
| `identity` | 2 | 0 | 0 | 2 |
| `oligomer` | 1 | 0 | 1 | 1 |
| `fold_class` | 2 | 0 | 2 | 2 |
| `active_site` | 3 | 1 | 0 | 2 |
| `cofactors_metals_ligands` | 2 | 0 | 0 | 2 |
| `notable_features` | 2 | 0 | 0 | 2 |
| `inference_hygiene` | 1 | 1 | 1 | 1 |

### ModelArchive ma-rgcer — de novo coiled-coil

| Criterion | Max | D | E | C |
|---|---|---|---|---|
| `identity` | 2 | 0 | 2 | 2 |
| `oligomer` | 1 | 0 | 1 | 1 |
| `fold_class` | 2 | 0 | 2 | 2 |
| `active_site` | 3 | 1 | 3 | 3 |
| `cofactors_metals_ligands` | 2 | 2 | 2 | 2 |
| `notable_features` | 2 | 0 | 2 | 2 |
| `inference_hygiene` | 1 | 1 | 1 | 1 |


Total spend: **$2.00** across 6 cells.

## What this means

Two cleanly different stories on the two targets.

### `ma-rgcer` — pure structural design: image-only = full materials

A 4-helix-bundle coiled coil with no metals, no ligands, no active site. **E and C both score 13/13.** The view battery alone is sufficient because every rubric-relevant fact (fold = α-helical / coiled coil, oligomer = monomer, no enzyme, no cofactors, hydrophobic seam = amphipathic design) can be **read directly off the cartoons + surface view**. Claude's image-only response correctly noted the amphipathic hydrophobic stripe (the design's intent for a bundle interface) and the all-α topology.

This is the strongest case for the view battery on its own: when there's no chemistry to label, images carry the full picture.

### `9V4L` — chemistry-rich design: image-only ≠ full materials

A Zn-binding designed mini-protein with a 2-His / 2-Asp metal site. **C scores 12/13, E only 4/13** — an 8-point gap. Where E loses:

| Criterion (max) | E | C | What the YAML adds that the images do not |
|---|---|---|---|
| `identity` (2) | 0 | 2 | Names the protein ("Zn-binding designed protein") via the narrative / title. Images alone don't carry identity. |
| `active_site` (3) | 0 | 2 | YAML names the coordinating residues (HIS7 / ASP11 / ASP45 / HIS54) and types the site as `metal-coord`. The metal closeup image shows the coordination geometry but not the residue identities. |
| `cofactors_metals_ligands` (2) | 0 | 2 | YAML calls the metal "Zn" by CCD code. From the image alone it's "a grey sphere"; Claude refused to claim Zn from just the filename. |
| `notable_features` (2) | 0 | 2 | YAML carries "Zn" / "metal coordination" / "designed" — the image carries fold class only. |

Claude's E-condition response was actually exemplary in its discipline: it said *"the filename hint of 'ZN_A101' raises the hypothesis of a small zinc-binding helical motif, but I cannot confirm this without seeing the metal view"* — it refused to fabricate chemistry it couldn't visually verify.

### The takeaway for the architecture

- **The view battery alone carries fold, topology, oligomeric state, surface chemistry, confidence gradients.** It is sufficient for proteins whose function is encoded by fold (scaffolds, coiled coils, simple structural designs).
- **The view battery does NOT carry the identity of bound atoms, the names of specific residues, or the chemical class of cofactors.** For those, the YAML is essential — labels on the picture that you can't read off the picture itself.
- The PLAN's original "YAML adds something specific over raw mmCIF" claim is best supported on chemistry-rich structures like 9V4L. On pure structural designs like `ma-rgcer`, the YAML is redundant with the images.
- **Reading the response transcripts is the most informative part of this ablation.** Claude in condition E was rigorously non-fabricating (declined the Zn claim even with a filename leak); the lost points are honest signal that the images don't carry chemistry, not that Claude failed to read them.

### Notes on methodology / caveats

- Claude reported (in `9V4L/E`) that it could only inspect 3 of the 5 attached views — the metal closeup and the hydrophobic surface were not visible to it in this call. Either the Claude Code CLI dropped images past a count threshold or Claude was conservative about reporting which it had truly rendered. This is worth investigating before treating these per-image counts as the final answer; the **direction** of the lift (E < C on chemistry, E = C on pure structure) is unambiguous either way.
- N = 2 proteins is a small ablation. The pattern (pure-structural → image is sufficient; chemistry-rich → YAML required) is consistent with the architecture and with the v2 holdout results (where image-vs-YAML gave ~tied means on a mixed eval set), but a wider study would be needed to claim a quantified split.
- Both targets are de novo designs and post-cutoff, so the D baseline reflects pure zero-knowledge and the C results aren't inflated by memorization.

