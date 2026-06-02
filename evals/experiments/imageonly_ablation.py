"""Images-only ablation (condition E).

Tests how much Claude can reason about a de novo designed protein when
it sees ONLY the PyMOL view battery — no PDB ID, no title, no YAML, no
header information. Compares against full-materials (C) and no-materials
baseline (D) on the same protein with the same rubric.

Conditions:
  D — no materials at all (just the rubric question)
  E — image battery only (no identifier, no metadata, no YAML)
  C — image battery + protein-inspect YAML + PDB/ModelArchive ID

Outputs:
  evals/experiments/imageonly_ablation_results.md — side-by-side table.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent.parent
GT_DIR = ROOT / "evals" / "ground_truth_v3"
PROMPTS_DIR = ROOT / "evals" / "prompts"
OUT_DIR = ROOT / "evals" / "experiments"

SUBJECT_MODEL = "claude-opus-4-7"
JUDGE_MODEL = "claude-opus-4-7"
CALL_TIMEOUT = 600

# Targets: (display_name, materials_dir, [optional fake-id-to-pass-as-D])
TARGETS = [
    {
        "id": "9V4L",
        "label": "PDB 9V4L — de novo Zn-binding designed protein",
        "materials_dir": Path("/tmp/designs_out/9V4L"),
        "fake_id_for_d": "9V4L",
    },
    {
        "id": "ma-rgcer",
        "label": "ModelArchive ma-rgcer — de novo coiled-coil",
        "materials_dir": Path("/tmp/ma_designs_out/ma-rgcer"),
        "fake_id_for_d": "ma-rgcer",
    },
]

SYSTEM_PROMPT = (PROMPTS_DIR / "system.md").read_text().strip()
EXTRACT_TEMPLATE = (PROMPTS_DIR / "judge_extract.md").read_text()
SCORE_TEMPLATE = (PROMPTS_DIR / "judge_score.md").read_text()

QUESTION_WITH_ID = (PROMPTS_DIR / "question.md").read_text()

# Custom question template for condition E (no PDB ID).
QUESTION_NO_ID = """# Protein structure analysis — image-only inspection

You are shown a small set of standardized PyMOL views of a protein structure.
You have NO identifier, no title, no annotation, no sequence. Reason ONLY
from what the images show you.

{materials_section}

Provide a structured analysis in **400–800 words**, with these section
headers in this order:

### 1. Identity & function
Identify the protein only if the images give unambiguous visual cues (very
unusual; usually not possible from images alone). Otherwise write "unknown
from images alone" and explain what fold-class hints the images carry.

### 2. Macromolecular composition
What polymer types are present (protein chains, nucleic acid, glycans)?
Count chains and estimate sizes from the cartoons.

### 3. Quaternary structure
Oligomeric state (monomer, dimer, trimer, etc.), symmetry if any.

### 4. Fold class
Name the fold(s) — be specific (β-grasp, TIM barrel, Rossmann, Ig fold,
4-helix bundle, coiled coil, 7TM bundle, etc.). Cite specific image features
that support each claim.

### 5. Active site / catalytic mechanism
If you see a clear binding pocket / metal / ligand in the images, describe
it. If not, write "no active-site features visible in these views".

### 6. Cofactors, metals, ligands
List what is visibly bound (metals as colored spheres, small molecules as
sticks). Do NOT invent ligands that are not shown.

### 7. Notable structural features
Disulfides (visible as connected yellow sticks), aromatic clusters,
hydrophobic surface patches (visible in the surface view), confidence
gradients (visible in the B-factor / pLDDT view).

### 8. Hypotheses & inferences
Mark this section explicitly as inference. Be conservative — images give
you fold class and topology, but rarely identity or mechanism.

If you don't know something, write "unknown from the available images"
rather than fabricating.
"""

QUESTION_NO_MATERIALS = """# Protein structure analysis — identifier only

