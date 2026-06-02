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
        ["1mbn", "--render-views", "--motif", "His64,Val68",
         "--use-merizo", "--out", "/tmp/x"]
    )
    assert args.target == "1mbn"
    assert args.render_views is True
    assert args.motif == "His64,Val68"
    assert args.use_merizo is True
    assert args.out == "/tmp/x"


# ─────────── RCSB title fetch ───────────

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
