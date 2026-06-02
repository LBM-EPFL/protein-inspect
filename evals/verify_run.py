"""Post-hoc sanity check for an eval run.

Run after `run_eval.py` completes (or at any checkpoint) to verify nothing
silently went wrong. Checks each (pdb, condition):

  - state.json status is "scored"
  - response file exists, non-trivially long, and was not truncated at
    max_tokens (checks the cached `stop_reason`)
  - extract JSON is parseable and has expected top-level keys
  - score JSON is parseable, total in valid range, scores sum correctly
  - condition C: at least one image file actually exists in the materials
    views dir for this PDB
  - condition A: prompt didn't accidentally end up empty after truncation

Outputs `verify_summary.md` in the run dir + exit 0 if clean / 1 if issues.

Usage:
    uv run python evals/verify_run.py <run-dir>
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).parent.parent
MATERIALS_DIR = ROOT / "evals" / "materials"


def check_run(run_dir: Path) -> tuple[list[str], list[str], dict]:
    """Returns (errors, warnings, summary_stats)."""
    errors: list[str] = []
    warnings: list[str] = []

    state_path = run_dir / "state.json"
    if not state_path.exists():
        return [f"no state.json in {run_dir}"], [], {}
    state = json.loads(state_path.read_text())
    items = state.get("items", [])
    if not items:
        return ["state.json has no items"], [], {}

    by_status = Counter(it["status"] for it in items)
    summary = {
        "n_items": len(items),
        "by_status": dict(by_status),
        "n_failed": by_status.get("failed", 0),
        "n_scored": by_status.get("scored", 0),
    }

    responses_dir = run_dir / "responses"
    extracts_dir = run_dir / "extracts"
    scores_dir = run_dir / "scores"
    cache_dir = run_dir / "cache"

    for it in items:
        pdb = it["pdb"]
        cond = it["condition"]
        tag = f"{pdb}/{cond}"
        status = it["status"]

        if status == "failed":
            errors.append(f"[{tag}] status=failed: {it.get('error', '')[:200]}")
            continue
        if status != "scored":
            warnings.append(f"[{tag}] incomplete (status={status})")
            continue

        # Response file checks
        resp_path = responses_dir / f"{pdb}_{cond}.txt"
        if not resp_path.exists():
            errors.append(f"[{tag}] response file missing")
            continue
        resp_text = resp_path.read_text()
        if len(resp_text) < 300:
            errors.append(f"[{tag}] response suspiciously short ({len(resp_text)} chars)")

        # Truncation check (via cached `stop_reason`)
        cache_hits = list(cache_dir.glob("*.json"))
        truncated = _check_truncation(resp_text, cache_hits)
        if truncated:
            warnings.append(f"[{tag}] response stop_reason={truncated} — may be max_tokens-truncated")

        # Extract JSON
        ex_path = extracts_dir / f"{pdb}_{cond}.json"
        if not ex_path.exists():
            errors.append(f"[{tag}] extract file missing")
        else:
            try:
                ex = json.loads(ex_path.read_text())
                required_keys = ["identity", "oligomer", "fold_class", "active_site",
                                  "cofactors_metals_ligands", "notable_features",
                                  "inferences_marked_as_inference"]
                missing = [k for k in required_keys if k not in ex]
                if missing:
                    warnings.append(f"[{tag}] extract missing keys: {missing}")
            except json.JSONDecodeError as e:
                errors.append(f"[{tag}] extract JSON malformed: {e}")

        # Score JSON
        sc_path = scores_dir / f"{pdb}_{cond}.json"
        if not sc_path.exists():
            errors.append(f"[{tag}] score file missing")
        else:
            try:
                sc = json.loads(sc_path.read_text())
                final = sc.get("final_score")
                raw = sc.get("raw_total")
                penalty = sc.get("penalty_total")
                if final is None:
                    errors.append(f"[{tag}] score has no final_score")
                elif not isinstance(final, (int, float)):
                    errors.append(f"[{tag}] final_score not numeric: {final!r}")
                elif final < -20 or final > 13:
                    warnings.append(f"[{tag}] final_score out of expected range [-20, 13]: {final}")
                # Consistency check: raw + penalty should equal final
                if raw is not None and penalty is not None and final is not None:
                    if abs((raw + penalty) - final) > 0.5:
                        errors.append(f"[{tag}] arithmetic inconsistency: raw {raw} + penalty {penalty} != final {final}")
                # Per-category bounds
                cat_max = {"identity": 2, "oligomer": 1, "fold_class": 2,
                           "active_site": 3, "cofactors_metals_ligands": 2,
                           "notable_features": 2, "inference_hygiene": 1}
                for k, mx in cat_max.items():
                    pts = (sc.get("scores", {}).get(k) or {}).get("pts")
                    if pts is None:
                        warnings.append(f"[{tag}] score missing category {k}")
                    elif pts < 0 or pts > mx:
                        errors.append(f"[{tag}] {k} pts={pts} out of [0, {mx}]")
            except json.JSONDecodeError as e:
                errors.append(f"[{tag}] score JSON malformed: {e}")

        # Condition C: verify images were available when the prompt was built
        if cond == "C":
            views_dir = MATERIALS_DIR / pdb / "views"
            if not views_dir.exists():
                errors.append(f"[{tag}] condition C but no views dir at {views_dir}")
            else:
                n_pngs = len(list(views_dir.glob("*.png")))
                if n_pngs == 0:
                    errors.append(f"[{tag}] condition C but views dir empty — image refs in prompt were broken")
                elif n_pngs < 3:
                    warnings.append(f"[{tag}] condition C had only {n_pngs} views — fewer than expected")

        # Condition A: verify the CIF content actually made it into the prompt
        if cond == "A":
            # We can spot-check by reading the cached response — if the model
            # complains "no structure data provided" we have a leak
            if "no structure" in resp_text.lower()[:1000] or "no materials" in resp_text.lower()[:1000]:
                warnings.append(f"[{tag}] condition A response complains about missing structure — verify prompt assembly")

    summary["n_errors"] = len(errors)
    summary["n_warnings"] = len(warnings)
    return errors, warnings, summary


def _check_truncation(resp_text: str, cache_files: list[Path]) -> str | None:
    """Look for the cached raw call result whose 'result' matches resp_text;
    if its stop_reason isn't end_turn, flag it. Best-effort — returns None
    if we can't determine.
    """
    target = resp_text.strip()[:200]
    for cf in cache_files:
        try:
            d = json.loads(cf.read_text())
            if d.get("result", "").strip()[:200] == target:
                sr = d.get("stop_reason", "")
                if sr and sr != "end_turn":
                    return sr
                return None
        except (json.JSONDecodeError, OSError):
            continue
    return None


def render_report(run_dir: Path, errors: list[str], warnings: list[str], summary: dict) -> str:
    lines = [f"# Verify report: `{run_dir.name}`\n\n"]
    if not errors and not warnings:
        lines.append("✅ **All checks passed.**\n\n")
    else:
        lines.append(f"❌ {len(errors)} error(s), ⚠️  {len(warnings)} warning(s).\n\n")

    lines.append("## Stats\n\n")
    lines.append(f"- Items: {summary.get('n_items', 0)}\n")
    lines.append(f"- Scored: {summary.get('n_scored', 0)}\n")
    lines.append(f"- Failed: {summary.get('n_failed', 0)}\n")
    by_status = summary.get("by_status", {})
    if by_status:
        lines.append(f"- By status: {by_status}\n")
    lines.append("\n")

    if errors:
        lines.append("## Errors (must fix)\n\n")
        for e in errors:
            lines.append(f"- ❌ {e}\n")
        lines.append("\n")

    if warnings:
        lines.append("## Warnings (review)\n\n")
        for w in warnings:
            lines.append(f"- ⚠️  {w}\n")
        lines.append("\n")

    return "".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="verify_run")
    parser.add_argument("run_dir", help="evals/runs/<dated-dir>")
    args = parser.parse_args(argv)

    run_dir = Path(args.run_dir)
    if not run_dir.exists():
        print(f"Run dir not found: {run_dir}", file=sys.stderr)
        return 2

    errors, warnings, summary = check_run(run_dir)
    report = render_report(run_dir, errors, warnings, summary)
    print(report)
    (run_dir / "verify_summary.md").write_text(report)

    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
