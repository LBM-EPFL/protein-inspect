"""Schema-layer tests for protein-inspect v1.1.

These run before any feature/runner implementation and confirm the contracts
are well-formed and that representative payloads validate (or are rejected
when malformed).
"""

import json
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).parent.parent
SCHEMA_PATH    = ROOT / "schema" / "summary.schema.json"
DECISION_PATH  = ROOT / "skills" / "protein-inspect" / "decision_tree.yaml"
VIEWS_PATH     = ROOT / "skills" / "protein-inspect" / "view_battery.yaml"
LIGAND_PATH    = ROOT / "skills" / "protein-inspect" / "ligand_classes.yaml"
PROMPT_PATH    = ROOT / "skills" / "protein-inspect" / "prompts" / "analyze.md"


# ─────────────── summary.schema.json ───────────────

def test_schema_is_valid_json_schema():
    schema = json.loads(SCHEMA_PATH.read_text())
    Draft202012Validator.check_schema(schema)


def test_schema_version_is_1_1():
    schema = json.loads(SCHEMA_PATH.read_text())
    assert schema["properties"]["schema_version"]["const"] == "1.1"


def _minimal_summary():
    """The smallest summary that satisfies all required fields."""
    return {
        "entry": "1ubq",
        "schema_version": "1.1",
        "generated": "2026-05-07T12:00:00Z",
        "macromolecule_type": "protein_only",
        "model_quality": {"is_computed": False, "confidence_metric": "bfactor"},
        "provenance": {"source": "rcsb", "resolution_class": "high"},
        "assembly": {"n_chains": 1, "chains": ["A"], "homo_or_hetero": "monomer"},
        "fold": {
            "representative_chain": "A",
            "length": 76,
            "ss_fractions": {"helix": 0.18, "sheet": 0.30, "loop": 0.52},
        },
    }


def test_minimal_summary_validates():
    schema = json.loads(SCHEMA_PATH.read_text())
    Draft202012Validator(schema).validate(_minimal_summary())


def test_full_shaped_summary_validates():
    """A complete summary covering every optional layer — modeled on
    a multi-chain ligand-bearing deposited structure (4HHB-like)."""
    schema = json.loads(SCHEMA_PATH.read_text())
    full = _minimal_summary()
    full.update({
        "entry": "4hhb",
        "narrative": "Hemoglobin α2β2 heterotetramer with HEM cofactors.",
        "macromolecule_type": "protein_only",
        "provenance": {
            "source": "rcsb",
            "resolution": 1.74,
            "method": "X-RAY DIFFRACTION",
            "resolution_class": "high",
            "space_group": "P 21 21 21",
            "unit_cell": [63.15, 83.59, 53.80, 90.0, 90.0, 90.0],
            "deposition_date": "1984-07-07",
        },
        "assembly": {
            "n_chains": 4,
            "oligomer": "tetramer",
            "symmetry": "C2",
            "homo_or_hetero": "hetero",
            "chains": ["A", "B", "C", "D"],
            "unique_sequences": 2,
            "chain_rmsd_max": 0.40,
            "interface_contacts": [{"pair": ["A", "B"], "n_residues": 12}],
        },
        "fold": {
            "representative_chain": "A",
            "length": 141,
            "ss_fractions": {"helix": 0.78, "sheet": 0.0, "loop": 0.22},
            "bfactor_stats": {"mean": 18.7, "min": 4.5, "max": 65.2},
        },
        "ligands": {
            "buffer": [],
            "cryoprotectant": [],
        },
        "cofactors": [
            {"id": "HEM", "n_copies": 4, "chemistry_class": "redox_heme"},
        ],
        "disulfides": [],
        "active_site_patterns": [],
        "flags": [
            {"rule_id": "cofactors_present", "priority": "medium",
             "message": "Cofactor(s) bound."},
        ],
        "coords_ref": {"path": "./4hhb.bcif", "format": "bcif"},
    })
    Draft202012Validator(schema).validate(full)


def test_computed_model_summary_validates():
    """An AlphaFold-style computed model with pLDDT in the B-factor channel."""
    schema = json.loads(SCHEMA_PATH.read_text())
    computed = _minimal_summary()
    computed.update({
        "entry": "AF_test_protein",
        "macromolecule_type": "protein_only",
        "narrative": None,
        "provenance": {"source": "alphafold_db", "resolution": None, "resolution_class": "computed"},
        "model_quality": {
            "is_computed": True,
            "confidence_metric": "plddt",
            "plddt_summary": {
                "mean": 82.3, "fraction_high": 0.55, "fraction_medium": 0.30, "fraction_low": 0.15,
                "low_confidence_regions": [{"chain": "A", "range": [1, 12], "mean_plddt": 42.0}],
            },
        },
    })
    Draft202012Validator(schema).validate(computed)


