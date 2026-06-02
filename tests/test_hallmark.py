"""Hallmark: end-to-end feature extraction over 20 diverse proteins.

Each entry has:
  - pdb_id
  - description (short, for the report)
  - expectations (a dict of properties the extractor should pick up)

We don't require *all* expectations to be hit — the report just shows what
matched and what didn't. This is the breadth scan that catches blind spots in
the rule set or detector logic before we build the renderer / decision walker.
"""

import json
import time
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

from protein_inspect import features as F

ROOT = Path(__file__).parent.parent
SCHEMA = json.loads((ROOT / "schema" / "summary.schema.json").read_text())
VALIDATOR = Draft202012Validator(SCHEMA)
RESULTS_DIR = ROOT / "examples" / "hallmark"

# ─────────────────────────────────────────────────────────────────
# 20 diverse PDB entries chosen to exercise different rules / classes
# ─────────────────────────────────────────────────────────────────
HALLMARK = [
    # Single-chain enzymes & small folds
    {"pdb": "1ubq", "desc": "Ubiquitin (small β-grasp monomer)",
     "expect": {"oligomer": "monomer", "macromolecule": "protein_only"}},
    {"pdb": "1mbn", "desc": "Myoglobin (heme monomer)",
     # NOTE: Fe is inside the HEM molecule in 1mbn, not a separate metal record.
     # We expect cofactor_class redox_heme, not a separate FE metal.
     "expect": {"oligomer": "monomer", "cofactor_class": "redox_heme"}},
    {"pdb": "1tim", "desc": "Triosephosphate isomerase (TIM barrel dimer)",
     "expect": {"oligomer": "dimer", "homo_or_hetero": "homo"}},

    # Cys-loop / pentameric
    {"pdb": "2zju", "desc": "Ls-AChBP pentamer + imidacloprid",
     "expect": {"oligomer": "pentamer", "vicinal_disulfide": True,
                "aromatic_cage": True, "bio_ligand": ["IM4"]}},

    # Hetero-oligomers
    {"pdb": "4hhb", "desc": "Hemoglobin α2β2 heterotetramer (heme)",
     "expect": {"oligomer": "tetramer", "homo_or_hetero": "hetero",
                "cofactor_class": "redox_heme"}},

    # Catalytic triad
    {"pdb": "5cha", "desc": "Chymotrypsin (Ser-His-Asp triad, post-cleavage chains)",
     "expect": {"active_site_pattern": "catalytic_triad"}},

    # Cys-His dyad
    {"pdb": "6lu7", "desc": "SARS-CoV-2 main protease (Cys-His dyad, dimer + inhibitor)",
     "expect": {"active_site_pattern": "cys_his_dyad"}},

    # Asp dyad (cross-chain)
    {"pdb": "1hsg", "desc": "HIV-1 protease (Asp25-Asp25' dimer dyad)",
     "expect": {"active_site_pattern": "asp_dyad",
                "homo_or_hetero": "homo", "oligomer": "dimer"}},

    # P-loop / nucleotide binding
    {"pdb": "1atp", "desc": "PKA catalytic subunit (kinase, ATP, divalent metal)",
     # 1atp uses Mn instead of Mg (substituted divalent — common in PKA crystals)
     "expect": {"free_nucleotide": True, "metals": ["MG", "MN"]}},

    # NAD-dependent oxidoreductase
    {"pdb": "1adc", "desc": "Alcohol dehydrogenase (NAD analog PAD, Zn)",
     # 1adc has PAD (1,4,5,6-tetrahydronicotinamide AD analog) — added to cofactor list
     "expect": {"cofactor": ["NAD", "NAI", "NAJ", "PAD"],
                "metals": ["ZN"]}},

    # Iron-sulfur protein
    {"pdb": "1fxd", "desc": "Ferredoxin (4Fe-4S cluster)",
     "expect": {"iron_sulfur": True}},

    # Membrane protein (β-barrel)
    {"pdb": "2omf", "desc": "OmpF porin (β-barrel membrane)",
     "expect": {"membrane_likely": True}},

    # Membrane protein (α-helical TM bundle)
    {"pdb": "1bl8", "desc": "KcsA potassium channel (TM tetramer)",
     "expect": {"oligomer": "tetramer", "membrane_likely": True}},

    # Antibody (multi-chain, glycosylated)
    {"pdb": "1igy", "desc": "IgG immunoglobulin (multi-chain, glycosylated)",
     "expect": {"homo_or_hetero": "hetero", "glycans": True,
                "interchain_disulfide": True}},

    # Protein-DNA
    {"pdb": "1cdw", "desc": "TBP-DNA complex",
     "expect": {"macromolecule": ["protein_dna", "mixed"]}},

    # Protein-RNA
    {"pdb": "1asy", "desc": "Aspartyl-tRNA synthetase + tRNA",
     "expect": {"macromolecule": ["protein_rna", "mixed"]}},

    # Multi-domain / large
    {"pdb": "1aon", "desc": "GroEL chaperonin (large, multi-domain, 14-mer asymmetric unit subset)",
     "expect": {"multi_domain": True}},

    # Pepsin (asp protease, intra-chain dyad)
    {"pdb": "5pep", "desc": "Pepsin (aspartyl protease, intra-chain Asp dyad)",
     "expect": {"active_site_pattern": "asp_dyad"}},

    # Ribonuclease (small, has multiple disulfides)
    {"pdb": "7rsa", "desc": "Ribonuclease A (small, 4 disulfides)",
     "expect": {"oligomer": "monomer", "disulfide_count_min": 3}},

    # GPCR (membrane, 7TM)
    {"pdb": "2rh1", "desc": "β2-adrenergic receptor (GPCR, 7TM)",
     "expect": {"membrane_likely": True}},
]


