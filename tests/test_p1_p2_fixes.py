"""Regression tests for the v1.1 detector tightening (P1) and
evidence_quality propagation (P2). If any of these break, we've
re-introduced the false-positive failure modes the v1 eval caught.

Organized by which v1 eval failure each test guards against.
"""

import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

from protein_inspect import features as F
from protein_inspect.decision import DecisionEngine

ROOT = Path(__file__).parent.parent
SCHEMA = json.loads((ROOT / "schema" / "summary.schema.json").read_text())
VALIDATOR = Draft202012Validator(SCHEMA)


# ──────────────────────────────────────────────────────────────────
# P2: evidence_quality plumbing
# ──────────────────────────────────────────────────────────────────

def test_schema_accepts_evidence_quality():
    """summary.schema.json v1.1 must accept evidence_quality on flags."""
    sample = {
        "entry": "test", "schema_version": "1.1",
        "generated": "2026-05-18T12:00:00Z",
        "macromolecule_type": "protein_only",
        "model_quality": {"is_computed": False, "confidence_metric": "bfactor"},
        "provenance": {"source": "rcsb", "resolution_class": "high"},
        "assembly": {"n_chains": 1, "chains": ["A"], "homo_or_hetero": "monomer"},
        "fold": {"representative_chain": "A", "length": 100,
                 "ss_fractions": {"helix": 0.3, "sheet": 0.3, "loop": 0.4}},
        "flags": [
            {"rule_id": "x", "priority": "high",
             "evidence_quality": "geometric_only", "message": "..."},
        ],
    }
    VALIDATOR.validate(sample)


def test_schema_rejects_unknown_evidence_quality():
    sample = {
        "entry": "test", "schema_version": "1.1",
        "generated": "2026-05-18T12:00:00Z",
        "macromolecule_type": "protein_only",
        "model_quality": {"is_computed": False, "confidence_metric": "bfactor"},
        "provenance": {"source": "rcsb", "resolution_class": "high"},
        "assembly": {"n_chains": 1, "chains": ["A"], "homo_or_hetero": "monomer"},
        "fold": {"representative_chain": "A", "length": 100,
                 "ss_fractions": {"helix": 0.3, "sheet": 0.3, "loop": 0.4}},
        "flags": [{"rule_id": "x", "priority": "high",
                   "evidence_quality": "very_strong",  # not in enum
                   "message": "..."}],
    }
    errors = list(VALIDATOR.iter_errors(sample))
    assert errors, "Schema should reject unknown evidence_quality value"


@pytest.fixture
def decision_engine_with_eq():
    """Decision engine evaluated on a representative summary that triggers
    flags from rules with each evidence_quality category."""
    summary = {
        "narrative": "test",
        "assembly": {"n_chains": 2, "homo_or_hetero": "homo", "chains": ["A", "B"]},
        "fold": {"representative_chain": "A", "length": 100,
                 "ss_fractions": {"helix": 0.3, "sheet": 0.3, "loop": 0.4}},
        "model_quality": {"is_computed": False},
        "macromolecule_type": "protein_only",
        # confirmed flag: metals_present needs `metals` non-empty
        "metals": [{"id": "ZN", "n_copies": 1, "cluster_type": "mononuclear",
                    "coordinating_residues": ["CYS46"], "context": "catalytic_likely"}],
        # confirmed flag: cofactors_present
        "cofactors": [{"id": "NAD", "n_copies": 1, "chemistry_class": "redox_2e"}],
        # confirmed flag: disulfides_present
        "disulfides": [{"residues": ["CYS1", "CYS5"], "chains": ["A"],
                        "distance_a": 2.05, "type": "standard"}],
        # geometric_only flag: a catalytic triad pattern
        "active_site_patterns": [
            {"pattern": "catalytic_triad", "residues": ["SER1", "HIS2", "ASP3"],
             "chain": "A", "rule_id": "catalytic_triad_geometry"},
        ],
        # heuristic flag: membrane_likely (belt_detected: true)
        "membrane_features": {"belt_detected": True, "belt_residues": ["LEU10"],
                              "trp_girdle": False, "tyr_girdle": False,
                              "estimated_belt_width_a": 30.0},
    }
    return DecisionEngine().run(summary)


