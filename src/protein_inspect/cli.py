"""Command-line entry point and top-level pipeline orchestrator.

Wires together: features → decision engine → planner → optional render →
schema validation → summary.yaml emission. Also fetches the deposition title
from the RCSB Data API so `narrative` is populated for PDB-fetched entries
(instead of the `no_narrative` rule firing unnecessarily).

Usage:
    protein-inspect 1mbn                                      # YAML only
    protein-inspect 1mbn --render-views                       # + canonical PyMOL views
    protein-inspect /path/to/design.pdb --render-views        # local file
    protein-inspect 1kxj --motif His153,Asp166,Ser142 --render-views
    protein-inspect /path/design.pdb --use-merizo             # ML domain segmentation
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
import urllib.request
import urllib.error
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

from protein_inspect import __version__, features as F
from protein_inspect.decision import plan_for_summary
from protein_inspect.pymol_runner import PyMOLRunner, is_pymol_available

PKG_ROOT = Path(__file__).parent.parent.parent
SCHEMA_PATH = PKG_ROOT / "schema" / "summary.schema.json"

log = logging.getLogger("protein_inspect")


# ─────────── narrative from RCSB ───────────

def fetch_rcsb_title(pdb_id: str, timeout: float = 5.0) -> str | None:
    """Fetch the `struct.title` field from the RCSB Data API. Returns None if
    the entry doesn't exist or the API is unreachable — caller treats null
    narrative as a designed/unannotated structure."""
    url = f"https://data.rcsb.org/rest/v1/core/entry/{pdb_id.upper()}"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("struct", {}).get("title")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, OSError):
        return None


# ─────────── pipeline ───────────

def run_pipeline(
    pdb_id_or_path: str,
    out_dir: Path,
    render_views: bool = False,
    motif: str | None = None,
    use_merizo: bool = False,
    fetch_narrative: bool = True,
) -> dict:
    """End-to-end: extract → decide → plan → optional render → emit summary.yaml.

    Returns the final summary dict. Side effects:
      - writes <out_dir>/summary.yaml
      - copies coordinates to <out_dir>/<entry>.<ext>
      - if render_views: writes PNGs to <out_dir>/views/
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    views_dir = out_dir / "views"

    log.info("Extracting features from %s", pdb_id_or_path)
    summary = F.extract_all(pdb_id_or_path, motif=motif, use_merizo=use_merizo)

    # Fetch narrative for deposited structures (improves analysis prompt's first section)
    if fetch_narrative and summary["provenance"]["source"] == "rcsb":
        is_4char_id = Path(pdb_id_or_path).exists() is False and len(pdb_id_or_path) == 4
        if is_4char_id:
            title = fetch_rcsb_title(pdb_id_or_path)
            if title:
                summary["narrative"] = title
                log.info("RCSB title: %s", title[:80])

    # Get the structure for planner expansion + (optional) PyMOL load
    struct, struct_path = F.fetch_structure(pdb_id_or_path)

    # Copy coordinates into the output directory and reference via coords_ref
    src = Path(struct_path)
    coords_dest = out_dir / f"{summary['entry']}{src.suffix}"
    if coords_dest != src:
        shutil.copyfile(src, coords_dest)
    suffix = src.suffix.lstrip(".").lower()
    fmt = suffix if suffix in {"bcif", "cif", "pdb"} else "cif"
    summary["coords_ref"] = {"path": str(coords_dest), "format": fmt}

    # Run the decision engine and planner
    log.info("Running decision engine")
    plan_out = plan_for_summary(summary, struct, views_dir,
                                 args={"motif": motif})
    if plan_out["flags"]:
        summary["flags"] = plan_out["flags"]
    log.info("Rules fired: %s", ", ".join(plan_out["rule_ids_fired"]))

    # Optional rendering
    if render_views:
        if not is_pymol_available(timeout=1.0):
            log.warning("PyMOL not running on port 9880 — skipping render. "
                        "Start PyMOL with the claudemol plugin to enable views.")
            summary["visual"] = None
        else:
            log.info("Rendering %d view(s) via PyMOL", len(plan_out["render_plan"]))
            runner = PyMOLRunner()
            runner.connect()
            try:
                runner.load_structure(str(struct_path), obj_name="obj")
                results = runner.render_plan(plan_out["render_plan"], obj_name="obj")
            finally:
                runner.disconnect()

            rendered = []
            for r in results:
                if r["ok"]:
                    entry = {"name": r["name"], "path": r["path"], "ray": True}
                    if r.get("details"):
                        entry["details"] = r["details"]
                    rendered.append(entry)
            summary["visual"] = {
                "views_dir": str(views_dir),
                "battery_version": "1.1",
                "rendered": rendered,
            }
            n_failed = sum(1 for r in results if not r["ok"])
            if n_failed:
                log.warning("%d view(s) failed to render — see logs", n_failed)

            # Build a labeled grid montage of all successfully-rendered views.
            # See src/protein_inspect/montage.py for the rationale: the Claude
            # Code CLI silently caps @path attachments at 3 images per prompt,
            # and the full view battery is usually 5–9 views. Composing them
            # into a single grid PNG with view-name title bars bypasses the
            # cap (one attachment) while keeping all views legible.
            try:
                from protein_inspect.montage import build_montage
                montage_info = build_montage(views_dir, out_dir / "montage.png")
                summary["visual"]["montage"] = montage_info
                log.info("Wrote montage: %d panels, grid %dx%d, %dx%d px total",
                         montage_info["n_panels"], *montage_info["grid"],
                         *montage_info["total_size"])
            except Exception as e:
                log.warning("Montage build failed: %s", e)

    # Validate before writing
    log.info("Validating summary against schema v%s",
              summary["schema_version"])
    schema = json.loads(SCHEMA_PATH.read_text())
    Draft202012Validator(schema).validate(summary)

    # Write summary.yaml
    summary_path = out_dir / "summary.yaml"
    with open(summary_path, "w") as f:
        yaml.safe_dump(summary, f, sort_keys=False, default_flow_style=False,
                       indent=2, width=120)
    log.info("Wrote %s", summary_path)
    return summary


