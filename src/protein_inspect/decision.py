"""Walk decision_tree.yaml against an extracted summary.

Outputs:
- `flags`        — list of {rule_id, priority, message} to merge into summary.flags
- `view_requests` — list of (view_name, params, per_directive) — abstract render requests
- `render_plan`  — concrete RenderPlanItem list after parameter expansion (one entry per
                   ligand instance, per metal site, per vicinal disulfide, etc.)

The planner translates "abstract" view requests like `ligand_pocket: per_ligand: true`
into concrete instances by introspecting the gemmi.Structure to find chain+resi for each
HETATM residue. The view battery's `output:` template fills in unique filenames.

Predicate evaluator is a small interpreter for the YAML DSL (always / has / equals /
greater / less / any_in / all_of / any_of / not / input_provided / missing). NO Python
eval, NO arbitrary code paths — every condition kind is enumerated explicitly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import gemmi
import yaml

from protein_inspect.pymol_runner import RenderPlanItem, make_render_plan

log = logging.getLogger(__name__)

PKG_ROOT = Path(__file__).parent.parent.parent
DECISION_TREE_PATH = PKG_ROOT / "skills" / "protein-inspect" / "decision_tree.yaml"
VIEW_BATTERY_PATH = PKG_ROOT / "skills" / "protein-inspect" / "view_battery.yaml"


@dataclass
class ViewRequest:
    """An abstract request for a view; may expand to multiple RenderPlanItems."""
    name: str
    params: dict = field(default_factory=dict)
    per_ligand: bool = False
    per_metal: bool = False
    per_disulfide: bool = False
    per_cofactor: bool = False
    per_glycan: bool = False
    per_na_chain: bool = False
    per_peptide_chain: bool = False
    rule_id: str = ""


# ─────────── condition evaluator ───────────

class ConditionEvaluator:
    """Evaluates the small DSL in decision_tree.yaml against a summary dict."""

    def __init__(self, summary: dict, args: dict):
        self.summary = summary
        self.args = args

    def eval(self, cond: Any, scope: dict | None = None) -> bool:
        """Recursively evaluate. `scope` is the summary by default but switches to
        a list item when inside `any_in`'s `where` block."""
        if scope is None:
            scope = self.summary
        if cond is True or cond == "always":
            return True
        if cond is False:
            return False
        if not isinstance(cond, dict):
            return False

        if "always" in cond:
            return bool(cond["always"])
        if "has" in cond:
            return self._has(cond["has"], scope)
        if "missing" in cond:
            return not self._has(cond["missing"], scope)
        if "equals" in cond:
            return self._get(cond["equals"]["path"], scope) == cond["equals"]["value"]
        if "greater" in cond:
            v = self._get(cond["greater"]["path"], scope)
            return v is not None and v > cond["greater"]["value"]
        if "less" in cond:
            v = self._get(cond["less"]["path"], scope)
            return v is not None and v < cond["less"]["value"]
        if "any_in" in cond:
            items = self._get(cond["any_in"]["list"], scope) or []
            sub = cond["any_in"]["where"]
            return any(self.eval(sub, scope=item) for item in items)
        if "all_of" in cond:
            return all(self.eval(c, scope=scope) for c in cond["all_of"])
        if "any_of" in cond:
            return any(self.eval(c, scope=scope) for c in cond["any_of"])
        if "not" in cond:
            return not self.eval(cond["not"], scope=scope)
        if "input_provided" in cond:
            return self.args.get(cond["input_provided"]) is not None
        log.warning("Unknown condition shape: %s", cond)
        return False

    def _has(self, path: str, scope: dict) -> bool:
        v = self._get(path, scope)
        if v is None:
            return False
        if isinstance(v, (list, dict, str)):
            return len(v) > 0
        return True

    @staticmethod
    def _get(path: str, scope: dict) -> Any:
        cur: Any = scope
        for part in path.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                return None
        return cur


# ─────────── decision engine ───────────

