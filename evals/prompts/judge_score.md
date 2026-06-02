You are scoring a structural-biology analysis against ground truth using a fixed rubric. Be strict but fair. Read the ground truth (canonical answer) and the extracted claims (what the response actually said), then assign points per category.

## Rubric (13 points total + negative penalties)

| Category | Max | Pass condition |
|---|---|---|
| identity | 2 | Any phrase in `identity.must_mention_one_of` appears (case-insensitive substring) in the extracted names/aliases or function_description |
| oligomer | 1 | extracted.oligomer.claimed_state matches `oligomeric_state.correct` OR any phrase in `oligomeric_state.acceptable` appears in verbatim claims. **PLUS**: if `oligomeric_state.required_caveat` is set, extracted.oligomer.addresses_asu_vs_biological_distinction MUST be true. If caveat required and missing, score = 0. |
| fold_class | 2 | Any phrase in `fold_class.must_mention_one_of` appears in extracted.fold_class.fold_names_mentioned (case-insensitive substring match) |
| active_site | 3 | All three sub-criteria: (a) extracted.active_site.site_type_claimed matches `active_site.type` OR mechanism_note context (b) at least one residue in extracted.active_site.residues_named matches a residue in `active_site.catalytic_residues` (compare by name+number) (c) extracted.active_site.mechanism_class matches `active_site.mechanism_class`. Partial: 1 pt per sub-criterion met. If `active_site.type` is "none" and extracted.active_site claims no enzyme/no catalytic residues, full 3 pts. |
| cofactors_metals_ligands | 2 | At least one CCD code OR its common name from `cofactors_metals_ligands.expected` appears in extracted (e.g. "HEM" or "heme" both count; "FAD" or "flavin"; "NAD" or "nicotinamide"; "PLP" or "pyridoxal"). If ground truth expected is empty `[]` AND the response doesn't fabricate cofactors, give full 2 pts. |
| notable_features | 2 | Any phrase in `notable_features.must_mention_one_of` appears in extracted (case-insensitive substring) |
| inference_hygiene | 1 | If `inference_hygiene.required` is true: 1 pt only if extracted.inferences_marked_as_inference is true. If `inference_hygiene.required` is false: 1 pt automatic. |

## Negative constraints

For EACH phrase in `negative_constraints`, check whether the response's verbatim_claims_used violates it. A violation = **−2 points** (subtracted from total). If you're not sure whether a constraint is violated, default to NO violation (be charitable).

## Output format — JSON only, no prose

```json
{
  "scores": {
    "identity":              {"pts": 0-2, "rationale": "one short sentence"},
    "oligomer":              {"pts": 0-1, "rationale": "..."},
    "fold_class":            {"pts": 0-2, "rationale": "..."},
    "active_site":           {"pts": 0-3, "rationale": "..."},
    "cofactors_metals_ligands": {"pts": 0-2, "rationale": "..."},
    "notable_features":      {"pts": 0-2, "rationale": "..."},
    "inference_hygiene":     {"pts": 0-1, "rationale": "..."}
  },
  "negative_violations": [
    {"constraint": "must not call it a kinase", "evidence": "verbatim claim from response", "penalty": -2}
  ],
  "raw_total": 0,
  "penalty_total": 0,
  "final_score": 0
}
```

`raw_total` = sum of `scores.*.pts`. `penalty_total` = sum of `negative_violations.*.penalty` (negative number). `final_score` = `raw_total + penalty_total`.

## Inputs

Ground truth:
```yaml
{ground_truth_yaml}
```

Extracted claims:
```json
{extracted_json}
```

Verbatim text from the response (for negative-constraint checking):
<<<
{response}
>>>

Output JSON only.
