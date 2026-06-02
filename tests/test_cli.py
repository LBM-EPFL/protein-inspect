"""End-to-end CLI / pipeline tests.

Most tests run without PyMOL (YAML-only mode). One test marked with the live
PyMOL integration runs the full pipeline with --render-views.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

from protein_inspect.cli import (
    build_parser,
    fetch_rcsb_title,
    main,
    run_pipeline,
)
from protein_inspect.pymol_runner import is_pymol_available

ROOT = Path(__file__).parent.parent
SCHEMA = json.loads((ROOT / "schema" / "summary.schema.json").read_text())
VALIDATOR = Draft202012Validator(SCHEMA)


# ─────────── argparse ───────────

def test_parser_minimal_invocation():
    args = build_parser().parse_args(["1ubq"])
    assert args.target == "1ubq"
    assert args.render_views is False
    assert args.motif is None
    assert args.use_merizo is False


def test_parser_full_flags():
    args = build_parser().parse_args(
        ["2zju", "--render-views", "--motif", "His57,Asp102,Ser195",
         "--use-merizo", "--out", "/tmp/x"]
    )
    assert args.target == "2zju"
    assert args.render_views is True
    assert args.motif == "His57,Asp102,Ser195"
    assert args.use_merizo is True
    assert args.out == "/tmp/x"


# ─────────── RCSB title fetch ───────────

@pytest.mark.network
def test_fetch_rcsb_title_2zju():
    """2ZJU's title should mention AChBP and imidacloprid."""
    title = fetch_rcsb_title("2zju")
    if title is None:
        pytest.skip("RCSB Data API unreachable")
    title_lower = title.lower()
    assert "achbp" in title_lower or "acetylcholine" in title_lower


@pytest.mark.network
def test_fetch_rcsb_title_invalid_returns_none():
    """A bogus PDB ID should return None, not crash."""
    assert fetch_rcsb_title("zzzz") is None


# ─────────── pipeline (YAML only, no PyMOL needed) ───────────

def test_pipeline_1ubq_yaml_only(tmp_path):
    """End-to-end: 1ubq → summary.yaml. No rendering, no PyMOL."""
    summary = run_pipeline("1ubq", out_dir=tmp_path, render_views=False,
                           fetch_narrative=False)

    # Schema validation
    VALIDATOR.validate(summary)

    # summary.yaml must exist and be loadable
    yaml_path = tmp_path / "summary.yaml"
    assert yaml_path.exists()
    loaded = yaml.safe_load(yaml_path.read_text())
    VALIDATOR.validate(loaded)

    # Coordinates must be copied
    coords_path = Path(loaded["coords_ref"]["path"])
    assert coords_path.exists()

    # No visual block since render_views=False
    assert "visual" not in loaded or loaded["visual"] is None


def test_pipeline_2zju_yaml_with_narrative(tmp_path):
    """Pipeline must populate narrative for deposited PDB IDs."""
    summary = run_pipeline("2zju", out_dir=tmp_path, render_views=False,
                           fetch_narrative=True)
    VALIDATOR.validate(summary)
    # narrative may be None if RCSB is unreachable — soft check
    if summary["narrative"]:
        title_lower = summary["narrative"].lower()
        assert "achbp" in title_lower or "acetylcholine" in title_lower


def test_pipeline_2zju_decision_engine_outputs_present(tmp_path):
    """Pipeline must produce flags from the decision tree."""
    summary = run_pipeline("2zju", out_dir=tmp_path, render_views=False,
                           fetch_narrative=False)
    assert "flags" in summary
    rule_ids = {f["rule_id"] for f in summary["flags"]}
    # Vicinal disulfide MUST be flagged for 2ZJU
    assert "vicinal_disulfide" in rule_ids


# ─────────── live integration (requires PyMOL) ───────────

@pytest.mark.skipif(not is_pymol_available(timeout=1.0),
                    reason="PyMOL not running on port 9880")
def test_pipeline_2zju_with_render(tmp_path):
    """Full end-to-end on 2ZJU with rendering. Verifies:
    - Schema validates
    - summary.yaml has a visual block with the expected canonical views
    - All rendered PNGs exist and are non-empty
    """
    summary = run_pipeline("2zju", out_dir=tmp_path, render_views=True,
                           fetch_narrative=False)
    VALIDATOR.validate(summary)

    assert summary["visual"] is not None
    rendered_names = {r["name"] for r in summary["visual"]["rendered"]}
    # 2zju MUST produce these views
    must_have = {"overview_top", "overview_side", "surface",
                 "bfactor_or_plddt_chain_a", "ligand_pocket",
                 "vicinal_ss_zoom", "interface_closeup"}
    missing = must_have - rendered_names
    assert not missing, f"Missing views in visual block: {missing}"

    # All PNGs must exist and be non-trivial size
    for r in summary["visual"]["rendered"]:
        p = Path(r["path"])
        assert p.exists(), f"missing PNG: {p}"
        assert p.stat().st_size > 1000, f"suspiciously small: {p}"


# ─────────── main() return codes ───────────

def test_main_invalid_target_returns_2(tmp_path, capsys):
    """A bogus 'PDB ID' that is not a valid identifier should exit with rc=2."""
    rc = main(["not_a_valid_pdb_id_format!", "--out", str(tmp_path), "--quiet"])
    assert rc == 2


def test_cli_console_script_entrypoint_works():
    """The `protein-inspect --version` entry point installed by pyproject.toml
    must run and report a version string."""
    result = subprocess.run(
        ["uv", "run", "protein-inspect", "--version"],
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0
    assert "protein-inspect" in result.stdout