class DecisionEngine:
    """Walk decision_tree.yaml and produce flags + view_requests."""

    def __init__(self, tree_path: Path | None = None, view_battery_path: Path | None = None):
        self.tree = yaml.safe_load((tree_path or DECISION_TREE_PATH).read_text())
        self.view_battery_path = view_battery_path or VIEW_BATTERY_PATH

    def run(self, summary: dict, args: dict | None = None) -> dict:
        """Returns {flags, view_requests, rule_ids_fired}."""
        args = args or {}
        ev = ConditionEvaluator(summary, args)
        flags: list[dict] = []
        view_requests: list[ViewRequest] = []
        rule_ids_fired: list[str] = []

        for rule in self.tree["rules"]:
            if not ev.eval(rule["when"]):
                continue
            rule_ids_fired.append(rule["id"])
            for action in rule["actions"]:
                self._execute_action(action, rule["id"], flags, view_requests)
        return {
            "flags": flags,
            "view_requests": view_requests,
            "rule_ids_fired": rule_ids_fired,
        }

    def _execute_action(self, action: Any, rule_id: str,
                        flags: list[dict], view_requests: list[ViewRequest]) -> None:
        if not isinstance(action, dict):
            return
        if "compute" in action:
            # features.py handles all extraction; `compute` is a documentation marker
            return
        if "annotate" in action:
            return  # reserved for v2
        if "flag" in action:
            f = action["flag"]
            entry = {
                "rule_id": rule_id,
                "priority": f.get("priority", "low"),
                "message": f["message"],
            }
            # evidence_quality is what tells the LLM how load-bearing this flag
            # is. geometric_only / heuristic flags require corroboration before
            # being treated as facts.
            if "evidence_quality" in f:
                entry["evidence_quality"] = f["evidence_quality"]
            flags.append(entry)
            return
        if "render_view" in action:
            rv = action["render_view"]
            # Two shapes: name only, or name + extras like per_ligand
            view_requests.append(ViewRequest(
                name=rv["name"],
                params=rv.get("params", {}),
                per_ligand=bool(rv.get("per_ligand")),
                per_metal=bool(rv.get("per_metal")),
                per_disulfide=bool(rv.get("per_disulfide")),
                per_cofactor=bool(rv.get("per_cofactor")),
                per_glycan=bool(rv.get("per_glycan")),
                per_na_chain=bool(rv.get("per_na_chain")),
                per_peptide_chain=bool(rv.get("per_peptide_chain")),
                rule_id=rule_id,
            ))
            return


# ─────────── view request expansion → concrete render plan ───────────

