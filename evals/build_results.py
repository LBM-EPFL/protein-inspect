"""Aggregate scored items from an eval run into evals/results.md.

The per-run `results.md` produced by run_eval.py is a small summary table.
This script produces the canonical top-level `evals/results.md` referenced
in PLAN.md §2.4 — with per-criterion breakdowns, the headline A/B/C/D mean
table, and per-protein scores for transparency.

Usage:
  python evals/build_results.py                              # use latest run
  python evals/build_results.py --run-dir <path>             # specific run
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent.parent
RUNS_DIR = ROOT / "evals" / "runs"
GT_DIR = ROOT / "evals" / "ground_truth"
OUT_PATH = ROOT / "evals" / "results.md"

CONDITION_DESCRIPTIONS = {
    "A": "raw mmCIF text (truncated at 80 KB)",
    "B": "protein-inspect `summary.yaml` only",
    "C": "protein-inspect `summary.yaml` + rendered PyMOL view battery",
    "D": "no materials — prior knowledge from PDB ID only (baseline)",
}

CRITERIA = [
    ("identity", 2),
    ("oligomer", 1),
    ("fold_class", 2),
    ("active_site", 3),
    ("cofactors_metals_ligands", 2),
    ("notable_features", 2),
    ("inference_hygiene", 1),
]
MAX_TOTAL = sum(m for _, m in CRITERIA)


def latest_run_dir() -> Path:
    candidates = sorted(p for p in RUNS_DIR.iterdir() if p.is_dir())
    if not candidates:
        raise SystemExit(f"No run directories under {RUNS_DIR}")
    return candidates[-1]


def load_scores(run_dir: Path) -> dict:
    """Return {pdb: {condition: score_dict}} for all scored items."""
    scores_dir = run_dir / "scores"
    out: dict[str, dict[str, dict]] = defaultdict(dict)
    for f in sorted(scores_dir.glob("*.json")):
        # Filenames are <pdb>_<condition>.json (pdb may contain underscores
        # for AFDB entries like "AF-P00558-F1" — saved as "af_p00558_A.json").
        stem = f.stem
        # The condition is always the last single uppercase letter after _
        if "_" not in stem or stem[-1] not in "ABCD" or stem[-2] != "_":
            continue
        pdb = stem[:-2]
        condition = stem[-1]
        try:
            out[pdb][condition] = json.loads(f.read_text())
        except json.JSONDecodeError:
            continue
    return dict(out)


def fmt(x: float | None, digits: int = 2) -> str:
    if x is None:
        return "—"
    return f"{x:.{digits}f}"


def render(run_dir: Path, scores: dict,
           heading: str = "# Eval results — `protein-inspect`\n\n",
           preamble: str = "",
           show_low_prior_section: bool = True,
           show_interpretation: bool = True) -> str:
    """Render a single-run results report.

    Parameters
    ----------
    heading:
        The top H1 line. When this function is called as part of a combined
        v1+v2 report we substitute a less prominent heading.
    preamble:
        Extra prose injected above the headline table — used by the combined
        report to introduce each section ("Holdout set …" / "Breadth set …").
    show_low_prior_section:
        Only meaningful for the breadth set, where many PDBs are at ceiling.
        Set False for the holdout set.
    show_interpretation:
        Whether to append the "How to read these numbers" footer. Suppress
        for the breadth half of a combined report (one footer is enough).
    """
    state = json.loads((run_dir / "state.json").read_text())
    pdbs = sorted(scores.keys(), key=str.casefold)
    conditions = ["A", "B", "C", "D"]

    lines: list[str] = []
    lines.append(heading)
    if preamble:
        lines.append(preamble + "\n\n")

    # ─── header / provenance ───
    try:
        rel = run_dir.resolve().relative_to(ROOT)
    except ValueError:
        rel = run_dir
    lines.append(f"- **Run directory**: `{rel}`\n")
    lines.append(f"- **Started**: {state.get('started', 'unknown')}\n")
    lines.append(f"- **Proteins scored**: {len(pdbs)}\n")
    lines.append(f"- **Subject model**: `claude-opus-4-7` (via `claude -p`)\n")
    lines.append(f"- **Judge model**: `claude-opus-4-7`\n")
    lines.append(f"- **Rubric**: 7 criteria, {MAX_TOTAL} points max, negative-constraint penalties (−2 each)\n\n")

    # ─── headline: per-condition mean ───
    lines.append("## Headline: mean score by condition\n\n")
    lines.append("| Condition | Materials provided | n | Mean | Median | Stdev | Min | Max |\n")
    lines.append("|---|---|---|---|---|---|---|---|\n")
    cond_finals: dict[str, list[float]] = {c: [] for c in conditions}
    for pdb in pdbs:
        for c in conditions:
            s = scores.get(pdb, {}).get(c)
            if s is not None:
                cond_finals[c].append(s.get("final_score", 0))
    for c in conditions:
        vals = cond_finals[c]
        if vals:
            mean = statistics.mean(vals)
            median = statistics.median(vals)
            stdev = statistics.stdev(vals) if len(vals) > 1 else 0.0
            lines.append(f"| **{c}** | {CONDITION_DESCRIPTIONS[c]} | {len(vals)} | "
                         f"**{fmt(mean)}** | {fmt(median)} | {fmt(stdev)} | "
                         f"{fmt(min(vals))} | {fmt(max(vals))} |\n")
        else:
            lines.append(f"| **{c}** | {CONDITION_DESCRIPTIONS[c]} | 0 | — | — | — | — | — |\n")
    lines.append(f"\n_Score range: 0 to {MAX_TOTAL} per cell; negative scores are possible when negative constraints are violated._\n\n")

    # ─── per-criterion mean by condition ───
    lines.append("## Per-criterion mean (out of category max)\n\n")
    lines.append("| Criterion | Max | A | B | C | D |\n")
    lines.append("|---|---|---|---|---|---|\n")
    for crit, mx in CRITERIA:
        row = [f"`{crit}`", str(mx)]
        for c in conditions:
            vals = []
            for pdb in pdbs:
                s = scores.get(pdb, {}).get(c)
                if s is not None:
                    pts = s.get("scores", {}).get(crit, {}).get("pts")
                    if pts is not None:
                        vals.append(pts)
            row.append(fmt(statistics.mean(vals)) if vals else "—")
        lines.append("| " + " | ".join(row) + " |\n")
    # Also a row for negative penalties
    lines.append("| _negative penalties_ | — | "
                 + " | ".join(
                     fmt(statistics.mean([
                         abs(s.get("penalty_total", 0))
                         for pdb in pdbs
                         for s in [scores.get(pdb, {}).get(c)]
                         if s is not None
                     ]) or 0)
                     for c in conditions)
                 + " |\n\n")

    # ─── delta tables: which materials help which criteria most? ───
    lines.append("## Lift from materials (mean Δ vs. baseline D)\n\n")
    lines.append("Headline lift = mean(condition) − mean(D). Positive = the materials help; "
                 "negative = the materials hurt (rare, would suggest distraction or hallucination triggered by materials).\n\n")
    lines.append("| Criterion | A − D | B − D | C − D |\n")
    lines.append("|---|---|---|---|\n")
    for crit, _ in CRITERIA:
        d_vals = [
            s.get("scores", {}).get(crit, {}).get("pts", 0)
            for pdb in pdbs
            for s in [scores.get(pdb, {}).get("D")]
            if s is not None
        ]
        d_mean = statistics.mean(d_vals) if d_vals else 0
        row = [f"`{crit}`"]
        for c in ("A", "B", "C"):
            c_vals = [
                s.get("scores", {}).get(crit, {}).get("pts", 0)
                for pdb in pdbs
                for s in [scores.get(pdb, {}).get(c)]
                if s is not None
            ]
            if c_vals:
                row.append(f"{statistics.mean(c_vals) - d_mean:+.2f}")
            else:
                row.append("—")
        lines.append("| " + " | ".join(row) + " |\n")
    # Total lift
    a_t = statistics.mean(cond_finals["A"]) if cond_finals["A"] else 0
    b_t = statistics.mean(cond_finals["B"]) if cond_finals["B"] else 0
    c_t = statistics.mean(cond_finals["C"]) if cond_finals["C"] else 0
    d_t = statistics.mean(cond_finals["D"]) if cond_finals["D"] else 0
    lines.append(f"| **total** | **{a_t - d_t:+.2f}** | **{b_t - d_t:+.2f}** | **{c_t - d_t:+.2f}** |\n\n")

    # ─── negative violations summary ───
    lines.append("## Negative-constraint violations\n\n")
    lines.append("Counts the number of (pdb, condition) cells where the response triggered at least one ground-truth negative constraint (e.g. \"must not call it a kinase\"). Lower is better.\n\n")
    lines.append("| Condition | Cells with ≥1 violation | Total violations |\n")
    lines.append("|---|---|---|\n")
    for c in conditions:
        cells_with_viol = 0
        total_viol = 0
        for pdb in pdbs:
            s = scores.get(pdb, {}).get(c)
            if s is None:
                continue
            v = s.get("negative_violations", []) or []
            if v:
                cells_with_viol += 1
                total_viol += len(v)
        lines.append(f"| **{c}** | {cells_with_viol} | {total_viol} |\n")
    lines.append("\n")

    # ─── per-protein scores ───
    lines.append("## Per-protein final scores\n\n")
    lines.append("| PDB | A | B | C | D | best |\n")
    lines.append("|---|---|---|---|---|---|\n")
    for pdb in pdbs:
        row = [pdb]
        cell_scores = []
        for c in conditions:
            s = scores.get(pdb, {}).get(c)
            if s is not None:
                v = s.get("final_score", 0)
                row.append(fmt(v, 0))
                cell_scores.append((v, c))
            else:
                row.append("—")
        best = max(cell_scores)[1] if cell_scores else "—"
        row.append(f"**{best}**")
        lines.append("| " + " | ".join(row) + " |\n")
    lines.append("\n")

    # ─── low-prior-knowledge subset ───
    # Restrict to PDBs where D (no materials) scored below the rubric ceiling.
    # This is where the eval has signal — for famous structures Claude already
    # nails the rubric from prior knowledge alone and materials can't help.
    threshold = MAX_TOTAL - 1  # treat anything ≥ 12 as "near-ceiling on prior knowledge"
    low_prior_pdbs = []
    for pdb in pdbs:
        d_score = (scores.get(pdb, {}).get("D") or {}).get("final_score")
        if d_score is not None and d_score < threshold:
            low_prior_pdbs.append((pdb, d_score))

    if low_prior_pdbs and show_low_prior_section:
        lines.append(f"## Low-prior-knowledge subset (D < {threshold})\n\n")
        lines.append(
            f"Where the eval has signal. The full-set means above mostly reflect a "
            f"ceiling effect: famous PDBs (1ubq, 6lu7, 6vxx, 1tim, …) score near "
            f"{MAX_TOTAL}/{MAX_TOTAL} regardless of materials. This subset isolates "
            f"the {len(low_prior_pdbs)} entries where Claude's prior-knowledge "
            f"baseline (condition D) leaves clear room to improve.\n\n"
        )
        lines.append("| PDB | A | B | C | D |\n|---|---|---|---|---|\n")
        sub_cond_finals = {c: [] for c in conditions}
        for pdb, _ in low_prior_pdbs:
            row = [pdb]
            for c in conditions:
                s = scores.get(pdb, {}).get(c)
                if s is not None:
                    v = s.get("final_score", 0)
                    row.append(fmt(v, 0))
                    sub_cond_finals[c].append(v)
                else:
                    row.append("—")
            lines.append("| " + " | ".join(row) + " |\n")
        lines.append("| **mean** | "
                     + " | ".join(
                         f"**{fmt(statistics.mean(sub_cond_finals[c]))}**" if sub_cond_finals[c] else "—"
                         for c in conditions
                     ) + " |\n\n")
        # subset lift
        d_sub = statistics.mean(sub_cond_finals["D"]) if sub_cond_finals["D"] else 0
        for c in ("A", "B", "C"):
            if sub_cond_finals[c]:
                lift = statistics.mean(sub_cond_finals[c]) - d_sub
                lines.append(f"- Subset lift **{c} − D** = {lift:+.2f}\n")
        lines.append("\n")

    if not show_interpretation:
        return "".join(lines)

    # ─── interpretation notes ───
    lines.append("## How to read these numbers\n\n")
    lines.append(
        "- **D (baseline)** asks Claude to reason about a PDB ID with no materials provided. "
        "This measures pure prior knowledge — for famous structures (1ubq, 6vxx, 6lu7) "
        "this is high; for obscure or recent entries it should be low.\n"
        "- **A (raw mmCIF)** tests whether Claude can extract structural facts from coordinates "
        "directly. The architectural premise of the project is that this should be the *worst* "
        "performing materials condition.\n"
        "- **B (`summary.yaml`)** is the layered semantic representation — residues with roles, "
        "ligands with SMILES, flagged features.\n"
        "- **C (`summary.yaml` + view battery)** adds the standardized PyMOL images. The lift "
        "from B → C should concentrate in spatial-gestalt criteria (`oligomer`, `fold_class`, "
        "and qualitative `notable_features`).\n\n"
    )
    lines.append("### Findings vs. the PLAN.md hypothesis\n\n")
    lines.append(
        "The PLAN.md prediction was **C > B >> A**, with the A → B gap essentially everything "
        "and the B → C gap concentrated in spatial criteria. The full-set means above do not "
        "support that ranking: A, B, C, and D all cluster within ~0.5 points. Two structural "
        "reasons explain why, and both are signal-relevant:\n\n"
        "1. **Ceiling effect from famous PDBs.** The eval set is biased toward well-studied "
        "structures (1ubq, 6lu7, 6vxx, 1tim, 4hhb, …). Claude already gets ~13/13 on these "
        "from the PDB ID alone — there is no headroom for materials to help. The "
        "low-prior-knowledge subset above isolates the cases where the eval *does* have signal.\n"
        "2. **Judge sees the same prior knowledge.** The judge (also Opus 4.7) reads the response "
        "AND has full prior knowledge of the structure. A response that says \"this is ubiquitin\" "
        "satisfies the rubric whether the reasoning came from materials or memorization. To "
        "separate the two, the eval would need to either swap to a sealed-knowledge judge or "
        "use only PDBs that postdate the model's training cutoff.\n\n"
        "Both are real limitations of v1 of the eval. They should be addressed before any "
        "stronger headline claim is made in the marketplace README.\n"
    )

    return "".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Aggregate eval scores into evals/results.md. With both "
                    "--run-dir (holdout) and --breadth-run-dir (v1 famous-PDB set), "
                    "produces a two-section report with the holdout as the headline."
    )
    ap.add_argument("--run-dir", default=None,
                    help="Run directory under evals/runs/. Defaults to most recent.")
    ap.add_argument("--breadth-run-dir", default=None,
                    help="Optional second run dir for the v1 breadth (famous-PDB) set. "
                         "When provided, the report becomes a combined report with the "
                         "holdout set as the headline.")
    ap.add_argument("--out", default=str(OUT_PATH),
                    help=f"Output markdown path (default: {OUT_PATH.relative_to(ROOT)})")
    args = ap.parse_args()

    run_dir = Path(args.run_dir) if args.run_dir else latest_run_dir()
    if not run_dir.exists():
        raise SystemExit(f"Run directory does not exist: {run_dir}")

    scores = load_scores(run_dir)
    if not scores:
        raise SystemExit(f"No scores found in {run_dir / 'scores'}")

    if args.breadth_run_dir:
        breadth_dir = Path(args.breadth_run_dir)
        if not breadth_dir.exists():
            raise SystemExit(f"Breadth run directory does not exist: {breadth_dir}")
        breadth_scores = load_scores(breadth_dir)
        if not breadth_scores:
            raise SystemExit(f"No scores found in {breadth_dir / 'scores'}")

        # Combined report — holdout first (headline), then breadth.
        top_heading = "# Eval results — `protein-inspect`\n\n"
        holdout_preamble = (
            "## Holdout set — headline\n\n"
            "Entries released **after 2026-01-31**, postdating Claude Opus 4.7's "
            "training cutoff. The model can't have memorized these structures, so "
            "the lift from materials (A / B / C vs the D baseline) reflects the "
            "tool's actual contribution rather than recall of famous PDBs."
        )
        holdout_section = render(
            run_dir, scores,
            heading=top_heading,
            preamble=holdout_preamble,
            show_low_prior_section=False,
            show_interpretation=False,
        )

        breadth_preamble = (
            "## Breadth set — pre-cutoff PDBs (reference, ceiling-limited)\n\n"
            "29 well-studied structures, mostly deposited well before the training "
            "cutoff. The headline means here are squashed near the rubric ceiling "
            "because Claude already knows these proteins from prior knowledge alone. "
            "Treat as a *breadth check* (does the tool work on the famous targets?), "
            "not a lift measurement. The low-prior-knowledge subset below isolates "
            "the entries where the eval still has signal."
        )
        breadth_section = render(
            breadth_dir, breadth_scores,
            heading="\n---\n\n# Reference: breadth set\n\n",
            preamble=breadth_preamble,
            show_low_prior_section=True,
            show_interpretation=True,
        )

        out_text = holdout_section + breadth_section
        Path(args.out).write_text(out_text)
        print(f"Wrote {args.out} ({len(out_text)} chars, holdout n={len(scores)}, breadth n={len(breadth_scores)})")
    else:
        out_text = render(run_dir, scores)
        Path(args.out).write_text(out_text)
        print(f"Wrote {args.out} ({len(out_text)} chars, {len(scores)} proteins)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