def test_protein_dna_complex_validates():
    """A protein-DNA complex like a transcription factor."""
    schema = json.loads(SCHEMA_PATH.read_text())
    pdc = _minimal_summary()
    pdc.update({
        "entry": "1cdw",
        "macromolecule_type": "protein_dna",
        "assembly": {
            "n_chains": 3,
            "chains": ["A", "B", "C"],
            "homo_or_hetero": "hetero",
            "oligomer": "trimer",
        },
        "nucleic_acids": {
            "type": "DNA",
            "chains": ["B", "C"],
            "n_residues": 28,
            "is_double_stranded": True,
        },
    })
    Draft202012Validator(schema).validate(pdc)


def test_invalid_macromolecule_type_rejected():
    schema = json.loads(SCHEMA_PATH.read_text())
    bad = _minimal_summary()
    bad["macromolecule_type"] = "nonsense"
    errors = list(Draft202012Validator(schema).iter_errors(bad))
    assert errors, "Expected enum violation on macromolecule_type"


def test_invalid_active_site_pattern_rejected():
    schema = json.loads(SCHEMA_PATH.read_text())
    bad = _minimal_summary()
    bad["active_site_patterns"] = [{
        "pattern": "made_up_motif",   # not in enum
        "residues": ["SER195"],
        "rule_id": "fake",
    }]
    errors = list(Draft202012Validator(schema).iter_errors(bad))
    assert errors, "Expected enum violation on active_site_patterns.pattern"


# ─────────────── decision_tree.yaml ───────────────

def test_decision_tree_loads_and_versioned():
    tree = yaml.safe_load(DECISION_PATH.read_text())
    assert tree["version"] == "1.1"
    assert "rules" in tree


def test_decision_tree_rule_ids_unique():
    tree = yaml.safe_load(DECISION_PATH.read_text())
    ids = [r["id"] for r in tree["rules"]]
    assert len(ids) == len(set(ids)), f"Duplicate rule IDs: {ids}"


def test_decision_tree_rule_count_in_sane_range():
    """Sanity bound. Initial v1.1 ships ~33 rules across 7 tiers; flag rule
    explosion (>40) which would suggest premature family-specific additions."""
    tree = yaml.safe_load(DECISION_PATH.read_text())
    n = len(tree["rules"])
    assert 25 <= n <= 40, f"Expected 25-40 rules, got {n}"


def test_decision_tree_rules_have_required_fields():
    tree = yaml.safe_load(DECISION_PATH.read_text())
    for r in tree["rules"]:
        assert "id" in r
        assert "when" in r
        assert "actions" in r
        assert isinstance(r["actions"], list) and len(r["actions"]) > 0


def test_decision_tree_critical_rules_present():
    """Spot-check the rules whose absence would break v1.1."""
    tree = yaml.safe_load(DECISION_PATH.read_text())
    ids = {r["id"] for r in tree["rules"]}
    must_have = {
        "baseline", "macromolecule_type", "model_type",                  # tier 1
        "multi_chain", "hetero_oligomer",                                # tier 2
        "bio_ligand_present", "crystallographic_artifacts_present",      # tier 3
        "metals_present", "cofactors_present", "nucleic_acid_present",   # tier 4
        "vicinal_disulfide", "catalytic_triad_geometry",                 # tier 5
        "cysteine_dyad_geometry", "aspartate_dyad_geometry",             # tier 5 active site
        "phosphate_binding_loop", "membrane_likely",                     # tier 5
        "no_narrative",                                                  # safeguard
    }
    missing = must_have - ids
    assert not missing, f"Missing critical rules: {missing}"


def test_decision_tree_no_family_naming():
    """Sanity check: rule messages should not bake in pre-judgment family hints
    like 'this is a P450' or 'serine protease'. We allow generic class names
    (hydrolase, oxidoreductase) but refuse the specific ones we agreed to drop."""
    tree = yaml.safe_load(DECISION_PATH.read_text())
    forbidden = ["serine protease", "p450", "cytochrome p450", "rossmann-fold oxidoreductase"]
    for r in tree["rules"]:
        for a in r["actions"]:
            if isinstance(a, dict) and "flag" in a:
                msg = a["flag"]["message"].lower()
                for f in forbidden:
                    assert f not in msg, \
                        f"Rule {r['id']} pre-judges family with forbidden phrase: {f!r}"


# ─────────────── view_battery.yaml ───────────────

def test_view_battery_loads_v1_1():
    vb = yaml.safe_load(VIEWS_PATH.read_text())
    assert vb["version"] == "1.1"