class RenderPlanner:
    """Translates abstract ViewRequests into concrete RenderPlanItems."""

    def __init__(self, view_battery_path: Path | None = None):
        self.view_battery_path = view_battery_path or VIEW_BATTERY_PATH

    def expand(self, requests: list[ViewRequest], summary: dict,
               structure: gemmi.Structure, output_dir: Path) -> list[RenderPlanItem]:
        """Walk requests, expanding parameterized ones into per-instance renders.
        Returns a flat list of RenderPlanItems ready for PyMOLRunner.
        """
        concrete: list[tuple[str, dict]] = []
        for req in requests:
            concrete.extend(self._expand_one(req, summary, structure))
        return make_render_plan(concrete, output_dir, view_battery_path=self.view_battery_path)

    # ─────────── per-request expansion ───────────

    def _expand_one(self, req: ViewRequest, summary: dict, structure: gemmi.Structure) -> list[tuple[str, dict]]:
        # bfactor_or_plddt_chain_a — auto-route based on model_quality.
        # Skip on deposited structures whose B-factor field is flat (pre-1980
        # depositions like 1mbn record B-iso=0 for every atom — spectrum would
        # collapse to a uniform color and the view would be uninformative).
        if req.name == "bfactor_or_plddt_chain_a":
            is_computed = summary.get("model_quality", {}).get("is_computed", False)
            if not is_computed:
                bf_std = ((summary.get("fold") or {}).get("bfactor_stats") or {}).get("std", 0.0)
                if bf_std < 0.5:
                    log.info("skipping bfactor view: B-factors are flat (std=%.3f)", bf_std)
                    return []
            return [(req.name, self._params_bfactor_plddt(summary))]

        # multi_domain_view — needs repr_chain + threads domain_boundaries through ctx
        if req.name == "multi_domain_view":
            return [(req.name, self._params_multi_domain(summary))]

        # interface_closeup — pick A-B by default
        if req.name == "interface_closeup":
            return [(req.name, self._params_interface(summary))]

        # ligand_pocket — one per bio-ligand instance
        if req.per_ligand or req.name == "ligand_pocket":
            return [
                (req.name, p) for p in self._iter_ligand_params(summary, structure)
            ]

        # metal_closeup — one per metal residue instance
        if req.per_metal or req.name == "metal_closeup":
            return [
                (req.name, p) for p in self._iter_metal_params(summary, structure)
            ]

        # vicinal_ss_zoom — one per vicinal disulfide
        if req.per_disulfide or req.name == "vicinal_ss_zoom":
            return [
                (req.name, p) for p in self._iter_vicinal_disulfide_params(summary)
            ]

        # cofactor_closeup — one per cofactor residue instance
        if req.per_cofactor or req.name == "cofactor_closeup":
            return [
                (req.name, p) for p in self._iter_cofactor_params(summary, structure)
            ]

        # glycan_closeup — one per bound-glycan residue instance (skips
        # N-linked glycosylation decoration; those are flagged separately)
        if req.per_glycan or req.name == "glycan_closeup":
            return [
                (req.name, p) for p in self._iter_glycan_params(summary, structure)
            ]

        # na_interface_closeup — one per nucleic acid chain
        if req.per_na_chain or req.name == "na_interface_closeup":
            return [
                (req.name, p) for p in self._iter_na_chain_params(summary, structure)
            ]

        # peptide_interface_closeup — one per detected peptide-ligand chain
        if req.per_peptide_chain or req.name == "peptide_interface_closeup":
            return [
                (req.name, p) for p in self._iter_peptide_chain_params(summary, structure)
            ]

        # motif_focus — pull selection from CLI args (the engine receives it via args)
        if req.name == "motif_focus":
            sel = req.params.get("motif_selection")
            if sel:
                return [(req.name, {"motif_selection": sel})]
            log.warning("motif_focus requested but no motif_selection in params")
            return []

        # Default: pass through with whatever params were already supplied
        return [(req.name, dict(req.params))]

    # ─────────── parameter builders ───────────

    @staticmethod
    def _repr_chain(summary: dict) -> str:
        return summary.get("fold", {}).get("representative_chain", "A")

    def _params_bfactor_plddt(self, summary: dict) -> dict:
        repr_chain = self._repr_chain(summary)
        is_computed = summary.get("model_quality", {}).get("is_computed", False)
        return {
            "repr_chain": repr_chain,
            "confidence_metric": "plddt" if is_computed else "bfactor",
        }

    def _params_multi_domain(self, summary: dict) -> dict:
        repr_chain = self._repr_chain(summary)
        boundaries = (summary.get("domains") or {}).get("boundaries") or []
        # Filter to representative chain only — multi_domain_view shows one chain
        chain_boundaries = [b for b in boundaries if b.get("chain") == repr_chain]
        return {
            "repr_chain": repr_chain,
            "domain_boundaries": chain_boundaries,
        }

    def _params_interface(self, summary: dict) -> dict:
        chains = summary.get("assembly", {}).get("chains") or []
        if len(chains) >= 2:
            return {"chain_a": chains[0], "chain_b": chains[1]}
        # Shouldn't happen because multi_chain rule gates this view,
        # but defensive default
        return {"chain_a": "A", "chain_b": "B"}

    @staticmethod
    def _iter_ligand_params(summary: dict, structure: gemmi.Structure) -> list[dict]:
        """For each bio_ligand entry, find every (chain, resi) instance in the
        structure and emit one view per instance. Including resi ensures distinct
        copies of the same ligand on the same chain get separate filenames and
        separate close-up views."""
        bio_ligands = (summary.get("ligands") or {}).get("bio_ligand") or []
        if not bio_ligands:
            return []
        by_code = {entry["id"]: entry for entry in bio_ligands}

        out: list[dict] = []
        for chain in structure[0]:
            for res in chain:
                if res.name in by_code:
                    out.append({
                        "ligand_resn": res.name,
                        "ligand_chain": chain.name,
                        "ligand_resi": res.seqid.num,
                    })
        return out

    @staticmethod
    def _iter_metal_params(summary: dict, structure: gemmi.Structure) -> list[dict]:
        metal_codes = {m["id"] for m in summary.get("metals") or []}
        if not metal_codes:
            return []
        out: list[dict] = []
        for chain in structure[0]:
            for res in chain:
                if res.name in metal_codes:
                    out.append({
                        "metal_resn": res.name,
                        "metal_chain": chain.name,
                        "metal_resi": res.seqid.num,
                    })
        return out

    @staticmethod
    def _iter_cofactor_params(summary: dict, structure: gemmi.Structure) -> list[dict]:
        """For each cofactor (FAD, NAD, HEM, PLP, …), emit one view per
        instance found in the structure."""
        cofactors = summary.get("cofactors") or []
        if not cofactors:
            return []
        codes = {entry["id"] for entry in cofactors}
        out: list[dict] = []
        for chain in structure[0]:
            for res in chain:
                if res.name in codes:
                    out.append({
                        "cofactor_resn": res.name,
                        "cofactor_chain": chain.name,
                        "cofactor_resi": res.seqid.num,
                    })
        return out

    @staticmethod
    def _iter_glycan_params(summary: dict, structure: gemmi.Structure) -> list[dict]:
        """For each glycan residue listed in summary.glycans, emit one view
        per residue instance. summary.glycans is intended to enumerate the
        bound saccharide units (NAG, BGC, MAN, FUC, …) that protein-inspect
        treats as ligand-like for analysis. The view zooms to each unit's
        protein contact and labels both sides."""
        glycans = summary.get("glycans") or []
        if not glycans:
            return []
        codes = {entry.get("id") for entry in glycans if entry.get("id")}
        out: list[dict] = []
        for chain in structure[0]:
            for res in chain:
                if res.name in codes:
                    out.append({
                        "glycan_resn": res.name,
                        "glycan_chain": chain.name,
                        "glycan_resi": res.seqid.num,
                    })
        return out

    @staticmethod
    def _iter_na_chain_params(summary: dict, structure: gemmi.Structure) -> list[dict]:
        """One view per nucleic-acid chain present in the assembly."""
        from protein_inspect.features import DNA_BASES, RNA_BASES, _polymer_kind  # local import to dodge cycles
        out: list[dict] = []
        for chain in structure[0]:
            residues = {r.name for r in chain}
            kind = _polymer_kind(residues)
            if kind in ("dna", "rna"):
                out.append({"na_chain": chain.name})
        return out

    @staticmethod
    def _iter_peptide_chain_params(summary: dict, structure: gemmi.Structure) -> list[dict]:
        """One view per detected peptide-ligand chain (short polymer-protein
        chain that is *not* the main protein). summary.peptide_ligands is
        populated by features.py:extract_peptide_ligands."""
        peptides = summary.get("peptide_ligands") or []
        return [{"peptide_chain": p["chain"]} for p in peptides]

    @staticmethod
    def _iter_vicinal_disulfide_params(summary: dict) -> list[dict]:
        out: list[dict] = []
        for d in summary.get("disulfides") or []:
            if d.get("type") != "vicinal":
                continue
            chains = d.get("chains") or ["A"]
            chain = chains[0]
            r1, r2 = d["residues"]   # e.g. "CYS187", "CYS188"
            try:
                resi_a = int("".join(c for c in r1 if c.isdigit()))
                resi_b = int("".join(c for c in r2 if c.isdigit()))
            except ValueError:
                continue
            lo, hi = sorted([resi_a, resi_b])
            out.append({"chain": chain, "resi_a": lo, "resi_b": hi})
        return out


# ─────────── orchestrator ───────────

def plan_for_summary(summary: dict, structure: gemmi.Structure, output_dir: Path,
                     args: dict | None = None) -> dict:
    """End-to-end: run decision engine, expand view requests, return everything
    needed to populate summary.flags + summary.visual + actually render."""
    engine = DecisionEngine()
    decision_out = engine.run(summary, args=args)
    planner = RenderPlanner()
    plan = planner.expand(decision_out["view_requests"], summary, structure, output_dir)
    return {
        "flags": decision_out["flags"],
        "rule_ids_fired": decision_out["rule_ids_fired"],
        "render_plan": plan,
    }