def test_decision_engine_tags_confirmed_flags(decision_engine_with_eq):
    flags_by_rule = {f["rule_id"]: f for f in decision_engine_with_eq["flags"]}
    for rid in ("metals_present", "cofactors_present", "disulfides_present"):
        assert rid in flags_by_rule, f"{rid} did not fire"
        assert flags_by_rule[rid].get("evidence_quality") == "confirmed", \
            f"{rid} should be confirmed, got {flags_by_rule[rid].get('evidence_quality')}"


def test_decision_engine_tags_geometric_only_flags(decision_engine_with_eq):
    flags_by_rule = {f["rule_id"]: f for f in decision_engine_with_eq["flags"]}
    assert "catalytic_triad_geometry" in flags_by_rule
    assert flags_by_rule["catalytic_triad_geometry"]["evidence_quality"] == "geometric_only"


def test_decision_engine_tags_heuristic_flags(decision_engine_with_eq):
    flags_by_rule = {f["rule_id"]: f for f in decision_engine_with_eq["flags"]}
    assert "membrane_likely" in flags_by_rule
    assert flags_by_rule["membrane_likely"]["evidence_quality"] == "heuristic"


# ──────────────────────────────────────────────────────────────────
# P1: detector tightening — REGRESSION CASES from the v1 eval
# ──────────────────────────────────────────────────────────────────

def _summary(pdb):
    return F.extract_all(pdb)


# --- the case that triggered the whole rebuild ---

def test_NDRG2_no_active_site_patterns():
    """AF-Q9UN36 (NDRG2 pseudo-enzyme) — v1 fired asp_dyad on this and the
    eval scored only 8/13 on condition C. The contextual gate must keep
    NDRG2 clean."""
    s = _summary("AF-Q9UN36-F1")
    patterns = [p["pattern"] for p in s.get("active_site_patterns") or []]
    assert "asp_dyad" not in patterns, \
        "v1 false positive: NDRG2 must not fire asp_dyad without ligand or metal"
    assert "catalytic_triad" not in patterns


def test_U1A_no_active_site_patterns():
    """1A9N (U1A RBD bound to RNA) — v1 fired asp_dyad. Must stay clean."""
    s = _summary("1a9n")
    patterns = [p["pattern"] for p in s.get("active_site_patterns") or []]
    assert "asp_dyad" not in patterns
    assert "catalytic_triad" not in patterns


# --- membrane_likely false-positive cases from the v1 eval ---

@pytest.mark.parametrize("pdb,note", [
    ("5pep", "Pepsin — soluble enzyme, was v1 FP"),
    ("6lu7", "SARS Mpro — soluble enzyme, was v1 FP"),
    ("1adc", "Alcohol dehydrogenase — soluble enzyme, was v1 FP"),
])
def test_membrane_likely_clean_on_soluble_proteins(pdb, note):
    s = _summary(pdb)
    mf = s.get("membrane_features") or {}
    assert mf.get("belt_detected") is not True, \
        f"v1 regression: {pdb} should not be flagged membrane-likely ({note})"


def test_NDRG2_membrane_flag_at_least_tagged_heuristic():
    """NDRG2 still trips heuristic-A (α-bundle path) because it has long
    interior α-helices. The P1 detector tightening reduced FPs but didn't
    eliminate this one. The safety net is the evidence_quality tag: this
    flag is `heuristic`, so Claude is instructed to treat it as a
    hypothesis requiring corroboration — and the negative_constraint on
    NDRG2 specifically forbids pseudo-enzyme/hydrolase claims."""
    summary = _summary("AF-Q9UN36-F1")
    out = DecisionEngine().run(summary)
    mem_flags = [f for f in out["flags"] if f["rule_id"] == "membrane_likely"]
    if mem_flags:
        # If the flag fires, it MUST be tagged heuristic so Claude
        # weights it correctly.
        assert mem_flags[0]["evidence_quality"] == "heuristic", \
            "NDRG2 membrane flag must carry evidence_quality=heuristic"


def test_AChBP_membrane_clean():
    """2ZJU — pentameric receptor extracellular domain, not membrane-spanning."""
    s = _summary("2zju")
    assert (s.get("membrane_features") or {}).get("belt_detected") is not True


# --- true positives MUST still fire (don't over-tighten) ---

