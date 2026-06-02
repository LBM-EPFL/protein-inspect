"""Bridge from view_battery.yaml to a running PyMOL via claudemol's TCP socket.

Translates the high-level `{fn, args}` commands in view_battery.yaml into
PyMOL Python API calls and renders PNGs. Has explicit handlers for "virtual"
functions (color_by_chain, color_by_hydrophobicity, color_by_domain) that
expand into multiple low-level cmd calls.

The runner is deliberately stateless about decision-tree logic: it takes a
render plan (a list of (view_name, params) tuples) and executes it. Plan
generation lives in decision.py (Phase 1.3).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from claudemol.connection import PyMOLConnection

log = logging.getLogger(__name__)

PKG_ROOT = Path(__file__).parent.parent.parent
VIEW_BATTERY_PATH = PKG_ROOT / "skills" / "protein-inspect" / "view_battery.yaml"

# Eisenberg consensus hydrophobicity (same scale as features.HYDROPHOBICITY,
# duplicated here so the PyMOL-side script can be self-contained when sent
# over the socket).
EISENBERG = {
    "ALA": 0.62, "ARG": -2.53, "ASN": -0.78, "ASP": -0.90, "CYS": 0.29,
    "GLU": -0.74, "GLN": -0.85, "GLY": 0.48, "HIS": -0.40, "ILE": 1.38,
    "LEU": 1.06, "LYS": -1.50, "MET": 0.64, "PHE": 1.19, "PRO": 0.12,
    "SER": -0.18, "THR": -0.05, "TRP": 0.81, "TYR": 0.26, "VAL": 1.08,
}


@dataclass
class RenderPlanItem:
    """One view to render."""
    view_name: str
    params: dict
    output_path: Path


class PyMOLRunner:
    """Connects to a running PyMOL via claudemol's TCP socket and executes view scripts."""

    def __init__(self, view_battery_path: Path | None = None,
                 conn: PyMOLConnection | None = None):
        self.view_battery_path = view_battery_path or VIEW_BATTERY_PATH
        self.battery = yaml.safe_load(self.view_battery_path.read_text())
        self.defaults = self.battery.get("defaults", {})
        self.views = self.battery["views"]
        self.conn = conn or PyMOLConnection()
        self._connected = False

    # ─────────── lifecycle ───────────

    def connect(self, timeout: float = 2.0) -> None:
        if not self._connected:
            self.conn.connect(timeout=timeout)
            self._connected = True

    def disconnect(self) -> None:
        if self._connected:
            self.conn.disconnect()
            self._connected = False

    def execute(self, code: str) -> str:
        """Execute Python code in PyMOL. Raises on error."""
        if not self._connected:
            self.connect()
        return self.conn.execute(code)

    # ─────────── structure handling ───────────

    def load_structure(self, path: str, obj_name: str = "obj") -> str:
        """Reset PyMOL state completely and load the structure as obj_name.

        Using `cmd.delete('all')` (not just the named object) so stale state
        from prior structures, named selections, or aborted renders doesn't
        leak between proteins in a multi-protein run. We also explicitly clear
        any user-defined selections — `cmd.delete('all')` leaves those alive
        in some PyMOL versions.
        """
        self.execute("cmd.delete('all')")
        # Belt-and-suspenders: also wipe any custom selections that aren't
        # actual atom groups (selections persist even after cmd.delete('all')
        # in some PyMOL builds).
        self.execute(
            "for _n in list(cmd.get_names('selections')): cmd.delete(_n)"
        )
        self.execute(f"cmd.load({str(path)!r}, {obj_name!r})")
        return obj_name

    def reset_visuals(self) -> None:
        """Clean state between views: hide everything, no labels, default colors."""
        self.execute("cmd.hide('everything')")
        self.execute("cmd.label('all', '')")

    def apply_defaults(self) -> None:
        """Set scene-wide defaults from the view_battery's defaults block.

        Note on PyMOL undo: the undo history grows monotonically across a
        multi-PDB eval run until PyMOL hits its budget and prints
        "Undo has been disabled. Reason: Memory exceeded" — informational
        only, PyMOL keeps rendering. An earlier version tried to pre-empt
        the warning with `cmd.set('suspend_undo', 1)`, but that setting is
        Incentive-PyMOL-only and the open-source build emits one
        "Setting-Warning: suspend_undo is not supported in this PyMOL build"
        per render batch in response — louder than the original message.
        Leaving the undo management to PyMOL's own budget is the portable
        behavior."""
        bg = self.defaults.get("bg_color", "white")
        self.execute(f"cmd.bg_color({bg!r})")
        rs = self.defaults.get("ray_shadows", 1)
        self.execute(f"cmd.set('ray_shadows', {rs})")

    # ─────────── view rendering ───────────

    def render_plan(self, plan: list[RenderPlanItem], obj_name: str = "obj") -> list[dict]:
        """Render a list of views. Returns a list of {name, path, ok, error?} dicts.

        Errors on a single view do not abort the plan — we log and continue, so a
        partial output is still useful. The summary's `visual.rendered` block
        only lists successful renders.
        """
        results = []
        self.apply_defaults()
        for item in plan:
            try:
                path = self.render_view(item.view_name, item.params, item.output_path, obj_name=obj_name)
                results.append({"name": item.view_name, "path": str(path), "ok": True,
                               "details": dict(item.params)})
            except Exception as e:
                log.warning("View %s failed: %s", item.view_name, e)
                results.append({"name": item.view_name, "path": str(item.output_path),
                               "ok": False, "error": str(e)})
        return results

    def render_view(self, view_name: str, params: dict, output_path: Path,
                    obj_name: str = "obj") -> Path:
        """Execute a single view's command sequence and save the PNG."""
        if view_name not in self.views:
            raise KeyError(f"View {view_name!r} not in view battery")
        view_def = self.views[view_name]
        commands = view_def.get("commands", [])
        ctx = {"obj": obj_name, **params}

        # Wipe state from previous view
        self.reset_visuals()

        # Execute the command sequence
        for cmd in commands:
            self._dispatch_command(cmd, ctx)

        # Render and save
        size = self.defaults.get("size", [1200, 900])
        ray = view_def.get("ray", self.defaults.get("ray", True))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if ray:
            self.execute(f"cmd.ray({size[0]}, {size[1]})")
        self.execute(f"cmd.png({str(output_path)!r}, dpi=150)")
        return output_path

    # ─────────── command dispatch ───────────

    def _dispatch_command(self, cmd: dict, ctx: dict) -> None:
        """Translate a {fn, args} entry into a PyMOL call and execute."""
        fn = cmd["fn"]
        args = [self._fill_placeholder(a, ctx) for a in cmd["args"]]

        # Virtual functions that expand to multiple cmds
        if fn == "color_by_chain":
            self.execute(f"cmd.util.cbc({args[0]!r})")
            return
        if fn == "color_by_hydrophobicity":
            self._color_by_hydrophobicity(args[0])
            return
        if fn == "color_by_domain":
            self._color_by_domain(args[0], ctx.get("domain_boundaries", []))
            return

        # Default: cmd.<fn>(...)
        args_repr = ", ".join(_pyrepr(a) for a in args)
        self.execute(f"cmd.{fn}({args_repr})")

    def _fill_placeholder(self, value: Any, ctx: dict) -> Any:
        """Fill {placeholders} in string args. The `obj` placeholder is rewritten
        to PyMOL's explicit `model <name>` syntax — newer PyMOL builds reject
        bare object names inside compound selections like `obj and polymer`,
        with an "invalid model 'and'" error. `model <name>` is the documented
        unambiguous form and works in both bare and compound selection contexts.
        """
        if not isinstance(value, str) or "{" not in value:
            return value
        obj_value = ctx.get("obj")
        local_ctx = dict(ctx)
        if obj_value is not None:
            local_ctx["obj"] = f"model {obj_value}"
        try:
            return value.format(**local_ctx)
        except KeyError as e:
            raise KeyError(
                f"Missing context key {e} for placeholder in {value!r}; "
                f"context keys: {sorted(ctx.keys())}"
            )

    def _color_by_hydrophobicity(self, selection: str) -> None:
        """Color residues by Eisenberg consensus scale: white (hydrophilic) → red (hydrophobic).

        Distinct from PyMOL Wiki's color_h script — we use a 5-step palette so
        the range stays interpretable in raster figures instead of the often
        muddy continuous gradient.
        """
        # Define five named colors mapped to bins of the hydrophobicity scale
        bins = [
            ("h_phil",  "[1.0, 1.0, 1.0]"),  # white  (most hydrophilic)
            ("h_pol",   "[1.0, 0.85, 0.85]"),
            ("h_neut",  "[1.0, 0.6, 0.6]"),
            ("h_hphob", "[0.95, 0.35, 0.35]"),
            ("h_hphob_max", "[0.7, 0.05, 0.05]"),  # deep red (most hydrophobic)
        ]
        for name, rgb in bins:
            self.execute(f"cmd.set_color({name!r}, {rgb})")

        # Bin assignments: thresholds on Eisenberg score
        # bin index 0: ≤ -1.0   → h_phil (R, K, D, E, Q, N)
        # bin index 1: > -1.0 to ≤ 0.0 → h_pol  (S, T, H, G)
        # bin index 2: > 0.0  to ≤ 0.5 → h_neut (A, P, Y, C, M)
        # bin index 3: > 0.5  to ≤ 1.0 → h_hphob (W, L, V)
        # bin index 4: > 1.0          → h_hphob_max (I, F)
        for resn, score in EISENBERG.items():
            if score <= -1.0:
                color = "h_phil"
            elif score <= 0.0:
                color = "h_pol"
            elif score <= 0.5:
                color = "h_neut"
            elif score <= 1.0:
                color = "h_hphob"
            else:
                color = "h_hphob_max"
            sel = f"({selection}) and resn {resn}"
            self.execute(f"cmd.color({color!r}, {sel!r})")

    def _color_by_domain(self, selection: str, boundaries: list[dict]) -> None:
        """Paint each domain a different distinct color.

        boundaries: list of {chain, range: [start, end]} from summary.domains.
        If empty, falls back to a single uniform color.
        """
        palette = ["marine", "salmon", "limon", "violet", "orange",
                   "deepteal", "yelloworange", "lightpink"]
        if not boundaries:
            self.execute(f"cmd.color('gray70', {selection!r})")
            return
        for i, b in enumerate(boundaries):
            chain = b.get("chain", "A")
            start, end = b["range"]
            color = palette[i % len(palette)]
            sel = f"({selection}) and chain {chain} and resi {start}-{end}"
            self.execute(f"cmd.color({color!r}, {sel!r})")


