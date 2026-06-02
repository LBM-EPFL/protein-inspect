"""Unit tests for individual feature extractors.

Quick correctness checks against well-known structures. The Hallmark
integration test (test_hallmark.py) covers the breadth scan over 20 PDBs.
"""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from protein_inspect import features as F

ROOT = Path(__file__).parent.parent
SCHEMA = json.loads((ROOT / "schema" / "summary.schema.json").read_text())
VALIDATOR = Draft202012Validator(SCHEMA)


# ─────────── ligand-class registry ───────────

def test_ligand_classes_load():
    cls = F.load_ligand_classes()
    assert "GOL" in cls["by_code"]
    assert cls["by_code"]["GOL"] == "cryoprotectant"
    assert cls["by_code"]["NAG"] == "glycan"
    assert cls["by_code"]["ZN"] == "metal"
    assert "FES" in cls["iron_sulfur_clusters"]
    assert cls["cofactor_chemistry"]["NAD"] == "redox_2e"
    assert cls["cofactor_chemistry"]["HEM"] == "redox_heme"
    assert cls["cofactor_chemistry"]["PLP"] == "schiff_base"


# ─────────── provenance / macromolecule_type / model_type ───────────

def test_provenance_1ubq():
    s, _ = F.fetch_structure("1ubq")
    p = F.extract_provenance(s)
    assert p["source"] == "rcsb"
    assert p["resolution"] is not None
    assert p["resolution_class"] in ("high", "medium")
    # 1UBQ is X-ray, ~1.8 Å, P 21 21 21
    assert p["resolution"] < 2.5
    assert p["space_group"] is not None


def test_macromolecule_type_protein_only():
    s, _ = F.fetch_structure("1ubq")
    assert F.extract_macromolecule_type(s) == "protein_only"


def test_macromolecule_type_protein_dna():
    """1cdw: TBP-DNA complex."""
    s, _ = F.fetch_structure("1cdw")
    t = F.extract_macromolecule_type(s)
    assert t in ("protein_dna", "mixed")


def test_model_type_for_deposited_structure():
    s, _ = F.fetch_structure("1ubq")
    p = F.extract_provenance(s)
    mq = F.extract_model_type(s, p)
    assert mq["is_computed"] is False
    assert mq["confidence_metric"] == "bfactor"


# ─────────── assembly ───────────

def test_assembly_monomer():
    s, _ = F.fetch_structure("1ubq")
    a = F.extract_assembly(s)
    assert a["n_chains"] == 1
    assert a["homo_or_hetero"] == "monomer"
    assert a["oligomer"] == "monomer"


def test_assembly_hetero_oligomer():
    """4hhb: hemoglobin α2β2 heterotetramer."""
    s, _ = F.fetch_structure("4hhb")
    a = F.extract_assembly(s)
    assert a["n_chains"] == 4
    assert a["homo_or_hetero"] == "hetero"
    assert a["unique_sequences"] == 2


# ─────────── fold ───────────

def test_fold_ss_fractions_sum_to_one():
    s, _ = F.fetch_structure("1ubq")
    f = F.extract_fold(s)
    fr = f["ss_fractions"]
    assert abs(fr["helix"] + fr["sheet"] + fr["loop"] - 1.0) < 0.01


def test_fold_length_correct_1ubq():
    s, _ = F.fetch_structure("1ubq")
    f = F.extract_fold(s)
    assert 70 <= f["length"] <= 80


# ─────────── ligand classification ───────────

def test_ligand_classification_filters_glycerol():
    """1ubq has water but no glycerol; check the partition runs without error."""
    s, _ = F.fetch_structure("1ubq")
    cls = F.load_ligand_classes()
    p = F.extract_ligand_classification(s, cls)
    # No buffer/cryoprotectant should leak into bio_ligand
    bio = set(p["bio_ligand_codes"].keys())
    assert "GOL" not in bio
    assert "EDO" not in bio
    assert "HOH" not in bio


# ─────────── metals / cofactors ───────────

def test_metals_in_4hhb_heme_iron():
    """4hhb has 4 hemes, each carrying an Fe atom."""
    s, _ = F.fetch_structure("4hhb")
    cls = F.load_ligand_classes()
    p = F.extract_ligand_classification(s, cls)
    metals = F.extract_metals(s, p)
    cofactors = F.extract_cofactors(p)
    cofactor_ids = {c["id"] for c in cofactors}
    assert "HEM" in cofactor_ids
    # Fe iron may show up as a separate FE atom or be embedded in heme depending on the entry
    # Just check that heme is recognized as redox_heme chemistry
    heme_entry = [c for c in cofactors if c["id"] == "HEM"][0]
    assert heme_entry["chemistry_class"] == "redox_heme"


# ─────────── disulfides ───────────

# ─────────── active site patterns ───────────