@pytest.mark.parametrize("pdb", ["2omf", "1bl8", "2rh1", "1c3w"])
def test_membrane_likely_still_fires_on_real_membrane_proteins(pdb):
    s = _summary(pdb)
    assert (s.get("membrane_features") or {}).get("belt_detected") is True, \
        f"{pdb} is a real membrane protein and must be flagged"


def test_chymotrypsin_triad_still_fires():
    """5CHA — canonical Ser195/His57/Asp102 cross-chain triad. Must fire.
    Tests the seq_proximate + cross_chain gate paths together."""
    s = _summary("5cha")
    patterns = [p["pattern"] for p in s.get("active_site_patterns") or []]
    assert "catalytic_triad" in patterns


def test_hiv_protease_asp_dyad_still_fires():
    """1HSG — canonical cross-chain Asp25/Asp25' dyad. Must fire (tests
    cross_chain contextual gate)."""
    s = _summary("1hsg")
    patterns = [p["pattern"] for p in s.get("active_site_patterns") or []]
    assert "asp_dyad" in patterns


def test_SARS_Mpro_cys_his_dyad_still_fires():
    """6LU7 — Cys145/His41 catalytic dyad. cys_his_dyad detector wasn't
    contextual-gated, so this should still fire unchanged."""
    s = _summary("6lu7")
    patterns = [p["pattern"] for p in s.get("active_site_patterns") or []]
    assert "cys_his_dyad" in patterns


# --- evidence_quality end-to-end on real proteins ---

def test_2zju_geometric_flags_tagged_geometric_only():
    """The remaining triad/dyad flags on 2ZJU (from anchors like IM4) must
    carry evidence_quality=geometric_only so the prompt steers Claude to
    contradict them rather than trust them."""
    summary = _summary("2zju")
    out = DecisionEngine().run(summary)
    flags = [f for f in out["flags"]
             if f["rule_id"] in ("catalytic_triad_geometry",
                                  "aspartate_dyad_geometry",
                                  "cysteine_dyad_geometry")]
    if flags:   # the contextual gate may have killed them all
        for f in flags:
            assert f["evidence_quality"] == "geometric_only", \
                f"Pattern flag {f['rule_id']} not tagged geometric_only"


def test_iron_sulfur_cluster_flag_is_confirmed():
    """1FXD has an Fe-S cluster — CCD-code-based, deterministic, must be
    tagged as confirmed (not geometric_only or heuristic)."""
    summary = _summary("1fxd")
    out = DecisionEngine().run(summary)
    fes_flags = [f for f in out["flags"] if f["rule_id"] == "iron_sulfur_cluster"]
    assert fes_flags, "1FXD should fire iron_sulfur_cluster"
    assert fes_flags[0]["evidence_quality"] == "confirmed"


# --- decision_tree.yaml integrity ---

def test_every_flag_rule_has_evidence_quality():
    """No rule with a flag action should be missing evidence_quality."""
    tree = yaml.safe_load((ROOT / "skills" / "protein-inspect"
                           / "decision_tree.yaml").read_text())
    missing = []
    for rule in tree["rules"]:
        for action in rule["actions"]:
            if isinstance(action, dict) and "flag" in action:
                if "evidence_quality" not in action["flag"]:
                    missing.append(rule["id"])
    assert not missing, f"Rules with flags missing evidence_quality: {missing}"


def test_geometric_only_rules_are_correctly_tagged():
    """Specific load-bearing assertions about which rules are geometric_only."""
    tree = yaml.safe_load((ROOT / "skills" / "protein-inspect"
                           / "decision_tree.yaml").read_text())
    expected_geometric = {
        "catalytic_triad_geometry", "cysteine_dyad_geometry",
        "aspartate_dyad_geometry", "phosphate_binding_loop",
    }
    for rule in tree["rules"]:
        for action in rule["actions"]:
            if isinstance(action, dict) and "flag" in action:
                if rule["id"] in expected_geometric:
                    assert action["flag"]["evidence_quality"] == "geometric_only", \
                        f"{rule['id']} should be geometric_only"


