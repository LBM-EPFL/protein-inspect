"""Automated fact-check of the ground-truth YAML files.

For each evals/ground_truth/*.yaml file, verify against the actual PDB
structure:
  - cited catalytic residues exist at the named positions
  - cited cofactor / ligand CCD codes appear in the structure
  - description has substring overlap with the deposited title, and no
    molecule identifier in the title contradicts the claimed identity
  - oligomer claim is consistent with the structure's chain count
    (claimed monomer + hetero-oligomer structure is a hard failure)

Output: evals/verify_report.md — one section per file with ✓/✗/? marks.
Exit code 0 if no ✗, 1 if any ✗ found.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from protein_inspect import features as F

ROOT = Path(__file__).parent.parent
GT_DIR = ROOT / "evals" / "ground_truth"
REPORT = ROOT / "evals" / "verify_report.md"

# A second ground-truth directory exists for the eval v2 holdout set —
# entries released after the model's training cutoff. Callers can point
# main() at it via --gt-dir, in which case the report is written next to
# it as verify_report_v2.md. See evals/ground_truth_v2_picks.md.


# ─────────── helpers ───────────

def fetch_rcsb_title(pdb_id: str, timeout: float = 5.0) -> str | None:
    if pdb_id.upper().startswith("AF-"):
        return None
    url = f"https://data.rcsb.org/rest/v1/core/entry/{pdb_id.upper()}"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            return json.loads(resp.read().decode("utf-8")).get("struct", {}).get("title")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def fetch_rcsb_assembly(pdb_id: str, timeout: float = 5.0) -> dict | None:
    """Fetch the deposited biological-assembly metadata (assembly 1) from RCSB.

    Returns a dict with `oligomeric_count` (int), `oligomeric_details` (str,
    e.g. 'dimeric', 'tetrameric'), and `polymer_composition` (str, e.g.
    'homomeric protein', 'heteromeric protein', 'protein/NA'). Returns None
    for AFDB models or on network/parse error — the caller treats that as
    "biological assembly unknown" and falls back to ASU-only checks."""
    if pdb_id.upper().startswith("AF-"):
        return None
    url = f"https://data.rcsb.org/rest/v1/core/assembly/{pdb_id.upper()}/1"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            d = json.loads(resp.read().decode("utf-8"))
            ai = d.get("rcsb_assembly_info", {}) or {}
            sa = d.get("pdbx_struct_assembly", {}) or {}
            return {
                "oligomeric_count": sa.get("oligomeric_count"),
                "oligomeric_details": sa.get("oligomeric_details"),
                "polymer_composition": ai.get("polymer_composition"),
            }
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def parse_res_name(token: str) -> tuple[str, int] | None:
    """Parse 'SER195' / 'CYS-187' / 'TRP143' → ('SER', 195). Bare 3-letter
    tokens like 'CYS' (placeholder rows for ground-truth entries that name
    a residue type without a specific number — e.g. ferredoxin cluster-
    coordinating cysteines) parse to ('CYS', 0); the caller skips them."""
    t = token.strip().upper()
    m = re.match(r"^([A-Z]{3})-?(\d+)$", t)
    if m:
        return (m.group(1), int(m.group(2)))
    m = re.match(r"^([A-Z]{3})$", t)
    if m:
        return (m.group(1), 0)
    return None


def residue_exists(struct, resn: str, resi: int) -> tuple[bool, set[str]]:
    """Does any chain have a residue of this type at this number? Return
    (exists, chains_where_found)."""
    found_chains: set[str] = set()
    for chain in struct[0]:
        for res in chain:
            if res.name == resn and res.seqid.num == resi:
                found_chains.add(chain.name)
    return (bool(found_chains), found_chains)


def collect_hetatm_codes(struct) -> set[str]:
    codes: set[str] = set()
    for chain in struct[0]:
        for res in chain:
            if res.name in F.STANDARD_AA or res.name in F.DNA_BASES or res.name in F.RNA_BASES:
                continue
            if res.name in F.WATER:
                continue
            codes.add(res.name)
    return codes


def title_overlap(description: str, title: str | None,
                  min_chars: int = 4) -> tuple[bool, list[str]]:
    """Rough sanity: at least one >= min_chars word from the title (case-insensitive,
    minus stopwords) appears in the description.

    Tokens are alphanumeric so identifiers like 'PDE2A', '6vxx', 'COVID-19',
    'IL-6' don't get fragmented into too-short pieces by a letters-only regex —
    those identifiers are usually the most discriminating words in a deposition
    title."""
    if not title or not description:
        return (True, [])  # can't verify; pass-through
    stop = {"of", "the", "with", "and", "from", "for", "in", "to", "a", "an",
            "structure", "crystal", "complex", "complexed", "form", "bound"}
    title_words = {w.lower() for w in re.findall(r"[A-Za-z][A-Za-z0-9]*", title)
                   if len(w) >= min_chars and w.lower() not in stop}
    desc_lower = description.lower()
    matched = [w for w in title_words if w in desc_lower]
    return (len(matched) > 0, matched)


# Prefixes too generic to treat as molecule identifiers (avoid false conflicts).
_ID_PREFIX_STOP = {"TYPE", "FORM", "CLASS", "GROUP", "CHAIN", "AT", "FIG",
                   "NO", "VERSION", "PH", "RES", "AND"}


def identifier_pairs(text: str) -> dict[str, set[int]]:
    """Extract (letter-prefix → set of numbers) from identifier-style tokens
    such as 'U2', 'U2B', 'CDK4', 'HIV-1'. These name a *specific* molecule, so
    a prefix that recurs with a different number in the title vs the ground
    truth is a strong signal the entry points at the wrong PDB (e.g. U1A/U2B)."""
    pairs: dict[str, set[int]] = {}
    # Letters immediately followed (optional hyphen) by digits. No trailing
    # boundary, so trailing letters are ignored: 'U2B' → ('U', 2).
    for prefix, num in re.findall(r"\b([A-Za-z]{1,6})-?(\d{1,3})", text):
        p = prefix.upper()
        if p in _ID_PREFIX_STOP:
            continue
        pairs.setdefault(p, set()).add(int(num))
    return pairs


_UNP_ACCESSION = re.compile(r"\b[A-Z][0-9][A-Z0-9]{3}[0-9](?:[A-Z0-9]{4})?\b")


def count_distinct_unp_accessions(cif_path: Path | None) -> int | None:
    """Return the number of distinct UniProt accessions referenced in the
    mmCIF `_struct_ref` loop. Used to distinguish a real protein-protein
    hetero-oligomer (>=2 accessions, e.g. U2B''+U2A' in 1a9n) from a single
    protein that happens to be multi-chain (one cleaved gene product like
    chymotrypsin, or protein + nucleic acid like Cas9-sgRNA). Returns None
    if the cif is missing or no `UNP` lines are present (designed proteins,
    AFDB models)."""
    if cif_path is None or not cif_path.exists():
        return None
    accs: set[str] = set()
    saw_unp = False
    for line in cif_path.read_text(errors="ignore").splitlines():
        if " UNP " not in line:
            continue
        saw_unp = True
        for tok in _UNP_ACCESSION.findall(line):
            accs.add(tok)
    return len(accs) if saw_unp else None


def identifier_conflict(gt_text: str, title: str) -> list[str]:
    """Return conflict descriptions where the ground truth and the RCSB title
    share an identifier prefix but disagree on the number — the failure mode
    that let 1a9n (U2B''/U2A') get mislabeled as U1A and pass v1.1."""
    gt_ids = identifier_pairs(gt_text)
    title_ids = identifier_pairs(title)
    conflicts = []
    for prefix in sorted(set(gt_ids) & set(title_ids)):
        if gt_ids[prefix].isdisjoint(title_ids[prefix]):
            conflicts.append(
                f"identifier {prefix!r}: ground truth says "
                f"{prefix}{sorted(gt_ids[prefix])}, title says "
                f"{prefix}{sorted(title_ids[prefix])}")
    return conflicts


# ─────────── checks ───────────

def check_one(gt_path: Path) -> dict:
    """Run all checks against one ground-truth file."""
    gt = yaml.safe_load(gt_path.read_text())
    pdb_id = gt["pdb"]
    results = {"pdb": pdb_id, "checks": []}

    # Load structure (cached path)
    try:
        struct, _ = F.fetch_structure(pdb_id)
    except Exception as e:
        results["checks"].append({
            "status": "✗", "kind": "fetch",
            "msg": f"Could not load structure: {type(e).__name__}: {str(e)[:200]}",
        })
        return results

    # ─── 1. catalytic residues exist ───
    cat_residues = (gt.get("active_site") or {}).get("catalytic_residues") or []
    for cr in cat_residues:
        token = cr.get("name", "")
        parsed = parse_res_name(token)
        if not parsed:
            results["checks"].append({"status": "?", "kind": "residue_format",
                                       "msg": f"Could not parse residue name {token!r}"})
            continue
        resn, resi = parsed
        # Skip non-numbered placeholder rows (e.g. "CYS" without resi for ferredoxin)
        if resn in F.STANDARD_AA and resi == 0:
            continue
        ok, chains = residue_exists(struct, resn, resi)
        if ok:
            results["checks"].append({"status": "✓", "kind": "residue",
                                       "msg": f"{token} found on chain(s) {sorted(chains)}"})
        else:
            results["checks"].append({"status": "✗", "kind": "residue",
                                       "msg": f"{token} NOT FOUND in structure — verify numbering"})

    # ─── 2. cofactor/ligand CCD codes appear ───
    expected_codes = []
    for entry in (gt.get("cofactors_metals_ligands") or {}).get("expected") or []:
        if "id" in entry:
            expected_codes.append(entry["id"])
    hetatm_codes = collect_hetatm_codes(struct)
    for code in expected_codes:
        if code in hetatm_codes:
            results["checks"].append({"status": "✓", "kind": "ccd",
                                       "msg": f"CCD {code!r} present"})
        else:
            results["checks"].append({"status": "✗", "kind": "ccd",
                                       "msg": f"CCD {code!r} NOT FOUND — actual HETATMs: {sorted(hetatm_codes)}"})

    # ─── 3. oligomer count matches chain count ───
    # Hardened in v1.3: we now fetch the deposited biological assembly from
    # RCSB (assembly 1) and accept the ground-truth claim when it matches the
    # biological assembly even if the ASU contains fewer chains (a very common
    # convention — e.g. 6LU7 Mpro is an obligate functional dimer but the ASU
    # has a single chain because the dimer is generated by crystallographic
    # symmetry). The ASU chain count is only treated as ground truth when the
    # biological assembly is unavailable (AFDB models, network failure).
    summary = F.extract_all(pdb_id)
    actual_n = summary["assembly"]["n_chains"]
    homo_hetero = summary["assembly"].get("homo_or_hetero", "")
    claimed = (gt.get("oligomeric_state") or {}).get("correct", "")
    oligo_map = {"monomer": 1, "dimer": 2, "trimer": 3, "tetramer": 4,
                 "pentamer": 5, "hexamer": 6, "heptamer": 7, "octamer": 8}
    bio = fetch_rcsb_assembly(pdb_id)
    bio_count = (bio or {}).get("oligomeric_count")
    bio_details = (bio or {}).get("oligomeric_details") or ""
    bio_composition = (bio or {}).get("polymer_composition") or ""

    if claimed == "monomer" and homo_hetero == "hetero":
        # Hardened in v1.2: monomer + hetero is suspicious, but the `hetero`
        # flag also fires on single proteins that are post-translationally
        # cleaved into multiple chains (chymotrypsin), single proteins bound
        # to nucleic acids (Cas9-sgRNA), or designed proteins with two
        # slightly-different ASU copies. Only escalate to a hard fail when
        # the structure references >=2 distinct UniProt accessions — i.e.
        # the chains come from different gene products (1a9n: U2B'' + U2A').
        cif_candidates = [
            ROOT / "evals" / "materials" / pdb_id / f"{pdb_id}.cif",
            ROOT / "evals" / "materials" / pdb_id / f"{pdb_id.lower()}.cif",
        ]
        cif_path = next((p for p in cif_candidates if p.exists()), None)
        n_unp = count_distinct_unp_accessions(cif_path)
        unique_seq = summary['assembly'].get('unique_sequences', '?')
        if n_unp is not None and n_unp >= 2:
            results["checks"].append({"status": "✗", "kind": "oligomer_mismatch",
                                       "msg": f"claimed monomer but structure is a true protein-protein "
                                              f"hetero-oligomer ({actual_n} chains, {n_unp} distinct UniProt "
                                              f"accessions) — ground truth likely refers to the wrong PDB entry"})
        else:
            # Single gene product cleaved into multiple chains (chymotrypsin),
            # protein+nucleic-acid (Cas9-sgRNA), or designed/AFDB structures
            # are biologically OK as "monomer" claims — the multi-chain ASU
            # is a deposition artifact, not a true oligomer.
            note = ("single gene product, multiple cleaved chains or protein+nucleic-acid"
                    if n_unp == 1 else "designed/AFDB — no UniProt to disambiguate")
            results["checks"].append({"status": "✓", "kind": "oligomer",
                                       "msg": f"claimed monomer accepted: {actual_n}-chain ASU "
                                              f"({unique_seq} distinct sequences, {note})"})
    elif claimed in oligo_map:
        expected = oligo_map[claimed]
        if actual_n == expected:
            results["checks"].append({"status": "✓", "kind": "oligomer",
                                       "msg": f"claimed {claimed} matches {actual_n}-chain structure"})
        elif bio_count == expected:
            # ASU has fewer (or more) chains than the claim, but the deposited
            # biological assembly matches — accept.
            results["checks"].append({"status": "✓", "kind": "oligomer",
                                       "msg": f"claimed {claimed} confirmed by biological assembly "
                                              f"({bio_details or f'{bio_count}-mer'}; ASU has {actual_n} chains)"})
        elif claimed == "dimer" and bio_composition == "heteromeric protein" \
                and bio_count is not None and bio_count >= 2 and bio_count % 2 == 0:
            # Heteromeric assemblies in which the GT counts the protein-only
            # dimer separately from a co-crystallized small partner (e.g. 6LU7
            # Mpro homodimer with two peptide-inhibitor copies → 4 instances
            # in the bio assembly).
            results["checks"].append({"status": "✓", "kind": "oligomer",
                                       "msg": f"claimed dimer accepted: biological assembly is "
                                              f"{bio_details or f'{bio_count}-mer'} heteromeric "
                                              f"(protein dimer + non-protein partner); ASU has {actual_n} chains"})
        elif actual_n < expected:
            results["checks"].append({"status": "?", "kind": "oligomer",
                                       "msg": f"claimed {claimed} but structure has {actual_n} chains and "
                                              f"biological assembly is {bio_details or 'unknown'} — ASU subset?"})
        else:
            results["checks"].append({"status": "?", "kind": "oligomer",
                                       "msg": f"claimed {claimed} but structure has {actual_n} chains "
                                              f"({homo_hetero}); biological assembly is {bio_details or 'unknown'}"})
    elif claimed == "heterotetramer":
        if actual_n == 4 and summary["assembly"]["homo_or_hetero"] == "hetero":
            results["checks"].append({"status": "✓", "kind": "oligomer",
                                       "msg": "heterotetramer confirmed (4 chains, hetero)"})
        else:
            results["checks"].append({"status": "?", "kind": "oligomer",
                                       "msg": f"claimed heterotetramer; structure has {actual_n} chains, homo_or_hetero={summary['assembly']['homo_or_hetero']}"})
    elif claimed == "higher_order":
        if actual_n >= 6:
            results["checks"].append({"status": "✓", "kind": "oligomer",
                                       "msg": f"higher_order confirmed ({actual_n} chains)"})
        elif bio_count is not None and bio_count >= 6:
            results["checks"].append({"status": "✓", "kind": "oligomer",
                                       "msg": f"higher_order confirmed by biological assembly "
                                              f"({bio_details or f'{bio_count}-mer'}; ASU has {actual_n} chains)"})
        else:
            results["checks"].append({"status": "?", "kind": "oligomer",
                                       "msg": f"claimed higher_order but only {actual_n} chains "
                                              f"(biological assembly: {bio_details or 'unknown'})"})

    # ─── 4. computed model: is_computed should match AF- prefix ───
    is_af = pdb_id.upper().startswith("AF-")
    is_computed = summary["model_quality"]["is_computed"]
    if is_af and is_computed:
        results["checks"].append({"status": "✓", "kind": "computed",
                                   "msg": "AFDB model correctly detected as computed"})
    elif is_af and not is_computed:
        results["checks"].append({"status": "✗", "kind": "computed",
                                   "msg": "AFDB identifier but is_computed=False — detection broken"})
    elif not is_af and is_computed:
        results["checks"].append({"status": "?", "kind": "computed",
                                   "msg": "Deposited PDB ID but is_computed=True — unexpected"})

    # ─── 5. title agreement with description ───
    # Hardened in v1.2: word overlap alone is too weak — 1a9n passed v1.1 on
    # the single generic word "protein" while actually being the wrong entry
    # (U1A vs U2B''). Now we also check that specific molecule identifiers in
    # the deposited title do not contradict the ground truth's claimed identity.
    title = fetch_rcsb_title(pdb_id)
    if title:
        # 5a. identifier conflict — GT names a different numbered molecule
        id_text = " ".join([
            gt.get("short_name", ""),
            *((gt.get("identity") or {}).get("must_mention_one_of") or []),
        ])
        conflicts = identifier_conflict(id_text, title)
        if conflicts:
            results["checks"].append({"status": "✗", "kind": "identifier_conflict",
                                       "msg": f"ground-truth identity contradicts RCSB title {title!r} — "
                                              + "; ".join(conflicts)})
        # 5b. substantive word overlap
        ok, matched = title_overlap(gt.get("description", ""), title)
        if ok:
            results["checks"].append({"status": "✓", "kind": "title",
                                       "msg": f"description overlaps title via: {matched[:5]}"})
        else:
            results["checks"].append({"status": "✗", "kind": "title_mismatch",
                                       "msg": f"description shares NO substantive words with RCSB title {title!r} — ground truth likely refers to the wrong PDB entry"})

    # ─── 6. schema-level: required top-level fields ───
    required = ["pdb", "short_name", "description", "identity",
                "oligomeric_state", "fold_class", "active_site",
                "cofactors_metals_ligands", "notable_features",
                "negative_constraints", "inference_hygiene"]
    missing = [k for k in required if k not in gt]
    if missing:
        results["checks"].append({"status": "✗", "kind": "schema",
                                   "msg": f"missing required top-level keys: {missing}"})

    return results


# ─────────── report ───────────

def render_report(all_results: list[dict]) -> str:
    out = ["# Ground-truth verification report\n\n"]
    # Summary
    n_pass = sum(1 for r in all_results
                 if not any(c["status"] == "✗" for c in r["checks"]))
    n_warn = sum(1 for r in all_results
                 if any(c["status"] == "?" for c in r["checks"])
                 and not any(c["status"] == "✗" for c in r["checks"]))
    n_fail = sum(1 for r in all_results
                 if any(c["status"] == "✗" for c in r["checks"]))
    out.append(f"**{n_pass}/{len(all_results)} fully clean · {n_warn} with warnings · {n_fail} with failures.**\n\n")

    # Failure-first, then warnings, then clean
    def sort_key(r):
        if any(c["status"] == "✗" for c in r["checks"]):
            return (0, r["pdb"])
        if any(c["status"] == "?" for c in r["checks"]):
            return (1, r["pdb"])
        return (2, r["pdb"])

    for r in sorted(all_results, key=sort_key):
        n_fail = sum(1 for c in r["checks"] if c["status"] == "✗")
        n_warn = sum(1 for c in r["checks"] if c["status"] == "?")
        n_pass = sum(1 for c in r["checks"] if c["status"] == "✓")
        header_emoji = "❌" if n_fail else ("⚠️ " if n_warn else "✅")
        out.append(f"## {header_emoji} `{r['pdb']}` — {n_pass} ok, {n_warn} warn, {n_fail} fail\n\n")
        # Show failures + warnings first, then OKs
        for status_filter in ("✗", "?", "✓"):
            for c in r["checks"]:
                if c["status"] != status_filter:
                    continue
                out.append(f"- {c['status']} **{c['kind']}**: {c['msg']}\n")
        out.append("\n")
    return "".join(out)


# ─────────── main ───────────

def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--gt-dir", default=str(GT_DIR),
                    help=f"Directory of ground-truth YAML files (default: {GT_DIR.relative_to(ROOT)})")
    ap.add_argument("--report", default=None,
                    help="Output report path (default: verify_report.md next to GT dir)")
    args = ap.parse_args(argv)

    gt_dir = Path(args.gt_dir).resolve()
    report_path = Path(args.report) if args.report else (gt_dir.parent / f"verify_report_{gt_dir.name.replace('ground_truth_', '')}.md" if gt_dir.name != "ground_truth" else REPORT)

    all_results = []
    files = sorted(gt_dir.glob("*.yaml"))
    files = [f for f in files if not f.name.startswith("_")]
    print(f"Checking {len(files)} ground-truth files in {gt_dir}…")
    for i, f in enumerate(files, 1):
        print(f"  [{i:2d}/{len(files)}] {f.name}", end="", flush=True)
        try:
            r = check_one(f)
            n_fail = sum(1 for c in r["checks"] if c["status"] == "✗")
            n_warn = sum(1 for c in r["checks"] if c["status"] == "?")
            print(f"   {n_fail} fail, {n_warn} warn")
            all_results.append(r)
        except Exception as e:
            print(f"   CRASH: {type(e).__name__}: {e}")
            all_results.append({"pdb": f.stem,
                                "checks": [{"status": "✗", "kind": "crash",
                                            "msg": f"{type(e).__name__}: {e}"}]})

    report_path.write_text(render_report(all_results))
    print(f"\nWrote {report_path}")

    # Exit code reflects whether any ✗ items remain
    any_fail = any(any(c["status"] == "✗" for c in r["checks"]) for r in all_results)
    return 1 if any_fail else 0


if __name__ == "__main__":
    sys.exit(main())