def _check(summary: dict, key: str, expected, results: list):
    """Check one expectation, append a result tuple."""
    matched = False
    actual = None
    if key == "oligomer":
        actual = summary["assembly"].get("oligomer")
        matched = actual == expected
    elif key == "homo_or_hetero":
        actual = summary["assembly"].get("homo_or_hetero")
        matched = actual == expected
    elif key == "macromolecule":
        actual = summary["macromolecule_type"]
        matched = actual in expected if isinstance(expected, list) else actual == expected
    elif key == "vicinal_disulfide":
        actual = any(d["type"] == "vicinal" for d in summary.get("disulfides", []))
        matched = actual == expected
    elif key == "interchain_disulfide":
        actual = any(d["type"] == "interchain" for d in summary.get("disulfides", []))
        matched = actual == expected
    elif key == "disulfide_count_min":
        actual = len(summary.get("disulfides", []))
        matched = actual >= expected
    elif key == "aromatic_cage":
        # check via ligands.bio_ligand
        actual = any(l.get("aromatic_cage") for l in summary.get("ligands", {}).get("bio_ligand", []))
        # fallback: aromatic_cage_at_ligand_site rule fires through patterns
        if not actual:
            actual = any(p["pattern"] == "aromatic_cage" for p in summary.get("active_site_patterns", []))
        matched = actual == expected
    elif key == "bio_ligand":
        bio_codes = {l["id"] for l in summary.get("ligands", {}).get("bio_ligand", [])}
        actual = list(bio_codes & set(expected)) if isinstance(expected, list) else (expected in bio_codes)
        matched = bool(actual)
    elif key == "metals":
        present = {m["id"] for m in summary.get("metals", [])}
        actual = sorted(present & set(expected))
        matched = len(actual) > 0
    elif key == "iron_sulfur":
        actual = any(m["cluster_type"] in ("FES", "F3S", "SF4", "CFM") for m in summary.get("metals", []))
        matched = actual == expected
    elif key == "cofactor_class":
        actual = {c["chemistry_class"] for c in summary.get("cofactors", [])}
        matched = expected in actual
    elif key == "cofactor":
        present = {c["id"] for c in summary.get("cofactors", [])}
        actual = sorted(present & set(expected))
        matched = bool(actual)
    elif key == "free_nucleotide":
        actual = bool(summary.get("nucleotides_free"))
        matched = actual == expected
    elif key == "glycans":
        actual = bool(summary.get("glycans"))
        matched = actual == expected
    elif key == "active_site_pattern":
        present = {p["pattern"] for p in summary.get("active_site_patterns", [])}
        actual = expected in present
        matched = actual
    elif key == "membrane_likely":
        actual = bool(summary.get("membrane_features", {}).get("belt_detected"))
        matched = actual == expected
    elif key == "multi_domain":
        actual = (summary.get("domains", {}) or {}).get("count", 0) > 1
        matched = actual == expected
    else:
        actual = "UNKNOWN_KEY"

    results.append({"check": key, "expected": expected, "actual": actual, "matched": matched})
    return matched


@pytest.mark.slow
@pytest.mark.parametrize("entry", HALLMARK, ids=lambda e: e["pdb"])
def test_hallmark_entry_validates_and_extracts(entry):
    """Per-entry: extract_all() must succeed, validate against schema, and
    we record which expectations were hit. The test only fails on hard errors
    (extraction crash, schema violation). Mismatched expectations are reported
    but do not fail — they're the data we want to inspect."""
    pdb = entry["pdb"]
    t0 = time.time()
    summary = F.extract_all(pdb)
    elapsed = time.time() - t0

    # Hard requirements
    VALIDATOR.validate(summary)

    # Soft expectations (recorded, not asserted)
    results = []
    for key, expected in entry["expect"].items():
        _check(summary, key, expected, results)

    # Persist per-entry output for inspection
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "pdb": pdb,
        "desc": entry["desc"],
        "elapsed_sec": round(elapsed, 2),
        "checks": results,
        "n_flags_potential": _count_potential_flags(summary),
        "summary_excerpt": _summary_excerpt(summary),
    }
    (RESULTS_DIR / f"{pdb}.json").write_text(json.dumps(payload, indent=2, default=str))