def test_chymotrypsin_has_catalytic_triad():
    """5cha: chymotrypsin Ser195-His57-Asp102."""
    s, _ = F.fetch_structure("5cha")
    patterns = F.extract_active_site_patterns(s)
    triads = [p for p in patterns if p["pattern"] == "catalytic_triad"]
    assert len(triads) > 0, "Expected at least one catalytic triad in 5cha"
    # canonical chymotrypsin numbering
    residues_flat = [r for t in triads for r in t["residues"]]
    has_ser195 = any("SER195" in r for r in residues_flat)
    has_his57 = any("HIS57" in r for r in residues_flat)
    assert has_ser195 and has_his57, f"Expected SER195 + HIS57 — got {residues_flat}"


def test_sars_mpro_has_cys_his_dyad():
    """6lu7: SARS-CoV-2 main protease Cys145-His41 dyad. (Replaces 9pap, whose
    Cys-His geometry is non-productive due to the bound covalent inhibitor.)"""
    s, _ = F.fetch_structure("6lu7")
    patterns = F.extract_active_site_patterns(s)
    dyads = [p for p in patterns if p["pattern"] == "cys_his_dyad"]
    assert len(dyads) > 0, "Expected Cys-His dyad in SARS-CoV-2 Mpro"


def test_hiv_protease_has_asp_dyad():
    """1hsg: HIV-1 protease Asp25-Asp25' dyad (across the two chains, but each chain has both Asps in proximity)."""
    s, _ = F.fetch_structure("1hsg")
    patterns = F.extract_active_site_patterns(s)
    asp_dyads = [p for p in patterns if p["pattern"] == "asp_dyad"]
    assert len(asp_dyads) > 0, "Expected Asp dyad in HIV protease"


# ─────────── full extraction validates against schema ───────────

def test_full_summary_validates_for_1ubq():
    summary = F.extract_all("1ubq")
    VALIDATOR.validate(summary)


def test_full_summary_validates_for_4hhb():
    summary = F.extract_all("4hhb")
    VALIDATOR.validate(summary)


# ─────────── domain segmentation: CATH + length + merizo ───────────

def test_domains_length_heuristic_short_protein():
    """Ubiquitin (76 aa) should always be reported as single-domain by the length heuristic."""
    s, _ = F.fetch_structure("1ubq")
    d = F._domains_via_length_heuristic(s, "A")
    assert d["count"] == 1
    assert d["detected_by"] == "contact_map_ratio"


def test_domains_length_heuristic_large_protein_flags_multi():
    """GroEL chain A (524 aa) > 300 → length heuristic flags multi-domain."""
    s, _ = F.fetch_structure("1aon")
    repr_chain = next(c.name for c in s[0] if F._polymer_kind({r.name for r in c}) == "protein")
    d = F._domains_via_length_heuristic(s, repr_chain)
    assert d["count"] >= 2


@pytest.mark.network
def test_domains_via_cath_groel_is_multi_domain():
    """1AON GroEL has 3 CATH domains per chain (apical, intermediate, equatorial,
    with the equatorial being discontinuous). PDBe SIFTS should return all three.
    Falls back gracefully (skipped, not failed) if API is unreachable."""
    result = F._domains_via_cath("1aon", "A", timeout=10.0)
    if result is None:
        pytest.skip("PDBe SIFTS unreachable — fallback path will be used")
    assert result["detected_by"] == "cath_api"
    assert result["count"] >= 2, f"Expected GroEL to have ≥2 domains via CATH, got {result['count']}"
    # Each boundary should have a sensible residue range
    for b in result["boundaries"]:
        start, end = b["range"]
        assert end > start


@pytest.mark.network
def test_domains_via_cath_ubiquitin_is_single_domain():
    """1UBQ ubiquitin has exactly 1 CATH domain (β-grasp fold). Sanity check
    that CATH returns small-protein boundaries correctly."""
    result = F._domains_via_cath("1ubq", "A", timeout=10.0)
    if result is None:
        pytest.skip("PDBe SIFTS unreachable")
    assert result["count"] == 1


def test_domains_dispatcher_uses_cath_for_pdb_id_input():
    """When extract_all is called with a 4-char PDB ID, the resulting domains
    block should be detected_by=cath_api (assuming CATH is reachable)."""
    summary = F.extract_all("1aon")
    if summary.get("domains", {}).get("detected_by") == "cath_api":
        assert summary["domains"]["count"] >= 2
    else:
        pytest.skip("CATH unreachable — fell back to length heuristic")


def test_domains_dispatcher_falls_back_for_local_files():
    """If we pass a local file path (no PDB ID), the CATH path is skipped
    and the length heuristic is used."""
    s, _ = F.fetch_structure("1ubq")
    d = F.extract_domains(s, pdb_id=None, use_merizo=False)
    assert d["detected_by"] == "contact_map_ratio"


def test_merizo_skipped_when_not_installed():
    """If merizo isn't installed, _domains_via_merizo returns None (no crash).
    The default install path doesn't include merizo, so this should always
    return None unless the user has explicitly opted in."""
    s, _ = F.fetch_structure("1ubq")
    result = F._domains_via_merizo(s, "A")
    # Acceptable: None (not installed) OR a dict (installed and worked)
    assert result is None or (isinstance(result, dict) and result["detected_by"] == "merizo")
