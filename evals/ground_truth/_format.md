# Ground-truth file format

One YAML file per PDB entry. The rubric (see EVAL.md §Rubric) maps directly
onto these fields. The judge reads this file alongside Claude's response
under each condition and scores.

## Schema

```yaml
pdb: <4-letter id>
short_name: <one-line tag — used in the report table>
description: |
  One short paragraph an expert structural biologist would write to introduce
  this structure. Used by the judge as canonical reference text.

# All categories below score 0 unless a positive match is found.
# Inside each category, `must_mention` / `acceptable` give the judge string
# patterns to look for (case-insensitive substring or regex).

identity:
  must_mention_one_of: [...]      # 2 pts
  reference_phrase: "..."          # human-readable canonical statement

oligomeric_state:
  correct: <monomer|dimer|...|heterotetramer|hexamer|higher>    # 1 pt
  acceptable: [list of strings the response can use]
  symmetry: <C2|C5|D2|null>
  required_caveat: <optional>
  # When the PDB asymmetric unit differs from the biological assembly
  # (common for membrane proteins, viral proteases, etc.), set
  # required_caveat to a short sentence that the response MUST
  # acknowledge — usually pointing out the ASU-vs-bio-assembly distinction.
  # If present, the judge gives the oligomer point ONLY if the response
  # makes the required distinction.

fold_class:                       # 2 pts
  must_mention_one_of: [list of fold-class names — Ig fold, TIM barrel, Rossmann, β-grasp, etc.]

active_site:                      # 3 pts — strongest signal of skill value
  type: <triad|dyad|metal-coord|metal-assisted|none>
  # metal-coord  = the metal IS the catalytic moiety (Zn-protease, carbonic
  #                anhydrase, alcohol-dehydrogenase catalytic Zn)
  # metal-assisted = metal positions/stabilizes substrate but chemistry is
  #                done by surrounding residues (kinases, aspRS, polymerases)
  # none         = covers non-canonical cases (e.g. RNase A His-pair); pair
  #                with mechanism_note for clarity
  mechanism_note: "(optional) free-text note clarifying non-textbook cases or
    mechanisms that don't fit the type enum cleanly"
  catalytic_residues:
    - {name: <SER195>, role: <nucleophile|base|acid|metal-coord|...>}
    - ...
  mechanism_class: <hydrolase|oxidoreductase|isomerase|none|...>
  location: <intra-subunit|inter-subunit|pocket|surface>

cofactors_metals_ligands:         # 2 pts
  expected:
    - {id: <CCD>, chemistry_class: <redox_heme|redox_2e|...>}
    - ...
  bio_ligand: <name of natural ligand or inhibitor, if applicable>

notable_features:                 # 2 pts — family-defining motifs
  must_mention_one_of:
    - "vicinal disulfide"
    - "iron-sulfur cluster"
    - "Cys-loop"
    - "aromatic cage"
    - "P-loop / Walker A"
    - "..."

negative_constraints:             # -2 pts each if violated
  - "must not claim it is a serine protease"   # example
  - "..."

inference_hygiene:                # 1 pt
  # Only checked for entries with narrative: null in the input (designed /
  # unannotated structures). For deposited structures with a known function,
  # this category scores N/A (1 pt awarded by default).
  required: <true|false>
```

## What "must_mention_one_of" means

A list of acceptable substrings (case-insensitive). If ANY appears in
Claude's response, the category passes. Multiple synonyms allowed —
e.g. for ubiquitin's fold: `["β-grasp", "beta-grasp", "ubiquitin fold"]`.

## What "negative_constraints" means

Hard penalty. If the response makes a forbidden claim, the rubric subtracts
2 points from the total. Up to 4 negative constraints typical per entry.

## Total points

Identity (2) + Oligomer (1) + Fold (2) + Active site (3) + Cofactors (2) +
Notable features (2) + Inference hygiene (1) = **13 possible**.
Negative constraints subtract from this total.
