You are extracting structured claims from a structural-biology analysis. Read the response below and pull out specific claims by category. Be conservative — only extract what the response actually says, not what it implies.

Output **JSON only, no prose** (no Markdown fences, no commentary):

```json
{
  "identity": {
    "names_or_aliases": ["..."],
    "function_description": "single short sentence summarizing claimed function"
  },
  "oligomer": {
    "claimed_state": "monomer|dimer|trimer|tetramer|pentamer|hexamer|heptamer|octamer|higher_order|heterotetramer|other|unstated",
    "symmetry": "C2|C3|C4|C5|...|D2|...|null",
    "addresses_asu_vs_biological_distinction": true|false
  },
  "fold_class": {
    "fold_names_mentioned": ["β-grasp", "TIM barrel", ...]
  },
  "active_site": {
    "residues_named": ["SER195", "HIS57", ...],
    "mechanism_class": "hydrolase|transferase|oxidoreductase|isomerase|lyase|ligase|none|unstated",
    "site_type_claimed": "triad|dyad|metal-coord|metal-assisted|aromatic-cage|none|other"
  },
  "cofactors_metals_ligands": {
    "ccd_codes_or_names": ["NAD", "FAD", "heme", "Zn", "imidacloprid", ...],
    "chemistry_class_mentions": ["redox", "Schiff base", "methyl donor", ...]
  },
  "notable_features": {
    "features_mentioned": ["vicinal disulfide", "Loop C", "WD40", "P-loop", "DFG motif", ...]
  },
  "inferences_marked_as_inference": true|false,
  "verbatim_claims_used": [
    "short verbatim snippets from the response that support the above extractions, 1-2 per category"
  ]
}
```

Rules:
- If the response doesn't mention a category, use empty list `[]`, empty string `""`, or `"unstated"` as appropriate.
- For `addresses_asu_vs_biological_distinction`: true ONLY if the response explicitly mentions that the asymmetric unit / crystal packing differs from the biological assembly.
- For `inferences_marked_as_inference`: true ONLY if the response uses words like "I infer", "this suggests", "inference", "speculative", "uncertain", or mark a "Hypotheses" section.
- Residue names: normalize to 3-letter-code + number, all caps, no space (SER195, HIS57). If only "Ser" or "the catalytic serine" is mentioned without a number, list as "SER (unnumbered)".

Response to extract:
<<<
{response}
>>>
