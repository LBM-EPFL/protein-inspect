"""Tests for decision.py — predicate evaluator, decision engine, render planner."""

from pathlib import Path

import pytest

from protein_inspect import features as F
from protein_inspect.decision import (
    ConditionEvaluator,
    DecisionEngine,
    RenderPlanner,
    ViewRequest,
    plan_for_summary,
)

ROOT = Path(__file__).parent.parent


# ─────────── condition evaluator: leaf operators ───────────

@pytest.fixture
def sample_summary():
    return {
        "model_quality": {"is_computed": False, "confidence_metric": "bfactor"},
        "assembly": {
            "n_chains": 5,
            "homo_or_hetero": "homo",
            "oligomer": "pentamer",
            "symmetry": "C5",
            "chains": ["A", "B", "C", "D", "E"],
        },
        "fold": {"representative_chain": "A", "length": 215,
                 "ss_fractions": {"helix": 0.07, "sheet": 0.42, "loop": 0.51}},
        "ligands": {
            "bio_ligand": [{"id": "IM4", "n_copies": 5, "aromatic_cage": True,
                           "placement": "subunit_interface"}],
            "cryoprotectant": [{"id": "GOL", "n_copies": 3}],
        },
        "disulfides": [
            {"residues": ["CYS123", "CYS136"], "chains": ["A"], "distance_a": 2.04, "type": "standard"},
            {"residues": ["CYS187", "CYS188"], "chains": ["A"], "distance_a": 2.05, "type": "vicinal"},
        ],
        "active_site_patterns": [
            {"pattern": "aromatic_cage", "residues": ["TRP143", "TYR185", "TYR192"], "chain": "A",
             "rule_id": "aromatic_cage_at_ligand_site"},
        ],
        "narrative": None,
        "metals": [],
        "cofactors": [],
        "macromolecule_type": "protein_only",
        "membrane_features": {"belt_detected": False},
    }


def test_eval_always(sample_summary):
    e = ConditionEvaluator(sample_summary, {})
    assert e.eval("always") is True
    assert e.eval(True) is True
    assert e.eval(False) is False


def test_eval_has_and_missing(sample_summary):
    e = ConditionEvaluator(sample_summary, {})
    assert e.eval({"has": "ligands.bio_ligand"}) is True
    assert e.eval({"has": "metals"}) is False     # empty list
    assert e.eval({"missing": "metals"}) is True
    assert e.eval({"has": "nonexistent.path"}) is False


def test_eval_equals(sample_summary):
    e = ConditionEvaluator(sample_summary, {})
    assert e.eval({"equals": {"path": "assembly.oligomer", "value": "pentamer"}}) is True
    assert e.eval({"equals": {"path": "assembly.oligomer", "value": "monomer"}}) is False
    assert e.eval({"equals": {"path": "narrative", "value": None}}) is True


def test_eval_greater_less(sample_summary):
    e = ConditionEvaluator(sample_summary, {})
    assert e.eval({"greater": {"path": "assembly.n_chains", "value": 1}}) is True
    assert e.eval({"greater": {"path": "assembly.n_chains", "value": 10}}) is False
    assert e.eval({"less": {"path": "fold.length", "value": 300}}) is True


def test_eval_any_in(sample_summary):
    e = ConditionEvaluator(sample_summary, {})
    cond = {"any_in": {"list": "disulfides", "where": {"equals": {"path": "type", "value": "vicinal"}}}}
    assert e.eval(cond) is True
    cond2 = {"any_in": {"list": "disulfides", "where": {"equals": {"path": "type", "value": "interchain"}}}}
    assert e.eval(cond2) is False


def test_eval_compound_all_of(sample_summary):
    e = ConditionEvaluator(sample_summary, {})
    cond = {"all_of": [
        {"equals": {"path": "assembly.oligomer", "value": "pentamer"}},
        {"equals": {"path": "assembly.symmetry", "value": "C5"}},
    ]}
    assert e.eval(cond) is True
    cond_bad = {"all_of": [
        {"equals": {"path": "assembly.oligomer", "value": "pentamer"}},
        {"equals": {"path": "assembly.symmetry", "value": "C7"}},
    ]}
    assert e.eval(cond_bad) is False