def _pyrepr(value: Any) -> str:
    """Repr for PyMOL Python API call args. Numbers stay numeric; strings are quoted."""
    if isinstance(value, (int, float)):
        return str(value)
    return repr(value)


# ─────────── render-plan helpers (decision.py will use these) ───────────

def make_render_plan(views: list[tuple[str, dict]], output_dir: Path,
                     view_battery_path: Path | None = None) -> list[RenderPlanItem]:
    """Build a list of RenderPlanItem from (view_name, params) tuples.

    Resolves each view's `output` template against params to compute the file
    path. Skips views not in the battery (logs a warning).
    """
    battery_path = view_battery_path or VIEW_BATTERY_PATH
    battery = yaml.safe_load(battery_path.read_text())
    plan = []
    for view_name, params in views:
        view_def = battery["views"].get(view_name)
        if view_def is None:
            log.warning("Unknown view %s — skipping", view_name)
            continue
        try:
            output_filename = view_def["output"].format(**params)
        except KeyError as e:
            log.warning("View %s missing param %s — skipping", view_name, e)
            continue
        plan.append(RenderPlanItem(view_name=view_name, params=params,
                                   output_path=output_dir / output_filename))
    return plan


def is_pymol_available(timeout: float = 1.0) -> bool:
    """Quick check: can we connect to the PyMOL socket right now?"""
    try:
        conn = PyMOLConnection()
        conn.connect(timeout=timeout)
        conn.disconnect()
        return True
    except Exception:
        return False