# ──────────────────────────────────────────────────────────────────
# AF / pLDDT semantics: B-factor column carries pLDDT for computed
# models, NOT crystallographic displacement. extract_fold must
# emit plddt_stats (not bfactor_stats) on AF-DB / computed entries,
# and decision_tree.yaml must carry the explicit reframing rule.
# ──────────────────────────────────────────────────────────────────

@pytest.mark.network
def test_af_model_emits_plddt_stats_not_bfactor_stats():
    """AF-DB model: fold block must carry plddt_stats; bfactor_stats absent."""
    summary = F.extract_all("AF-Q9UN36-F1", source="afdb")
    assert summary["model_quality"]["is_computed"] is True
    assert summary["model_quality"]["confidence_metric"] == "plddt"
    assert "plddt_stats" in summary["fold"], \
        "AF model should emit fold.plddt_stats"
    assert "bfactor_stats" not in summary["fold"], \
        "AF model must NOT emit fold.bfactor_stats — it would mislead readers " \
        "into reading pLDDT values (high = confident) as B-factors (high = mobile)"
    # Bands per EBI / AlphaFold convention
    p = summary["fold"]["plddt_stats"]
    for k in ("fraction_very_high", "fraction_confident", "fraction_low", "fraction_very_low"):
        assert k in p, f"missing pLDDT band fraction {k!r}"
    total = (p["fraction_very_high"] + p["fraction_confident"]
             + p["fraction_low"] + p["fraction_very_low"])
    assert abs(total - 1.0) < 1e-6, f"band fractions should sum to 1.0, got {total}"
    # Values are pLDDT (0–100), not displacement
    assert 0 <= p["min"] <= 100 and 0 <= p["max"] <= 100


@pytest.mark.network
def test_deposited_model_emits_bfactor_stats_not_plddt_stats():
    """Crystallographic entry: fold block must carry bfactor_stats; plddt_stats absent."""
    summary = F.extract_all("1ubq")
    assert summary["model_quality"]["is_computed"] is False
    assert summary["model_quality"]["confidence_metric"] == "bfactor"
    assert "bfactor_stats" in summary["fold"]
    assert "plddt_stats" not in summary["fold"]


def test_decision_tree_has_plddt_not_bfactor_rule():
    """decision_tree.yaml must carry the explicit reframing rule for AF models."""
    tree = yaml.safe_load((ROOT / "skills" / "protein-inspect"
                           / "decision_tree.yaml").read_text())
    rule = next((r for r in tree["rules"] if r["id"] == "plddt_not_bfactor"), None)
    assert rule is not None, "Missing decision_tree rule `plddt_not_bfactor`"
    # The rule should fire only on computed models
    assert rule["when"] == {"equals": {"path": "model_quality.is_computed", "value": True}}
    # The flag's message must explicitly call out that high pLDDT ≠ flexible —
    # this is the inversion-warning that the rule exists to deliver.
    flag = next((a["flag"] for a in rule["actions"] if isinstance(a, dict) and "flag" in a), None)
    assert flag is not None, "plddt_not_bfactor rule has no flag action"
    msg = flag["message"].lower()
    assert "plddt" in msg
    assert "not" in msg and ("flexible" in msg or "displacement" in msg), \
        "plddt_not_bfactor flag message must teach the inversion (high pLDDT ≠ flexible)"


def test_schema_accepts_plddt_stats_on_fold():
    """summary.schema.json must accept plddt_stats on the fold block."""
    sample = {
        "entry": "AF-test", "schema_version": "1.1",
        "generated": "2026-05-28T12:00:00Z",
        "macromolecule_type": "protein_only",
        "model_quality": {"is_computed": True, "confidence_metric": "plddt"},
        "provenance": {"source": "alphafold_db", "resolution_class": "computed"},
        "assembly": {"n_chains": 1, "chains": ["A"], "homo_or_hetero": "monomer"},
        "fold": {
            "representative_chain": "A", "length": 100,
            "ss_fractions": {"helix": 0.3, "sheet": 0.3, "loop": 0.4},
            "plddt_stats": {
                "mean": 85.0, "min": 30.0, "max": 99.0, "std": 15.0,
                "fraction_very_high": 0.6, "fraction_confident": 0.2,
                "fraction_low": 0.1, "fraction_very_low": 0.1,
            },
        },
    }
    VALIDATOR.validate(sample)  # raises if schema rejects