def test_eval_input_provided(sample_summary):
    e_with = ConditionEvaluator(sample_summary, {"motif": "His153,Asp166,Ser142"})
    assert e_with.eval({"input_provided": "motif"}) is True
    e_without = ConditionEvaluator(sample_summary, {})
    assert e_without.eval({"input_provided": "motif"}) is False


# ─────────── decision engine: rules fire correctly ───────────

def test_engine_fires_baseline_always(sample_summary):
    out = DecisionEngine().run(sample_summary)
    assert "baseline" in out["rule_ids_fired"]
    # Baseline schedules four views
    requested = {v.name for v in out["view_requests"]}
    for must in ("overview_top", "overview_side", "surface", "bfactor_or_plddt_chain_a"):
        assert must in requested


def test_engine_fires_multi_chain_for_oligomer(sample_summary):
    """The pentameric_ring rule was dropped (it pre-judged family). For
    multi-chain assemblies, multi_chain fires and produces interface analysis,
    which is the family-agnostic descriptive equivalent."""
    out = DecisionEngine().run(sample_summary)
    assert "multi_chain" in out["rule_ids_fired"]
    # interface_ligand should also fire (placement: subunit_interface)
    assert "interface_ligand" in out["rule_ids_fired"]


def test_engine_fires_vicinal_disulfide(sample_summary):
    out = DecisionEngine().run(sample_summary)
    assert "vicinal_disulfide" in out["rule_ids_fired"]
    rid_set = {r["rule_id"] for r in out["flags"]}
    assert "vicinal_disulfide" in rid_set
    # disulfides_present should fire too (generic flag)
    assert "disulfides_present" in out["rule_ids_fired"]


def test_engine_fires_no_narrative_safeguard(sample_summary):
    out = DecisionEngine().run(sample_summary)
    assert "no_narrative" in out["rule_ids_fired"]


def test_engine_does_not_fire_metals_when_empty(sample_summary):
    out = DecisionEngine().run(sample_summary)
    assert "metals_present" not in out["rule_ids_fired"]
    assert "iron_sulfur_cluster" not in out["rule_ids_fired"]


def test_engine_motif_rule_fires_with_arg():
    s = {"narrative": "x", "model_quality": {"is_computed": False}, "assembly": {"n_chains": 1, "homo_or_hetero": "monomer"}}
    out = DecisionEngine().run(s, args={"motif": "His153"})
    assert "motif_specified" in out["rule_ids_fired"]


# ─────────── render planner: parameter expansion ───────────

@pytest.fixture
def fixture_4hhb():
    """Real 4hhb summary + structure for end-to-end planner tests.
    Hemoglobin α2β2 tetramer with HEM cofactors — multi-chain, multi-ligand."""
    summary = F.extract_all("4hhb")
    struct, _ = F.fetch_structure("4hhb")
    return summary, struct


def test_planner_expands_ligand_pocket_per_instance(tmp_path):
    """1hsg: HIV-1 protease with MK1 inhibitor — small-molecule bio_ligand."""
    summary = F.extract_all("1hsg")
    struct, _ = F.fetch_structure("1hsg")
    requests = [ViewRequest(name="ligand_pocket", per_ligand=True, rule_id="bio_ligand_present")]
    plan = RenderPlanner().expand(requests, summary, struct, tmp_path)
    assert len(plan) >= 1
    paths = {p.output_path for p in plan}
    assert len(paths) == len(plan)
    chains_in_filenames = sorted({p.output_path.name for p in plan})
    assert any("MK1" in n for n in chains_in_filenames)


def test_planner_picks_bfactor_metric_for_deposited(fixture_4hhb, tmp_path):
    summary, struct = fixture_4hhb
    requests = [ViewRequest(name="bfactor_or_plddt_chain_a")]
    plan = RenderPlanner().expand(requests, summary, struct, tmp_path)
    assert len(plan) == 1
    # 4hhb is X-ray (deposited) → confidence_metric should be 'bfactor'
    assert "bfactor" in plan[0].output_path.name