def test_view_battery_contains_all_expected_views():
    vb = yaml.safe_load(VIEWS_PATH.read_text())
    expected = {
        "overview_top", "overview_side", "bfactor_or_plddt_chain_a",
        "surface", "hydrophobic_surface", "ligand_pocket", "metal_closeup",
        "nucleic_acid_cartoon", "interface_closeup", "multi_domain_view",
        "vicinal_ss_zoom", "motif_focus",
    }
    available = set(vb["views"].keys())
    missing = expected - available
    assert not missing, f"Missing views: {missing}"


def test_view_commands_well_formed():
    vb = yaml.safe_load(VIEWS_PATH.read_text())
    for name, view in vb["views"].items():
        assert "output" in view, f"View {name} missing output"
        assert "commands" in view, f"View {name} missing commands"
        for i, cmd in enumerate(view["commands"]):
            assert "fn" in cmd and "args" in cmd, f"{name} cmd {i} malformed"
            assert isinstance(cmd["args"], list)


# ─────────────── ligand_classes.yaml ───────────────

def test_ligand_classes_loads():
    lc = yaml.safe_load(LIGAND_PATH.read_text())
    assert lc["version"] == "1.0"


def test_ligand_classes_has_required_categories():
    lc = yaml.safe_load(LIGAND_PATH.read_text())
    required = {"cryoprotectants", "buffers", "heavy_atoms_phasing",
                "metals_biological", "iron_sulfur_clusters", "cofactors",
                "nucleotides_free", "glycans", "detergents", "lipids"}
    missing = required - lc.keys()
    assert not missing, f"Missing categories: {missing}"


def test_ligand_classes_contain_canonical_codes():
    """Spot-check: GOL must be cryoprotectant, NAD a cofactor, FES an iron-sulfur, NAG a glycan, ZN a metal."""
    lc = yaml.safe_load(LIGAND_PATH.read_text())
    assert "GOL" in lc["cryoprotectants"]
    assert "NAG" in lc["glycans"]
    assert "ZN"  in lc["metals_biological"]
    assert "FES" in lc["iron_sulfur_clusters"]
    # cofactors is a nested dict by chemistry class
    all_cofactor_codes = set()
    for sublist in lc["cofactors"].values():
        all_cofactor_codes.update(sublist)
    assert "NAD" in all_cofactor_codes
    assert "FAD" in all_cofactor_codes
    assert "HEM" in all_cofactor_codes
    assert "PLP" in all_cofactor_codes


def test_ligand_classes_no_overlap_in_artifact_categories():
    """A given CCD code should not be in two artifact categories simultaneously
    (this would create ambiguous classification). Some legitimate cross-listings
    may exist (e.g. dTTP / DTT) — we only check the strict artifact set here."""
    lc = yaml.safe_load(LIGAND_PATH.read_text())
    artifact_cats = ["cryoprotectants", "buffers", "heavy_atoms_phasing", "detergents"]
    seen = {}
    for cat in artifact_cats:
        for code in lc.get(cat, []):
            assert code not in seen, \
                f"{code} appears in both {seen[code]} and {cat} (ambiguous artifact classification)"
            seen[code] = cat


# ─────────────── cross-schema consistency ───────────────

def test_rule_view_names_exist_in_battery():
    tree = yaml.safe_load(DECISION_PATH.read_text())
    vb = yaml.safe_load(VIEWS_PATH.read_text())
    available = set(vb["views"].keys())
    referenced = set()
    for rule in tree["rules"]:
        for action in rule["actions"]:
            if isinstance(action, dict) and "render_view" in action:
                rv = action["render_view"]
                if isinstance(rv, dict) and "name" in rv:
                    referenced.add(rv["name"])
    missing = referenced - available
    assert not missing, f"Rules reference views not defined in battery: {missing}"


def test_active_site_patterns_referenced_by_rules():
    """Every pattern enum in the schema's active_site_patterns must have a
    corresponding decision-tree rule that flags it."""
    schema = json.loads(SCHEMA_PATH.read_text())
    tree = yaml.safe_load(DECISION_PATH.read_text())

    pattern_enum = schema["properties"]["active_site_patterns"]["items"]["properties"]["pattern"]["enum"]
    rule_messages = " ".join(
        a["flag"]["message"].lower()
        for r in tree["rules"]
        for a in r["actions"]
        if isinstance(a, dict) and "flag" in a
    )
    # not perfect but catches gross omissions
    for pat in pattern_enum:
        assert pat.replace("_", " ").split()[0] in rule_messages or pat in rule_messages, \
            f"Active site pattern '{pat}' has no corresponding rule that mentions it"


# ─────────────── prompt presence ───────────────

def test_analyze_prompt_exists_and_references_v1_1_fields():
    txt = PROMPT_PATH.read_text()
    for tag in ["macromolecule_type", "model_quality", "active_site_patterns",
                "ligands.bio_ligand", "metals", "cofactors", "rule_id"]:
        assert tag in txt, f"Prompt missing reference to v1.1 field: {tag}"