You are asked about the protein with identifier **{pdb_id}**. You have no
materials. Answer from prior knowledge if any.

Provide a structured analysis in **400–800 words**, with the section
headers below. If you have no information, write "unknown — no prior
knowledge of this identifier" for each section.

### 1. Identity & function
### 2. Macromolecular composition
### 3. Quaternary structure
### 4. Fold class
### 5. Active site / catalytic mechanism
### 6. Cofactors, metals, ligands
### 7. Notable structural features
### 8. Hypotheses & inferences
"""


def call_claude(prompt: str, system: str | None = None, model: str = SUBJECT_MODEL) -> dict:
    """Run `claude -p` and return the parsed JSON output."""
    args = ["claude", "-p", "--model", model, "--output-format", "json",
            "--no-session-persistence"]
    if system:
        args.extend(["--system-prompt", system])
    args.append(prompt)
    proc = subprocess.run(args, capture_output=True, text=True, timeout=CALL_TIMEOUT)
    if proc.returncode != 0:
        raise RuntimeError(
            f"claude -p failed (rc={proc.returncode}): "
            f"stderr={proc.stderr[:200]!r} stdout={proc.stdout[:200]!r}"
        )
    return json.loads(proc.stdout)


def parse_json(text: str) -> dict:
    """Strip markdown fences if any, parse JSON."""
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"\s*```\s*$", "", text)
    return json.loads(text)


def build_image_refs(views_dir: Path) -> str:
    return " ".join(f"@{p}" for p in sorted(views_dir.glob("*.png")))


def build_prompt(condition: str, target: dict) -> str:
    """Return the subject prompt for (target, condition)."""
    views_dir = target["materials_dir"] / "views"
    summary_path = target["materials_dir"] / "summary.yaml"

    if condition == "D":
        return QUESTION_NO_MATERIALS.replace("{pdb_id}", target["fake_id_for_d"])

    if condition == "E":
        materials_section = (
            "**CANONICAL VIEW BATTERY (PyMOL-rendered) — no other context provided:**\n\n"
            + build_image_refs(views_dir)
        )
        return QUESTION_NO_ID.replace("{materials_section}", materials_section)

    if condition == "C":
        yaml_text = summary_path.read_text()
        materials_section = (
            "**STRUCTURED SUMMARY (machine-extracted features from `protein-inspect`):**\n\n"
            "```yaml\n" + yaml_text + "\n```\n\n"
            "**CANONICAL VIEW BATTERY (PyMOL-rendered):**\n\n"
            + build_image_refs(views_dir)
        )
        return QUESTION_WITH_ID.replace("{pdb_id}", target["id"]).replace(
            "{materials_section}", materials_section)

    raise ValueError(f"unknown condition {condition!r}")


def score_one(target: dict, condition: str, out_dir: Path) -> dict:
    """Run subject + extract + score for one (target, condition). Returns
    {response, extracted, score, cost} dict."""
    label = f"{target['id']}/{condition}"
    print(f"  ─── {label} ───")

    prompt = build_prompt(condition, target)
    (out_dir / f"prompt_{target['id']}_{condition}.txt").write_text(prompt)

    # 1) Subject
    t0 = time.time()
    subj = call_claude(prompt, system=SYSTEM_PROMPT, model=SUBJECT_MODEL)
    response_text = subj["result"]
    (out_dir / f"response_{target['id']}_{condition}.txt").write_text(response_text)
    cost_subject = subj.get("total_cost_usd", 0)
    print(f"     subject: {time.time()-t0:.1f}s, ${cost_subject:.3f}")

    # 2) Judge extract
    extract_prompt = EXTRACT_TEMPLATE.replace("{response}", response_text)
    ex = call_claude(extract_prompt, model=JUDGE_MODEL)
    extracted = parse_json(ex["result"])
    (out_dir / f"extract_{target['id']}_{condition}.json").write_text(
        json.dumps(extracted, indent=2))
    cost_extract = ex.get("total_cost_usd", 0)

    # 3) Judge score
    gt = (GT_DIR / f"{target['id']}.yaml").read_text()
    score_prompt = (SCORE_TEMPLATE
                    .replace("{ground_truth_yaml}", gt)
                    .replace("{extracted_json}", json.dumps(extracted, indent=2))
                    .replace("{response}", response_text))
    sc = call_claude(score_prompt, model=JUDGE_MODEL)
    score = parse_json(sc["result"])
    (out_dir / f"score_{target['id']}_{condition}.json").write_text(
        json.dumps(score, indent=2))
    cost_score = sc.get("total_cost_usd", 0)

    return {
        "response": response_text,
        "extracted": extracted,
        "score": score,
        "cost": cost_subject + cost_extract + cost_score,
    }


def main() -> int:
    out_dir = OUT_DIR / "imageonly_ablation_run"
    out_dir.mkdir(parents=True, exist_ok=True)

    results: dict[str, dict[str, dict]] = {}

    for target in TARGETS:
        print(f"=== {target['label']} ===")
        results[target["id"]] = {}
        for condition in ("D", "E", "C"):
            try:
                results[target["id"]][condition] = score_one(target, condition, out_dir)
            except Exception as e:
                print(f"     FAIL {target['id']}/{condition}: {e}")
                results[target["id"]][condition] = {"error": str(e)}

    # Markdown report
    lines: list[str] = []
    lines.append("# Images-only ablation results\n\n")
    lines.append("Run on " + time.strftime("%Y-%m-%d %H:%M %Z") + "\n\n")
    lines.append("Conditions:\n")
    lines.append("- **D** — no materials, identifier only (\"what is X?\")\n")
    lines.append("- **E** — view battery only, no identifier, no YAML, no header\n")
    lines.append("- **C** — full materials: identifier + YAML + view battery\n\n")

    lines.append("## Headline scores (per protein, per condition)\n\n")
    lines.append("| Target | D | E | C |\n|---|---|---|---|\n")
    for target in TARGETS:
        tid = target["id"]
        row = [target["label"]]
        for cond in ("D", "E", "C"):
            r = results[tid].get(cond, {})
            if "score" in r:
                row.append(f"{r['score'].get('final_score', '?')}/13")
            else:
                row.append("FAIL")
        lines.append("| " + " | ".join(row) + " |\n")

    lines.append("\n## Per-criterion breakdown\n\n")
    criteria = ["identity", "oligomer", "fold_class", "active_site",
                "cofactors_metals_ligands", "notable_features", "inference_hygiene"]
    for target in TARGETS:
        tid = target["id"]
        lines.append(f"### {target['label']}\n\n")
        lines.append("| Criterion | Max | D | E | C |\n|---|---|---|---|---|\n")
        max_pts = {"identity": 2, "oligomer": 1, "fold_class": 2, "active_site": 3,
                   "cofactors_metals_ligands": 2, "notable_features": 2,
                   "inference_hygiene": 1}
        for c in criteria:
            row = [f"`{c}`", str(max_pts[c])]
            for cond in ("D", "E", "C"):
                r = results[tid].get(cond, {})
                if "score" in r:
                    pts = r["score"].get("scores", {}).get(c, {}).get("pts")
                    row.append(str(pts) if pts is not None else "—")
                else:
                    row.append("FAIL")
            lines.append("| " + " | ".join(row) + " |\n")
        lines.append("\n")

    # Cost
    total_cost = sum(
        r.get("cost", 0) for t in results.values() for r in t.values()
    )
    lines.append(f"\nTotal spend: **${total_cost:.2f}** across {sum(1 for t in results.values() for r in t.values() if 'score' in r)} cells.\n")

    (out_dir / "../imageonly_ablation_results.md").write_text("".join(lines))
    print(f"\nWrote {out_dir.parent / 'imageonly_ablation_results.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