def test_planner_picks_plddt_for_computed():
    """Synthetic computed-model summary: planner must route to plddt."""
    summary = {
        "model_quality": {"is_computed": True, "confidence_metric": "plddt"},
        "fold": {"representative_chain": "A", "length": 100,
                 "ss_fractions": {"helix": 0.5, "sheet": 0.3, "loop": 0.2}},
        "assembly": {"n_chains": 1, "chains": ["A"], "homo_or_hetero": "monomer"},
    }
    requests = [ViewRequest(name="bfactor_or_plddt_chain_a")]
    # Need a stub structure — easiest: load a small real one
    import gemmi
    struct, _ = F.fetch_structure("1ubq")
    plan = RenderPlanner().expand(requests, summary, struct, Path("/tmp"))
    assert "plddt" in plan[0].output_path.name


def test_planner_picks_default_AB_interface_for_multi_chain(fixture_4hhb, tmp_path):
    summary, struct = fixture_4hhb
    requests = [ViewRequest(name="interface_closeup")]
    plan = RenderPlanner().expand(requests, summary, struct, tmp_path)
    assert len(plan) == 1
    assert "A-B" in plan[0].output_path.name


def test_planner_threads_domain_boundaries_into_multi_domain_view(tmp_path):
    """multi_domain_view's params must include domain_boundaries so the runner's
    color_by_domain virtual function paints the right ranges."""
    summary = {
        "model_quality": {"is_computed": False},
        "assembly": {"n_chains": 1, "chains": ["A"], "homo_or_hetero": "monomer"},
        "fold": {"representative_chain": "A", "length": 524,
                 "ss_fractions": {"helix": 0.66, "sheet": 0.33, "loop": 0.01}},
        "domains": {
            "count": 3,
            "detected_by": "cath_api",
            "boundaries": [
                {"chain": "A", "range": [1, 134]},
                {"chain": "A", "range": [135, 410]},
                {"chain": "A", "range": [411, 525]},
            ],
        },
    }
    import gemmi
    struct, _ = F.fetch_structure("1aon")
    requests = [ViewRequest(name="multi_domain_view")]
    plan = RenderPlanner().expand(requests, summary, struct, tmp_path)
    assert len(plan) == 1
    # The expanded item should have domain_boundaries in its params
    item = plan[0]
    # domain_boundaries threads via params dict (used by runner's color_by_domain)
    # Note: RenderPlanItem.params holds the domain_boundaries
    assert "domain_boundaries" in item.params
    assert len(item.params["domain_boundaries"]) == 3


# ─────────── end-to-end orchestrator ───────────

def test_plan_for_summary_4hhb_end_to_end(fixture_4hhb, tmp_path):
    summary, struct = fixture_4hhb
    out = plan_for_summary(summary, struct, tmp_path)
    assert {"flags", "rule_ids_fired", "render_plan"} <= set(out.keys())
    # 4HHB is an α2β2 heterotetramer with 4 HEM cofactors. Key rules that
    # MUST fire on any deposited multi-chain ligand-bearing structure:
    fired = set(out["rule_ids_fired"])
    for rid in ("baseline", "multi_chain", "cofactors_present"):
        assert rid in fired, f"Expected rule {rid!r} to fire — got {fired}"
    # Plan must contain baseline views + cofactor_closeup + interface_closeup
    plan_view_names = {item.view_name for item in out["render_plan"]}
    must_view = {"overview_top", "overview_side", "surface",
                 "bfactor_or_plddt_chain_a", "interface_closeup"}
    missing = must_view - plan_view_names
    assert not missing, f"Missing planned views: {missing}"


def test_plan_for_summary_1ubq_minimal_protein(tmp_path):
    """Small monomeric ubiquitin: only baseline rules + macromolecule_type +
    model_type + no_narrative should fire. (features.py never extracts the
    narrative text — it's left None for the orchestrator to fill from RCSB
    metadata later — so no_narrative fires legitimately.)"""
    summary = F.extract_all("1ubq")
    struct, _ = F.fetch_structure("1ubq")
    out = plan_for_summary(summary, struct, tmp_path)
    fired = set(out["rule_ids_fired"])
    assert "baseline" in fired
    assert "multi_chain" not in fired         # monomer
    assert "vicinal_disulfide" not in fired
    assert "bio_ligand_present" not in fired
    assert "no_narrative" in fired            # narrative field not extracted by features.py
    # Render plan: only baseline views, none of the conditional ones
    plan_view_names = {item.view_name for item in out["render_plan"]}
    assert "ligand_pocket" not in plan_view_names
    assert "vicinal_ss_zoom" not in plan_view_names
    assert "interface_closeup" not in plan_view_names