# ─────────── argparse + main ───────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="protein-inspect",
        description="Turn a PDB ID or local structure file into a layered semantic "
                    "representation (summary.yaml + canonical PyMOL views).",
    )
    p.add_argument("target",
                   help="4-letter PDB ID (e.g. 1mbn) OR path to a local "
                        ".pdb/.cif/.bcif structure file")
    p.add_argument("--out", "-o", default=None,
                   help="Output directory (default: ./<entry>/)")
    p.add_argument("--render-views", action="store_true",
                   help="Render the canonical PyMOL view battery (requires PyMOL "
                        "running with the claudemol socket plugin on port 9880)")
    p.add_argument("--motif", default=None,
                   help="Comma-separated residues to highlight as a motif "
                        "(e.g. His153,Asp166,Ser142)")
    p.add_argument("--use-merizo", action="store_true",
                   help="Use Merizo for ML-based domain segmentation. Merizo "
                        "must be installed manually (see README). Default "
                        "uses CATH (deposited) + length heuristic (everything else).")
    p.add_argument("--no-narrative", action="store_true",
                   help="Skip the RCSB title fetch (offline mode)")
    p.add_argument("--quiet", "-q", action="store_true",
                   help="Suppress info logs")
    p.add_argument("--version", action="version",
                   version=f"protein-inspect {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    # Resolve output directory
    if args.out:
        out_dir = Path(args.out)
    else:
        if Path(args.target).exists():
            stem = Path(args.target).stem
        else:
            stem = args.target.lower()
        out_dir = Path.cwd() / stem

    try:
        run_pipeline(
            args.target,
            out_dir=out_dir,
            render_views=args.render_views,
            motif=args.motif,
            use_merizo=args.use_merizo,
            fetch_narrative=not args.no_narrative,
        )
    except FileNotFoundError as e:
        log.error("File not found: %s", e)
        return 2
    except ValueError as e:
        log.error("Invalid input: %s", e)
        return 2
    except Exception as e:
        log.error("Pipeline failed: %s", e, exc_info=not args.quiet)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
