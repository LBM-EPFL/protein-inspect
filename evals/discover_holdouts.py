"""Discover PDB candidates for the eval v2 holdout set.

Queries the RCSB search API for entries released after Claude's knowledge
cutoff (2026-01-31), pulls metadata, and writes a candidate manifest. The
holdout set isolates structures the subject model can't have memorized, so
the eval can measure the lift of materials directly instead of measuring
Claude's PDB recall.

Output: evals/holdout_candidates.json with one record per entry containing
title, release_date, polymer composition, oligomeric state, ligand presence,
organism, resolution, method. Use the manifest to pick the final ~20 picks.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
OUT = ROOT / "evals" / "holdout_candidates.json"

SEARCH_URL = "https://search.rcsb.org/rcsbsearch/v2/query"
DATA_URL = "https://data.rcsb.org/rest/v1/core"

# Cutoff: anything released on/after 2026-02-01 postdates the training data.
CUTOFF_DATE = "2026-02-01T00:00:00Z"

# Cap on entries to fetch from the search. Search returns ~thousands; we
# only need a few hundred to pick 20 from.
MAX_HITS = 400


def search_entries() -> list[str]:
    """Return PDB IDs released on/after CUTOFF_DATE.

    Protein-only filtering happens downstream in fetch_entry_meta + main(),
    not here — the RCSB search API rejected the compound query against
    `rcsb_entry_info.selected_polymer_entity_types` in testing."""
    query = {
        "query": {
            "type": "terminal",
            "service": "text",
            "parameters": {
                "attribute": "rcsb_accession_info.initial_release_date",
                "operator": "greater_or_equal",
                "value": CUTOFF_DATE,
            },
        },
        "return_type": "entry",
        "request_options": {
            "results_content_type": ["experimental"],
            "paginate": {"start": 0, "rows": MAX_HITS},
            "sort": [{"sort_by": "rcsb_accession_info.initial_release_date",
                      "direction": "desc"}],
        },
    }
    req = urllib.request.Request(
        SEARCH_URL,
        data=json.dumps(query).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read())
    return [hit["identifier"] for hit in body.get("result_set", [])]


def fetch_entry_meta(pdb_id: str) -> dict | None:
    """Pull a compact metadata record for one entry."""
    url = f"{DATA_URL}/entry/{pdb_id}"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            d = json.loads(resp.read())
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return None

    entry = d.get("rcsb_entry_info", {}) or {}
    accession = d.get("rcsb_accession_info", {}) or {}
    struct = d.get("struct", {}) or {}
    exptl = (d.get("exptl") or [{}])[0]

    # Pull biological assembly info for the canonical assembly
    assembly = None
    try:
        a_url = f"{DATA_URL}/assembly/{pdb_id}/1"
        a_req = urllib.request.Request(a_url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(a_req, timeout=10) as a_resp:
            a = json.loads(a_resp.read())
        ai = a.get("rcsb_assembly_info", {}) or {}
        sa = a.get("pdbx_struct_assembly", {}) or {}
        assembly = {
            "oligomeric_count": sa.get("oligomeric_count"),
            "oligomeric_details": sa.get("oligomeric_details"),
            "polymer_composition": ai.get("polymer_composition"),
        }
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        assembly = None

    return {
        "pdb": pdb_id.lower(),
        "title": struct.get("title", ""),
        "release_date": accession.get("initial_release_date", ""),
        "deposit_date": accession.get("deposit_date", ""),
        "method": exptl.get("method", ""),
        "resolution": entry.get("resolution_combined", [None])[0] if entry.get("resolution_combined") else None,
        "polymer_composition": entry.get("selected_polymer_entity_types", ""),
        "polymer_entity_count_protein": entry.get("polymer_entity_count_protein"),
        "polymer_entity_count_nucleic_acid": entry.get("polymer_entity_count_nucleic_acid"),
        "deposited_polymer_monomer_count": entry.get("deposited_polymer_monomer_count"),
        "n_branched_entities": entry.get("branched_entity_count", 0),
        "n_nonpolymer_entities": entry.get("nonpolymer_entity_count", 0),
        "assembly": assembly,
    }


def main() -> int:
    print(f"Searching for entries released on/after {CUTOFF_DATE}…")
    ids = search_entries()
    print(f"  → {len(ids)} candidates")

    print("Fetching metadata (this takes a minute)…")
    records: list[dict] = []
    for i, pdb in enumerate(ids):
        if i % 25 == 0:
            print(f"  [{i:3d}/{len(ids)}]  kept={len(records)}  current={pdb}")
        meta = fetch_entry_meta(pdb)
        if not meta:
            continue
        # Protein-only filter (we want structural biology, not pure NA/peptide)
        comp = (meta.get("polymer_composition") or "").lower()
        if "protein" not in comp:
            continue
        records.append(meta)
        # Stop once we have enough candidates to choose from
        if len(records) >= 150:
            print(f"  collected {len(records)} candidates after {i+1} entries — stopping")
            break
        # Be polite to RCSB
        time.sleep(0.05)

    OUT.write_text(json.dumps({
        "fetched_at": datetime.utcnow().isoformat() + "Z",
        "cutoff_date": CUTOFF_DATE,
        "n_records": len(records),
        "records": records,
    }, indent=2))
    print(f"Wrote {OUT} ({len(records)} entries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