def _count_potential_flags(s: dict) -> dict:
    """For a quick visual sanity, count how many decision-tree rules WOULD fire."""
    return {
        "is_computed": s["model_quality"]["is_computed"],
        "n_chains": s["assembly"]["n_chains"],
        "homo_or_hetero": s["assembly"]["homo_or_hetero"],
        "n_bio_ligands": len(s.get("ligands", {}).get("bio_ligand", []) or []),
        "n_artifacts": sum(len(v) for k, v in s.get("ligands", {}).items() if k != "bio_ligand"),
        "n_metals": len(s.get("metals", []) or []),
        "n_cofactors": len(s.get("cofactors", []) or []),
        "n_disulfides": len(s.get("disulfides", []) or []),
        "n_active_site_patterns": len(s.get("active_site_patterns", []) or []),
        "membrane_likely": (s.get("membrane_features") or {}).get("belt_detected", False),
        "macromolecule_type": s["macromolecule_type"],
    }


def _summary_excerpt(s: dict) -> dict:
    """A small slice of the summary for the per-entry JSON."""
    out = {
        "macromolecule_type": s["macromolecule_type"],
        "assembly": {k: s["assembly"].get(k) for k in ("n_chains", "oligomer", "homo_or_hetero", "symmetry", "unique_sequences")},
        "fold": {"length": s["fold"]["length"], "ss_fractions": s["fold"]["ss_fractions"]},
        "n_metals": len(s.get("metals", []) or []),
        "metals": [m["id"] for m in s.get("metals", []) or []],
        "n_cofactors": len(s.get("cofactors", []) or []),
        "cofactors": [(c["id"], c["chemistry_class"]) for c in s.get("cofactors", []) or []],
        "disulfide_types": [d["type"] for d in s.get("disulfides", []) or []],
        "active_site_patterns": [p["pattern"] for p in s.get("active_site_patterns", []) or []],
        "bio_ligands": [l["id"] for l in s.get("ligands", {}).get("bio_ligand", []) or []],
        "artifacts": {k: [x["id"] for x in v] for k, v in s.get("ligands", {}).items() if k != "bio_ligand"},
        "membrane_likely": (s.get("membrane_features") or {}).get("belt_detected", False),
    }
    return out


def test_hallmark_summary_report():
    """Aggregate the per-entry results into a single report.md after all entries run."""
    if not RESULTS_DIR.exists():
        pytest.skip("Per-entry results not yet generated; run hallmark tests first.")
    entries = sorted(RESULTS_DIR.glob("*.json"))
    if len(entries) < len(HALLMARK):
        pytest.skip(f"Only {len(entries)}/{len(HALLMARK)} per-entry results — run hallmark tests first.")

    lines = ["# Hallmark Report — protein-inspect feature extraction\n"]
    lines.append(f"Run on {len(entries)} structures.\n\n")
    lines.append("| PDB | Description | All checks matched? | Time (s) |\n")
    lines.append("|-----|-------------|---------------------|----------|\n")

    total_checks = 0
    total_matched = 0
    for f in entries:
        d = json.loads(f.read_text())
        passed = sum(1 for c in d["checks"] if c["matched"])
        all_p = passed == len(d["checks"])
        total_checks += len(d["checks"])
        total_matched += passed
        lines.append(f"| {d['pdb']} | {d['desc']} | {passed}/{len(d['checks'])} {'✓' if all_p else '✗'} | {d['elapsed_sec']} |\n")

    lines.append(f"\n**Overall: {total_matched}/{total_checks} expectations matched ({100*total_matched/total_checks:.0f}%)**\n\n")

    # Per-entry detail
    lines.append("## Per-entry detail\n\n")
    for f in entries:
        d = json.loads(f.read_text())
        lines.append(f"### {d['pdb']} — {d['desc']}\n")
        for c in d["checks"]:
            mark = "✓" if c["matched"] else "✗"
            lines.append(f"- {mark} `{c['check']}` expected `{c['expected']}` → got `{c['actual']}`\n")
        lines.append(f"- summary excerpt: `{d['summary_excerpt']}`\n\n")

    (ROOT / "examples" / "hallmark_report.md").write_text("".join(lines))
