"""Tests for pymol_runner.py.

Unit tests use a fake connection (no PyMOL needed) — they verify command
translation, placeholder substitution, and virtual-function expansion.

The integration test loads 2ZJU into the real PyMOL via claudemol and
renders the full baseline view battery. It SKIPS if PyMOL isn't running.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from protein_inspect import features as F
from protein_inspect.pymol_runner import (
    EISENBERG,
    PyMOLRunner,
    RenderPlanItem,
    is_pymol_available,
    make_render_plan,
)

ROOT = Path(__file__).parent.parent
VIEW_BATTERY = ROOT / "skills" / "protein-inspect" / "view_battery.yaml"


# ─────────── fakes ───────────

class FakeConn:
    """Stand-in for claudemol.PyMOLConnection. Records every Python snippet sent."""

    def __init__(self):
        self.history: list[str] = []
        self.connected = False

    def connect(self, timeout: float = 2.0):
        self.connected = True

    def disconnect(self):
        self.connected = False

    def execute(self, code: str) -> str:
        if not self.connected:
            raise RuntimeError("not connected")
        self.history.append(code)
        return ""


@pytest.fixture
def runner():
    fake = FakeConn()
    r = PyMOLRunner(view_battery_path=VIEW_BATTERY, conn=fake)
    r.connect()
    return r


# ─────────── placeholder substitution ───────────

def test_fill_placeholder_substitutes(runner):
    assert runner._fill_placeholder("chain {repr_chain}", {"repr_chain": "A"}) == "chain A"


def test_fill_placeholder_passes_through_non_strings(runner):
    assert runner._fill_placeholder(42, {}) == 42
    assert runner._fill_placeholder(["x"], {}) == ["x"]


def test_fill_placeholder_raises_on_missing_key(runner):
    with pytest.raises(KeyError):
        runner._fill_placeholder("chain {missing_key}", {"foo": "A"})


# ─────────── command dispatch (low-level) ───────────

def test_dispatch_simple_command_translates_to_cmd_call(runner):
    runner._dispatch_command({"fn": "hide", "args": ["everything", "{obj}"]},
                              {"obj": "obj"})
    # {obj} is rewritten to 'model obj' to satisfy newer PyMOL's strict
    # selection parser — see runner._fill_placeholder docstring.
    assert runner.conn.history[-1] == "cmd.hide('everything', 'model obj')"


def test_dispatch_numeric_args_stay_numeric(runner):
    runner._dispatch_command({"fn": "set", "args": ["transparency", 0.1]}, {})
    # 0.1 should NOT be quoted
    assert runner.conn.history[-1] == "cmd.set('transparency', 0.1)"


def test_dispatch_handles_multiple_strings(runner):
    runner._dispatch_command({"fn": "color", "args": ["yellow", "resn IM4"]}, {})
    assert runner.conn.history[-1] == "cmd.color('yellow', 'resn IM4')"


def test_dispatch_color_by_chain_expands_to_util_cbc(runner):
    runner._dispatch_command({"fn": "color_by_chain", "args": ["{obj}"]},
                              {"obj": "obj"})
    # {obj} now expands to 'model obj' (see runner._fill_placeholder)
    assert runner.conn.history[-1] == "cmd.util.cbc('model obj')"


def test_dispatch_color_by_hydrophobicity_emits_palette_and_per_residue(runner):
    runner._dispatch_command({"fn": "color_by_hydrophobicity", "args": ["{obj} and polymer"]},
                              {"obj": "obj"})
    history = runner.conn.history
    # Five named colors must be set up
    assert sum(1 for h in history if "set_color('h_phil'" in h) == 1
    assert sum(1 for h in history if "set_color('h_hphob_max'" in h) == 1
    # All 20 standard amino acids must be colored
    aa_colored = [h for h in history if "cmd.color(" in h and " resn " in h]
    assert len(aa_colored) == len(EISENBERG)


def test_dispatch_color_by_domain_with_boundaries(runner):
    boundaries = [
        {"chain": "A", "range": [1, 100]},
        {"chain": "A", "range": [101, 200]},
    ]
    runner._dispatch_command(
        {"fn": "color_by_domain", "args": ["{obj}"]},
        {"obj": "obj", "domain_boundaries": boundaries},
    )
    history = runner.conn.history
    color_calls = [h for h in history if h.startswith("cmd.color(")]
    assert len(color_calls) == 2
    # First domain marine, second salmon
    assert "marine" in color_calls[0]
    assert "salmon" in color_calls[1]


def test_dispatch_color_by_domain_empty_boundaries_uses_uniform_gray(runner):
    runner._dispatch_command({"fn": "color_by_domain", "args": ["{obj}"]},
                              {"obj": "obj", "domain_boundaries": []})
    assert "gray70" in runner.conn.history[-1]


# ─────────── render plan generation ───────────

def test_make_render_plan_resolves_output_paths(tmp_path):
    plan = make_render_plan(
        [("overview_top", {}),
         ("ligand_pocket", {"ligand_resn": "IM4", "ligand_chain": "A", "ligand_resi": 301})],
        output_dir=tmp_path,
        view_battery_path=VIEW_BATTERY,
    )
    assert len(plan) == 2
    assert plan[0].output_path.name == "01_top.png"
    assert plan[1].output_path.name == "05_pocket_IM4_A301.png"


def test_make_render_plan_skips_unknown_views(tmp_path, caplog):
    plan = make_render_plan(
        [("does_not_exist", {}), ("overview_top", {})],
        output_dir=tmp_path,
        view_battery_path=VIEW_BATTERY,
    )
    assert len(plan) == 1
    assert plan[0].view_name == "overview_top"


def test_make_render_plan_skips_views_with_missing_params(tmp_path):
    # ligand_pocket requires ligand_resn AND ligand_chain AND ligand_resi
    plan = make_render_plan(
        [("ligand_pocket", {"ligand_resn": "IM4"})],   # missing ligand_chain + ligand_resi
        output_dir=tmp_path,
        view_battery_path=VIEW_BATTERY,
    )
    assert plan == []


# ─────────── render orchestration with fake connection ───────────

def test_render_view_executes_full_command_sequence_and_saves_png(runner, tmp_path):
    out = tmp_path / "01_top.png"
    runner.render_view("overview_top", {}, out)
    history = runner.conn.history
    # Final command must be a png save with the requested path
    assert any(f"cmd.png({str(out)!r}" in h for h in history)
    # Ray-tracing call before png
    assert any(h.startswith("cmd.ray(") for h in history)


def test_render_plan_continues_after_a_view_fails(runner, tmp_path, monkeypatch):
    # Rig the fake connection to fail on the second view
    real_execute = runner.execute
    n_calls = {"count": 0}
    def flaky_execute(code):
        if "01_top.png" in code:
            n_calls["count"] += 1
        if "02_side.png" in code:
            raise RuntimeError("simulated PyMOL error")
        return real_execute(code)
    monkeypatch.setattr(runner, "execute", flaky_execute)

    plan = [
        RenderPlanItem(view_name="overview_top", params={}, output_path=tmp_path / "01_top.png"),
        RenderPlanItem(view_name="overview_side", params={}, output_path=tmp_path / "02_side.png"),
    ]
    results = runner.render_plan(plan)
    assert results[0]["ok"] is True
    assert results[1]["ok"] is False
    assert "simulated PyMOL error" in results[1]["error"]


# ─────────── live integration test (requires running PyMOL) ───────────

INTEGRATION_OUT = ROOT / "examples" / "integration_2zju"


@pytest.mark.skipif(not is_pymol_available(timeout=1.0),
                    reason="PyMOL not running on port 9880; start PyMOL with the claudemol plugin")
def test_integration_render_2zju_baseline_views():
    """End-to-end: load 2ZJU and render the four baseline views via real PyMOL.

    Verifies the runner survives a real round-trip through the socket and
    produces non-empty PNG files. Also exercises the hydrophobicity surface
    (which is a long sequence of per-residue color calls — a stress test
    for the socket pipeline)."""
    INTEGRATION_OUT.mkdir(parents=True, exist_ok=True)
    # Get a real structure path (uses the cached fetch from tests/test_features)
    struct, path = F.fetch_structure("2zju")

    runner = PyMOLRunner()
    runner.connect()
    try:
        runner.load_structure(path, obj_name="t2zju")
        plan = make_render_plan(
            [
                ("overview_top", {}),
                ("overview_side", {}),
                ("bfactor_or_plddt_chain_a", {"repr_chain": "A", "confidence_metric": "bfactor"}),
                ("surface", {}),
            ],
            output_dir=INTEGRATION_OUT,
            view_battery_path=VIEW_BATTERY,
        )
        results = runner.render_plan(plan, obj_name="t2zju")
    finally:
        runner.disconnect()

    # All four views must succeed
    failed = [r for r in results if not r["ok"]]
    assert not failed, f"Views failed: {failed}"
    # PNGs must exist and be non-empty
    for r in results:
        p = Path(r["path"])
        assert p.exists(), f"missing PNG: {p}"
        assert p.stat().st_size > 1000, f"PNG suspiciously small: {p} ({p.stat().st_size} B)"


@pytest.mark.skipif(not is_pymol_available(timeout=1.0),
                    reason="PyMOL not running on port 9880")
def test_integration_render_2zju_ligand_pocket():
    """Render the IM4 ligand pocket — exercises a parameterized conditional view."""
    INTEGRATION_OUT.mkdir(parents=True, exist_ok=True)
    struct, path = F.fetch_structure("2zju")

    # Find the actual residue number of an IM4 instance in chain A
    im4_resi = None
    for chain in struct[0]:
        if chain.name == "A":
            for res in chain:
                if res.name == "IM4":
                    im4_resi = res.seqid.num
                    break
            break
    assert im4_resi is not None, "IM4 not found on chain A"

    runner = PyMOLRunner()
    runner.connect()
    try:
        runner.load_structure(path, obj_name="t2zju")
        plan = make_render_plan(
            [("ligand_pocket", {"ligand_resn": "IM4", "ligand_chain": "A",
                                "ligand_resi": im4_resi})],
            output_dir=INTEGRATION_OUT,
            view_battery_path=VIEW_BATTERY,
        )
        results = runner.render_plan(plan, obj_name="t2zju")
    finally:
        runner.disconnect()

    assert results[0]["ok"], f"Ligand pocket render failed: {results[0]}"
    p = Path(results[0]["path"])
    assert p.exists()
    assert p.stat().st_size > 1000


@pytest.mark.skipif(not is_pymol_available(timeout=1.0),
                    reason="PyMOL not running on port 9880")
def test_integration_render_2zju_vicinal_disulfide():
    """Verify the vicinal-disulfide zoom view fires correctly when there's actually
    a vicinal disulfide present (2ZJU CYS187-CYS188)."""
    INTEGRATION_OUT.mkdir(parents=True, exist_ok=True)
    struct, path = F.fetch_structure("2zju")

    runner = PyMOLRunner()
    runner.connect()
    try:
        runner.load_structure(path, obj_name="t2zju")
        plan = make_render_plan(
            [("vicinal_ss_zoom", {"chain": "A", "resi_a": 187, "resi_b": 188})],
            output_dir=INTEGRATION_OUT,
            view_battery_path=VIEW_BATTERY,
        )
        results = runner.render_plan(plan, obj_name="t2zju")
    finally:
        runner.disconnect()

    assert results[0]["ok"]
    p = Path(results[0]["path"])
    assert p.exists() and p.stat().st_size > 1000
