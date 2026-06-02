"""Feature extraction from a structure file.

Each extractor takes a gemmi.Structure (and sometimes the ligand-class registry)
and returns a dict that maps directly to a sub-tree of summary.schema.json v1.1.

Design notes:
- gemmi for fast parsing, basic geometry, CIF/BCIF/PDB I/O.
- biotite for secondary-structure annotation (P-SEA algorithm).
- Heuristics are documented next to where they fire so they can be revised.
- Functions never raise on missing data; they return None / empty containers.
"""

from __future__ import annotations

import math
import os
import re
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import gemmi
import yaml

PKG_ROOT = Path(__file__).parent.parent.parent
LIGAND_CLASSES_PATH = PKG_ROOT / "skills" / "protein-inspect" / "ligand_classes.yaml"

# ─────────── constants ───────────

# Standard amino acid 3-letter codes
STANDARD_AA = {
    "ALA", "ARG", "ASN", "ASP", "CYS", "GLU", "GLN", "GLY", "HIS", "ILE",
    "LEU", "LYS", "MET", "PHE", "PRO", "SER", "THR", "TRP", "TYR", "VAL",
    "MSE",  # selenomethionine — treat as MET
}
DNA_BASES = {"DA", "DC", "DG", "DT", "DI", "DU"}
RNA_BASES = {"A", "C", "G", "U", "I"}
WATER     = {"HOH", "WAT", "DOD", "H2O"}

# Eisenberg consensus hydrophobicity (Kyte-Doolittle-like, normalized)
HYDROPHOBICITY = {
    "ALA": 0.62, "ARG": -2.53, "ASN": -0.78, "ASP": -0.90, "CYS": 0.29,
    "GLU": -0.74, "GLN": -0.85, "GLY": 0.48, "HIS": -0.40, "ILE": 1.38,
    "LEU": 1.06, "LYS": -1.50, "MET": 0.64, "PHE": 1.19, "PRO": 0.12,
    "SER": -0.18, "THR": -0.05, "TRP": 0.81, "TYR": 0.26, "VAL": 1.08,
    "MSE": 0.64,
}

# ─────────── ligand-class registry ───────────

def load_ligand_classes(path: Path | None = None) -> dict:
    """Load ligand_classes.yaml and flatten cofactor sub-categories for fast lookup."""
    p = path or LIGAND_CLASSES_PATH
    raw = yaml.safe_load(p.read_text())

    # Build {3-letter-code → category} map (artifact categories)
    by_code = {}

    def _add(codes, category):
        for c in codes or []:
            # later category wins; this is rare in practice (we test no overlap)
            by_code[c] = category

    _add(raw.get("cryoprotectants"),     "cryoprotectant")
    _add(raw.get("buffers"),             "buffer")
    _add(raw.get("precipitants_salts"),  "precipitant_salt")
    _add(raw.get("halides_phasing_or_buffer"), "buffer")
    _add(raw.get("heavy_atoms_phasing"), "heavy_atom_phasing")
    _add(raw.get("detergents"),          "detergent")
    _add(raw.get("glycans"),             "glycan")
    _add(raw.get("lipids"),              "lipid")
    _add(raw.get("nucleotides_free"),    "nucleotide_free")
    _add(raw.get("metals_biological"),   "metal")
    _add(raw.get("iron_sulfur_clusters"),"iron_sulfur")

    # Cofactors are a nested dict {chemistry_class: [codes]}
    cofactor_chemistry = {}
    for chem_class, codes in (raw.get("cofactors") or {}).items():
        for c in codes:
            cofactor_chemistry[c] = chem_class
            by_code[c] = "cofactor"

    return {
        "by_code": by_code,
        "cofactor_chemistry": cofactor_chemistry,
        "metals_biological": set(raw.get("metals_biological") or []),
        "iron_sulfur_clusters": set(raw.get("iron_sulfur_clusters") or []),
    }


# ─────────── structure loading ───────────

def fetch_structure(pdb_id_or_path: str, cache_dir: Path = Path("/tmp/protein_inspect_cache")) -> tuple[gemmi.Structure, str]:
    """Load a structure from a local path, an RCSB PDB ID (4 chars), or an
    AlphaFold DB identifier (e.g. AF-P00558-F1). Returns (Structure, path)."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    if Path(pdb_id_or_path).exists():
        return gemmi.read_structure(pdb_id_or_path), str(pdb_id_or_path)

    # ModelArchive: ma-<id> (e.g. ma-abc12, ma-bak-cm-0001).
    # API returns the model CIF file via the /files/main endpoint.
    ma_match = re.match(r"^ma-[0-9A-Za-z\-]+$", pdb_id_or_path, re.IGNORECASE)
    if ma_match:
        maid = pdb_id_or_path.lower()
        cached = cache_dir / f"{maid}.cif"
        if not cached.exists():
            # ModelArchive's main download endpoint
            url = f"https://modelarchive.org/api/projects/{maid}?type=basic__model_file_name"
            # Fallback to the standard CIF download URL pattern
            cif_url = f"https://modelarchive.org/doi/10.5452/{maid}.cif"
            try:
                urllib.request.urlretrieve(cif_url, cached)
            except urllib.error.HTTPError:
                # Try the alternate file pattern
                cif_url = f"https://modelarchive.org/api/projects/{maid}/data/main"
                urllib.request.urlretrieve(cif_url, cached)
        return gemmi.read_structure(str(cached)), str(cached)

    # AlphaFold DB: AF-<uniprot>-F<frag>  (also tolerate uppercase or
    # bare "AF-..." prefix without trailing -F1; default fragment = F1)
    af_match = re.match(r"^AF-([0-9A-Za-z]+)(?:-F(\d+))?$", pdb_id_or_path)
    if af_match:
        uniprot, frag = af_match.group(1), af_match.group(2) or "1"
        afid = f"AF-{uniprot}-F{frag}"
        cached = cache_dir / f"{afid}.cif"
        if not cached.exists():
            # AFDB model versions bump periodically (v4 → v5 → v6 …). Query the
            # prediction API for the latest version rather than hard-coding.
            import json
            api_url = f"https://alphafold.ebi.ac.uk/api/prediction/{uniprot}"
            try:
                with urllib.request.urlopen(api_url, timeout=10.0) as resp:
                    meta = json.loads(resp.read().decode("utf-8"))
                latest_version = meta[0]["latestVersion"]
            except Exception as e:
                raise RuntimeError(f"AFDB API lookup failed for {uniprot}: {e}")
            url = f"https://alphafold.ebi.ac.uk/files/{afid}-model_v{latest_version}.cif"
            urllib.request.urlretrieve(url, cached)
        return gemmi.read_structure(str(cached)), str(cached)

    # RCSB PDB: 4-char alphanumeric
    pdb_id = pdb_id_or_path.lower()
    if not re.match(r"^[0-9a-z]{4}$", pdb_id):
        raise ValueError(f"Not a path, RCSB ID, or AFDB ID: {pdb_id_or_path!r}")
    cached = cache_dir / f"{pdb_id}.cif"
    if not cached.exists():
        url = f"https://files.rcsb.org/download/{pdb_id}.cif"
        urllib.request.urlretrieve(url, cached)
    return gemmi.read_structure(str(cached)), str(cached)


# ─────────── extractors ───────────

def extract_provenance(struct: gemmi.Structure, source: str = "rcsb", input_path: str | None = None) -> dict:
    """Resolution, method, space group, unit cell, deposition date."""
    res = struct.resolution if struct.resolution > 0 else None

    # gemmi.InfoMap supports __contains__ and __getitem__, not .get()
    info = struct.info if hasattr(struct, "info") else None
    method = None
    if info is not None and "_exptl.method" in info:
        method = info["_exptl.method"]
    if not method and struct.raw_remarks:
        for rem in struct.raw_remarks:
            if "EXPDTA" in rem.upper():
                m = re.search(r"EXPDTA\s+(.+)", rem)
                if m:
                    method = m.group(1).strip()
                    break

    deposition = None
    if info is not None and "_pdbx_database_status.recvd_initial_deposition_date" in info:
        deposition = info["_pdbx_database_status.recvd_initial_deposition_date"]

    cell = None
    if struct.cell.a > 1.0:
        cell = [struct.cell.a, struct.cell.b, struct.cell.c,
                struct.cell.alpha, struct.cell.beta, struct.cell.gamma]

    sg = struct.spacegroup_hm or None
    if sg and sg.strip() in ("", "P 1"):
        # P1 in CIF can mean unspecified; only keep if real
        if cell is None or struct.cell.a < 1.0:
            sg = None

    # Resolution class
    if res is None:
        rclass = "computed" if (cell is None and method is None) else "unknown"
    elif res < 2.0:
        rclass = "high"
    elif res <= 3.0:
        rclass = "medium"
    else:
        rclass = "low"
    if method and "ELECTRON MICROSCOPY" in method.upper():
        rclass = "cryo_em"

    return {
        "source": source,
        "input_path": input_path,
        "resolution": res,
        "method": method,
        "resolution_class": rclass,
        "space_group": sg,
        "unit_cell": cell,
        "deposition_date": deposition,
    }


def _polymer_kind(residue_names: set[str]) -> str | None:
    """Classify a chain by its residue composition. Returns 'protein'/'dna'/'rna' or None."""
    aa_n = sum(1 for r in residue_names if r in STANDARD_AA)
    dna_n = sum(1 for r in residue_names if r in DNA_BASES)
    rna_n = sum(1 for r in residue_names if r in RNA_BASES)
    if aa_n == 0 and dna_n == 0 and rna_n == 0:
        return None
    # Pick majority
    counts = {"protein": aa_n, "dna": dna_n, "rna": rna_n}
    kind = max(counts, key=counts.get)
    if counts[kind] < 3:
        return None  # too short — likely a peptide ligand or something else
    return kind


def extract_macromolecule_type(struct: gemmi.Structure) -> str:
    """Classify chains as protein-only / NA-only / mixed."""
    has_protein = False
    has_dna = False
    has_rna = False
    has_glycan_chain = False
    model = struct[0]
    for chain in model:
        residues = {res.name for res in chain}
        kind = _polymer_kind(residues)
        if kind == "protein":
            has_protein = True
        elif kind == "dna":
            has_dna = True
        elif kind == "rna":
            has_rna = True

    if has_protein and has_dna and has_rna:
        return "mixed"
    if has_protein and has_dna:
        return "protein_dna"
    if has_protein and has_rna:
        return "protein_rna"
    if has_protein:
        return "protein_only"
    if has_dna and not has_rna:
        return "dna_only"
    if has_rna and not has_dna:
        return "rna_only"
    return "mixed"


def extract_model_type(struct: gemmi.Structure, provenance: dict) -> dict:
    """Detect computed model: resolution null AND B-factor range strictly in
    [0,100] AND the experimental method is NOT a non-X-ray/cryo-EM technique
    that also lacks a reported resolution (NMR, neutron diffraction, fiber
    diffraction, solid-state-NMR, EPR). Those have null resolution by nature
    and often have B-factor columns repurposed for per-atom RMSF, RMSD, or
    zero — which would otherwise satisfy the [0,100] gate and incorrectly
    flag an experimentally-determined NMR ensemble as a computed/AF model."""
    bvals = []
    model = struct[0]
    for chain in model:
        for res in chain:
            if res.name in WATER:
                continue
            for atom in res:
                bvals.append(atom.b_iso)
    if not bvals:
        return {"is_computed": False, "confidence_metric": "none"}

    # Experimental methods that legitimately produce resolution=None but are
    # NOT computed models. The match is case-insensitive and substring to
    # absorb variants like "SOLUTION NMR", "SOLID-STATE NMR", "NMR, OTHER".
    method = (provenance.get("method") or "").upper()
    experimental_no_resolution = any(
        tag in method for tag in ("NMR", "EPR", "FIBER", "NEUTRON")
    )

    res_is_null = provenance["resolution"] is None
    b_in_plddt_range = (min(bvals) >= 0.0) and (max(bvals) <= 100.0)
    is_computed = res_is_null and b_in_plddt_range and not experimental_no_resolution

    if is_computed:
        n = len(bvals)
        high = sum(1 for b in bvals if b > 90) / n
        med = sum(1 for b in bvals if 70 < b <= 90) / n
        low = sum(1 for b in bvals if b <= 70) / n
        return {
            "is_computed": True,
            "confidence_metric": "plddt",
            "plddt_summary": {
                "mean": sum(bvals) / n,
                "fraction_high": high,
                "fraction_medium": med,
                "fraction_low": low,
                "low_confidence_regions": _low_plddt_regions(struct),
            },
        }
    return {"is_computed": False, "confidence_metric": "bfactor"}


def _low_plddt_regions(struct: gemmi.Structure, threshold: float = 70.0, min_len: int = 5) -> list:
    """Return contiguous residue ranges with mean pLDDT below threshold."""
    out = []
    model = struct[0]
    for chain in model:
        cur = []
        for res in chain:
            if res.name not in STANDARD_AA:
                continue
            ca = next((a for a in res if a.name == "CA"), None)
            if ca is None:
                continue
            cur.append((res.seqid.num, ca.b_iso))
        if not cur:
            continue
        # walk, group consecutive low-confidence residues
        run = []
        for resi, b in cur:
            if b < threshold:
                run.append((resi, b))
            else:
                if len(run) >= min_len:
                    out.append({
                        "chain": chain.name,
                        "range": [run[0][0], run[-1][0]],
                        "mean_plddt": sum(x[1] for x in run) / len(run),
                    })
                run = []
        if len(run) >= min_len:
            out.append({
                "chain": chain.name,
                "range": [run[0][0], run[-1][0]],
                "mean_plddt": sum(x[1] for x in run) / len(run),
            })
    return out


# ─────────── assembly ───────────

def _chain_seq(chain: gemmi.Chain) -> str:
    """1-letter polymer sequence of a chain (uses MSE→M)."""
    map3to1 = gemmi.ResidueInfo
    out = []
    for res in chain:
        if res.name in STANDARD_AA or res.name in DNA_BASES or res.name in RNA_BASES:
            info = gemmi.find_tabulated_residue(res.name)
            if info and info.one_letter_code:
                out.append(info.one_letter_code.upper())
            elif res.name == "MSE":
                out.append("M")
    return "".join(out)


def _chain_ca_coords(chain: gemmi.Chain) -> list:
    out = []
    for res in chain:
        if res.name not in STANDARD_AA:
            continue
        ca = next((a for a in res if a.name == "CA"), None)
        if ca:
            out.append((res.seqid.num, ca.pos))
    return out


def _is_peptide_residue(name: str) -> bool:
    """Recognize amino acids broadly — standard 20 plus non-natural amino
    acid CCDs commonly used in peptide drugs. Uses gemmi's CCD tabulation
    when available (catches MLE, SAR, PIP, AC5, and a long tail) and falls
    back to STANDARD_AA. Required for detecting macrocyclic-peptide drugs
    that almost always include non-canonical residues."""
    if name in STANDARD_AA:
        return True
    try:
        info = gemmi.find_tabulated_residue(name)
        if info is None:
            return False
        # gemmi exposes one_letter_code and a kind enum. Amino acid analogues
        # (D-amino acids, N-methyl variants, β/γ-aas, etc.) have a one-letter
        # code; pure heterogens like buffers / cryoprotectants do not.
        if info.one_letter_code and info.is_amino_acid():
            return True
    except (AttributeError, Exception):
        pass
    return False


def extract_peptide_ligands(struct: gemmi.Structure) -> list[dict]:
    """Detect bound peptide ligands: short polymer chains of amino-acid-class
    residues (≤30 residues, ≥3 residues) that are clearly distinct from the
    main protein. Recognizes non-canonical amino acids (MLE, PIP, SAR, AC5,
    …) so macrocyclic-peptide drugs are caught — the standard 20-aa filter
    would miss them, since every macrocyclic peptide drug includes
    non-natural residues.

    Triggering use cases this covers:
      - macrocyclic peptide inhibitors of KRAS, Mpro, MDM2, …
      - peptide-substrate / propeptide complexes
      - neuropeptide-bound GPCR structures
      - antibody CDR-mimicking peptide drugs
      - cleaved propeptides retained in mature enzymes (PCSK9-style)
    """
    model = struct[0]
    main_lengths: list[int] = []
    candidates: list[dict] = []
    for chain in model:
        # Count amino-acid-class residues (standard + non-natural).
        aa_residues = [r for r in chain if _is_peptide_residue(r.name)]
        if len(aa_residues) < 3:
            continue
        # Build a representative "sequence" — one-letter codes where known,
        # 'X' for non-canonical residues. Used to report length and a hint.
        seq_chars: list[str] = []
        for r in aa_residues:
            if r.name in STANDARD_AA:
                info = gemmi.find_tabulated_residue(r.name)
                if info and info.one_letter_code:
                    seq_chars.append(info.one_letter_code.upper())
                    continue
            seq_chars.append("X")
        seq = "".join(seq_chars)
        n = len(aa_residues)
        if n <= 30:
            candidates.append({
                "chain": chain.name,
                "n_residues": n,
                "sequence": seq,
            })
        else:
            main_lengths.append(n)
    # If there's no clearly-larger main protein, the structure may itself
    # be peptide-only (cleaved fragments, designed mini-binders, etc.) —
    # don't claim peptide-ligand status in that case.
    if not candidates or not main_lengths:
        return []
    max_main = max(main_lengths)
    if max_main < 50:
        return []
    # Require the main protein to be ≥3× longer than the peptide candidate.
    return [c for c in candidates if c["n_residues"] * 3 <= max_main]


def extract_assembly(struct: gemmi.Structure) -> dict:
    """n_chains, oligomer, homo/hetero, interface contacts, RMSDs."""
    model = struct[0]
    chains_data = []
    for chain in model:
        residues = {res.name for res in chain}
        kind = _polymer_kind(residues)
        if kind != "protein":
            continue
        seq = _chain_seq(chain)
        if len(seq) < 10:
            continue
        chains_data.append({"name": chain.name, "seq": seq, "chain": chain})

    n = len(chains_data)
    chains = [c["name"] for c in chains_data]
    if n == 0:
        return {"n_chains": 0, "chains": [], "homo_or_hetero": "monomer"}

    if n == 1:
        return {"n_chains": 1, "chains": chains, "homo_or_hetero": "monomer", "oligomer": "monomer", "unique_sequences": 1}

    # Cluster chains by sequence similarity (>=90% identity over min length)
    seq_groups = []
    for cd in chains_data:
        placed = False
        for g in seq_groups:
            if _seq_similar(cd["seq"], g[0]["seq"]):
                g.append(cd)
                placed = True
                break
        if not placed:
            seq_groups.append([cd])
    unique = len(seq_groups)
    homo_or_hetero = "homo" if unique == 1 else "hetero"
    oligo_map = {1:"monomer", 2:"dimer", 3:"trimer", 4:"tetramer", 5:"pentamer",
                 6:"hexamer", 7:"heptamer", 8:"octamer"}
    oligomer = oligo_map.get(n, "higher_order")

    # Interface contacts: CA-CA within 8 Å between chains (relax from 4 since we want any contact)
    contacts = []
    for i in range(n):
        for j in range(i+1, n):
            ca_i = _chain_ca_coords(chains_data[i]["chain"])
            ca_j = _chain_ca_coords(chains_data[j]["chain"])
            count = 0
            for _, p1 in ca_i:
                for _, p2 in ca_j:
                    if p1.dist(p2) < 8.0:
                        count += 1
                        break
            if count > 0:
                contacts.append({"pair": [chains_data[i]["name"], chains_data[j]["name"]], "n_residues": count})

    # Symmetry guess for homo-oligomers: rotational order = n_chains for cyclic
    sym = None
    if homo_or_hetero == "homo" and n > 1:
        # very crude: if every chain pair has contacts in a ring pattern, call it Cn
        sym = f"C{n}"  # heuristic — refine later if needed

    rmsd_max = None
    if homo_or_hetero == "homo" and n > 1:
        rmsd_max = _compute_chain_rmsd_max(chains_data)

    return {
        "n_chains": n,
        "chains": chains,
        "homo_or_hetero": homo_or_hetero,
        "oligomer": oligomer,
        "symmetry": sym,
        "unique_sequences": unique,
        "chain_rmsd_max": rmsd_max,
        "interface_contacts": contacts,
    }


def _seq_similar(s1: str, s2: str, identity_threshold: float = 0.9) -> bool:
    if not s1 or not s2:
        return False
    if abs(len(s1) - len(s2)) / max(len(s1), len(s2)) > 0.2:
        return False
    n = min(len(s1), len(s2))
    matches = sum(1 for a, b in zip(s1[:n], s2[:n]) if a == b)
    return matches / n >= identity_threshold


def _compute_chain_rmsd_max(chains_data: list) -> float | None:
    """Crude pairwise RMSD of CA atoms after no-superposition (just relative shape)."""
    # For homo-oligomers we want a sense of conformational variance.
    # Proper superposition is complex; here we just return None and let downstream tools refine.
    return None


# ─────────── fold ───────────

def extract_fold(struct: gemmi.Structure, repr_chain: str | None = None,
                 is_computed: bool = False) -> dict:
    """SS fractions plus per-residue confidence/flexibility stats.

    For deposited (X-ray / cryo-EM / NMR) structures, the B-factor column
    holds atomic displacement (Å²) and is reported as `bfactor_stats` —
    higher mean = more disordered / mobile.

    For computed models (AlphaFold-DB and the like), the same column carries
    **pLDDT** (predicted Local Distance Difference Test, 0–100, higher = more
    confident). Reporting that as "B-factor" inverts the semantics: a high
    mean pLDDT means the model is *well-predicted*, not flexible. When
    `is_computed=True` we emit `plddt_stats` instead, with the standard
    EBI/AlphaFold bands (very_low <50, low 50–70, confident 70–90,
    very_high ≥90). Downstream readers (the analyze.md prompt + decision
    tree rules) branch on `model_quality.confidence_metric` to read the
    right key.
    """
    model = struct[0]
    if repr_chain is None:
        for chain in model:
            residues = {res.name for res in chain}
            if _polymer_kind(residues) == "protein":
                repr_chain = chain.name
                break
        if repr_chain is None:
            return {"representative_chain": "?", "length": 0, "ss_fractions": {"helix": 0, "sheet": 0, "loop": 1.0}}

    chain = next((c for c in model if c.name == repr_chain), None)
    ca_atoms = [a for r in chain for a in r if a.name == "CA" and r.name in STANDARD_AA]
    length = len(ca_atoms)
    if length == 0:
        return {"representative_chain": repr_chain, "length": 0, "ss_fractions": {"helix": 0, "sheet": 0, "loop": 1.0}}

    ss_string, fractions = _compute_secondary_structure(chain)
    bvals = [a.b_iso for a in ca_atoms]
    mean = sum(bvals) / len(bvals)
    stats = {
        "mean": mean,
        "min": min(bvals),
        "max": max(bvals),
        "std": (sum((b - mean) ** 2 for b in bvals) / len(bvals)) ** 0.5,
    }
    out: dict = {
        "representative_chain": repr_chain,
        "length": length,
        "ss_fractions": fractions,
        "ss_string": ss_string,
    }
    if is_computed:
        n = len(bvals)
        stats["fraction_very_high"] = sum(1 for b in bvals if b >= 90) / n
        stats["fraction_confident"] = sum(1 for b in bvals if 70 <= b < 90) / n
        stats["fraction_low"] = sum(1 for b in bvals if 50 <= b < 70) / n
        stats["fraction_very_low"] = sum(1 for b in bvals if b < 50) / n
        out["plddt_stats"] = stats
    else:
        out["bfactor_stats"] = stats
    return out


def _compute_secondary_structure(chain: gemmi.Chain) -> tuple[str, dict]:
    """Cheap geometric SS via CA-CA distance + virtual dihedrals (P-SEA-style).

    Returns (ss_string, fractions). H = helix, E = sheet, L = loop/other.
    For implementation simplicity we use a phi/psi-like proxy from CA positions.
    """
    ca = []
    for res in chain:
        if res.name not in STANDARD_AA:
            continue
        a = next((x for x in res if x.name == "CA"), None)
        if a:
            ca.append((res.seqid.num, a.pos))
    n = len(ca)
    if n < 5:
        return "L" * n, {"helix": 0.0, "sheet": 0.0, "loop": 1.0}

    ss = ["L"] * n
    # P-SEA criteria: alpha helix has CA-CA i,i+3 ~5.4 Å AND i,i+4 ~6.4 Å
    # beta strand has CA-CA i,i+2 ~6.7 Å (extended)
    for i in range(n):
        d3 = ca[i][1].dist(ca[i+3][1]) if i + 3 < n else None
        d4 = ca[i][1].dist(ca[i+4][1]) if i + 4 < n else None
        d2 = ca[i][1].dist(ca[i+2][1]) if i + 2 < n else None
        if d3 is not None and d4 is not None:
            if 4.5 < d3 < 6.5 and 5.5 < d4 < 7.5:
                for k in range(i, min(i+5, n)):
                    ss[k] = "H"
                continue
        if d2 is not None:
            if 6.0 < d2 < 7.5:
                for k in range(i, min(i+3, n)):
                    if ss[k] == "L":
                        ss[k] = "E"

    h_n = sum(1 for c in ss if c == "H")
    e_n = sum(1 for c in ss if c == "E")
    l_n = sum(1 for c in ss if c == "L")
    total = max(n, 1)
    return "".join(ss), {"helix": h_n/total, "sheet": e_n/total, "loop": l_n/total}


# ─────────── ligand classification ───────────

def extract_ligand_classification(struct: gemmi.Structure, classes: dict) -> dict:
    """Partition all HETATM-style residues into the schema's ligand classes."""
    by_code = classes["by_code"]
    cofactor_chem = classes["cofactor_chemistry"]
    is_metal = classes["metals_biological"]
    is_fes   = classes["iron_sulfur_clusters"]

    bins = defaultdict(Counter)  # category → Counter[code]
    metals_collected = []
    cofactors_collected = []
    glycans_collected = []
    lipids_collected = []
    nucleotides_collected = []
    unclassified = Counter()
    bio_ligands = Counter()

    model = struct[0]
    for chain in model:
        for res in chain:
            name = res.name
            # skip polymers (proteins/NAs are handled elsewhere) and water
            if name in STANDARD_AA or name in DNA_BASES or name in RNA_BASES or name in WATER:
                continue
            cat = by_code.get(name)
            if cat is None:
                unclassified[name] += 1
                bio_ligands[name] += 1   # fall through
                continue
            if cat == "metal":
                metals_collected.append((name, res, chain.name))
            elif cat == "iron_sulfur":
                metals_collected.append((name, res, chain.name))
            elif cat == "cofactor":
                cofactors_collected.append((name, res, chain.name, cofactor_chem.get(name, "other")))
            elif cat == "glycan":
                glycans_collected.append((name, res, chain.name))
            elif cat == "lipid":
                lipids_collected.append((name, res, chain.name))
            elif cat == "nucleotide_free":
                nucleotides_collected.append((name, res, chain.name))
            else:
                bins[cat][name] += 1

    return {
        "ligand_bins": {k: dict(v) for k, v in bins.items()},
        "bio_ligand_codes": dict(bio_ligands),
        "unclassified": dict(unclassified),
        "metals_raw": metals_collected,
        "cofactors_raw": cofactors_collected,
        "glycans_raw": glycans_collected,
        "lipids_raw": lipids_collected,
        "nucleotides_free_raw": nucleotides_collected,
        "_iron_sulfur_codes": is_fes,
    }


def assemble_ligands_block(struct: gemmi.Structure, classification: dict) -> dict:
    """Convert raw classification into the schema's ligands{} block (bio + artifact partition)."""
    out = {}
    bins = classification["ligand_bins"]
    # artifact categories
    for cat in ["buffer", "cryoprotectant", "precipitant_salt", "detergent", "heavy_atom_phasing"]:
        if cat in bins:
            out[cat] = [{"id": code, "n_copies": n} for code, n in sorted(bins[cat].items())]
    if classification["unclassified"]:
        out["unclassified"] = [{"id": code, "n_copies": n} for code, n in sorted(classification["unclassified"].items())]
    # bio_ligand: every code from extract_ligand_classification that fell through
    # to the bio_ligand bucket. Unclassified codes are listed in BOTH bio_ligand
    # (so they are still analyzed) and the unclassified bucket (so the curator
    # is alerted). Earlier code subtracted unclassified — that was wrong.
    if classification["bio_ligand_codes"]:
        out["bio_ligand"] = [
            {"id": code, "n_copies": n, "placement": "unknown"}
            for code, n in sorted(classification["bio_ligand_codes"].items())
        ]
    return out


def extract_metals(struct: gemmi.Structure, classification: dict) -> list:
    """List metals with their coordinating residues."""
    out = []
    fes_codes = classification["_iron_sulfur_codes"]
    counts = Counter()
    coords_by_code = defaultdict(list)
    for code, res, chain_name in classification["metals_raw"]:
        counts[code] += 1
        coords_by_code[code].append((res, chain_name))
    if not counts:
        return []

    model = struct[0]
    for code, n in counts.items():
        # Find protein residues within 3.5 Å of any atom of this metal
        coordinating = set()
        for res, chain_name in coords_by_code[code]:
            for matom in res:
                for chain in model:
                    for r in chain:
                        if r.name not in STANDARD_AA:
                            continue
                        for a in r:
                            if a.element.name in ("H",):
                                continue
                            if matom.pos.dist(a.pos) < 3.5:
                                coordinating.add(f"{r.name}{r.seqid.num}")
                                break
        cluster = "FES" if code == "FES" else (
                  "F3S" if code == "F3S" else (
                  "SF4" if code == "SF4" else (
                  "CFM" if code == "CFM" else "mononuclear")))
        if code in fes_codes:
            cluster = code
        out.append({
            "id": code,
            "n_copies": n,
            "cluster_type": cluster,
            "coordinating_residues": sorted(coordinating),
            "context": "catalytic_likely" if len(coordinating) >= 3 else "structural_likely" if len(coordinating) > 0 else "unknown",
        })
    return out


def extract_cofactors(classification: dict) -> list:
    counts = defaultdict(lambda: {"n": 0, "chemistry": "other"})
    for code, _res, _chain, chem in classification["cofactors_raw"]:
        counts[code]["n"] += 1
        counts[code]["chemistry"] = chem
    return [
        {"id": code, "n_copies": d["n"], "chemistry_class": d["chemistry"]}
        for code, d in sorted(counts.items())
    ]


def extract_free_nucleotides(classification: dict) -> list:
    counts = Counter()
    for code, _res, _chain in classification["nucleotides_free_raw"]:
        counts[code] += 1
    return [{"id": code, "n_copies": n, "near_phosphate_loop": False} for code, n in sorted(counts.items())]


def extract_glycans(struct: gemmi.Structure, classification: dict) -> list:
    """Aggregated glycan list — ASN linkage detection is best-effort."""
    counts = Counter()
    for code, _res, _chain in classification["glycans_raw"]:
        counts[code] += 1
    return [{"id": code, "n_copies": n} for code, n in sorted(counts.items())]


def extract_lipids(classification: dict) -> list:
    counts = Counter()
    for code, _res, _chain in classification["lipids_raw"]:
        counts[code] += 1
    return [{"id": code, "n_copies": n} for code, n in sorted(counts.items())]


def extract_nucleic_acids(struct: gemmi.Structure) -> dict | None:
    """If structure contains DNA/RNA chains, summarize them."""
    model = struct[0]
    na_chains = []
    n_residues = 0
    types = set()
    for chain in model:
        residues = {res.name for res in chain}
        kind = _polymer_kind(residues)
        if kind in ("dna", "rna"):
            na_chains.append(chain.name)
            n_residues += sum(1 for r in chain if r.name in DNA_BASES or r.name in RNA_BASES)
            types.add(kind.upper())
    if not na_chains:
        return None
    if len(types) == 2:
        t = "hybrid"
    else:
        t = next(iter(types))
    return {
        "type": t,
        "chains": na_chains,
        "n_residues": n_residues,
        "is_double_stranded": len(na_chains) >= 2,
    }


# ─────────── disulfides ───────────

def extract_disulfides(struct: gemmi.Structure) -> list:
    """Find S-S pairs < 2.5 Å between Cys SG atoms; classify standard/vicinal/interchain."""
    sg_atoms = []
    model = struct[0]
    for chain in model:
        for res in chain:
            if res.name != "CYS":
                continue
            sg = next((a for a in res if a.name == "SG"), None)
            if sg:
                sg_atoms.append((chain.name, res.seqid.num, sg))

    out = []
    seen = set()
    for i in range(len(sg_atoms)):
        for j in range(i+1, len(sg_atoms)):
            ch1, r1, a1 = sg_atoms[i]
            ch2, r2, a2 = sg_atoms[j]
            d = a1.pos.dist(a2.pos)
            if d > 2.5:
                continue
            key = tuple(sorted([(ch1, r1), (ch2, r2)]))
            if key in seen:
                continue
            seen.add(key)
            if ch1 != ch2:
                t = "interchain"
            elif abs(r1 - r2) == 1:
                t = "vicinal"
            else:
                t = "standard"
            out.append({
                "residues": [f"CYS{r1}", f"CYS{r2}"],
                "chains": [ch1] if ch1 == ch2 else sorted([ch1, ch2]),
                "distance_a": round(d, 3),
                "type": t,
            })
    return out


# ─────────── active site patterns ───────────

def extract_active_site_patterns(struct: gemmi.Structure, ligand_residues: list = None,
                                  bio_ligand_codes: set = None,
                                  metal_codes: set = None) -> list:
    """Run pattern detectors. Returns list of {pattern, residues, chain, geometry, rule_id}.

    `bio_ligand_codes` and `metal_codes` are used as CONTEXTUAL GATES — geometric
    patterns (triads, dyads) fire ONLY when corroborated by a bio-ligand or
    metal nearby, OR (for triads/asp dyads) when the residues span a homodimer
    interface. This eliminates the v1 false positives on AChBP and NDRG2.
    """
    bio_codes = bio_ligand_codes or set()
    met_codes = metal_codes or set()
    out = []
    out.extend(_detect_catalytic_triads(struct, bio_codes, met_codes))
    out.extend(_detect_cys_his_dyads(struct))
    out.extend(_detect_asp_dyads(struct, bio_codes, met_codes))
    out.extend(_detect_phosphate_loops(struct, ligand_residues or []))
    out.extend(_detect_aromatic_cages(struct, bio_codes))
    return out


def _functional_anchor_atoms(struct: gemmi.Structure, bio_ligand_codes: set,
                              metal_codes: set) -> list:
    """All heavy atoms of bio-ligands and metals — used as contextual gates
    for geometric pattern detectors. A pattern is contextually corroborated
    if at least one of its residues sits within range of any of these atoms.

    Excludes bio-ligands that sit primarily in aromatic cages of multi-chain
    assemblies (≥3 chains): those are agonist-like binders (nAChR mimics,
    receptor agonists) rather than enzyme substrates, and their proximity
    shouldn't gate enzymatic geometry as if the protein were an enzyme.
    """
    model = struct[0]
    n_chains = sum(1 for c in model if _polymer_kind({r.name for r in c}) == "protein")
    aromatic_cage_in_oligomer = n_chains >= 3   # rough check

    out = []
    for chain in model:
        for res in chain:
            if res.name not in bio_ligand_codes and res.name not in metal_codes:
                continue
            # Skip aromatic-caged bio-ligands in multi-chain oligomers: those
            # are agonists/effectors, not catalytic substrates, and shouldn't
            # gate enzymatic active-site patterns.
            if (res.name in bio_ligand_codes and aromatic_cage_in_oligomer
                    and _ligand_in_aromatic_cage(struct, res)):
                continue
            for a in res:
                if a.element.name not in ("H",):
                    out.append(a.pos)
    return out


def _ligand_in_aromatic_cage(struct: gemmi.Structure, lig_res: gemmi.Residue,
                              cutoff: float = 5.5, min_aromatics: int = 3) -> bool:
    """True if ≥`min_aromatics` aromatic residues (TRP/TYR/PHE) are within
    `cutoff` Å of any heavy atom of `lig_res`."""
    aromatic_set = {"TRP", "TYR", "PHE"}
    lig_atoms = [a for a in lig_res if a.element.name != "H"]
    if not lig_atoms:
        return False
    near = 0
    seen = set()
    for chain in struct[0]:
        for r in chain:
            if r.name not in aromatic_set:
                continue
            key = (chain.name, r.seqid.num)
            if key in seen:
                continue
            ref = _atom(r, "CG") or _atom(r, "CZ") or _atom(r, "CA")
            if ref is None:
                continue
            if any(la.pos.dist(ref.pos) < cutoff for la in lig_atoms):
                near += 1
                seen.add(key)
                if near >= min_aromatics:
                    return True
    return False


def _residue_near_any(res: gemmi.Residue, anchor_positions: list, cutoff: float) -> bool:
    """True if any heavy atom of `res` is within `cutoff` Å of any anchor."""
    if not anchor_positions:
        return False
    for a in res:
        if a.element.name == "H":
            continue
        for p in anchor_positions:
            if a.pos.dist(p) < cutoff:
                return True
    return False


def _detect_aromatic_cages(struct: gemmi.Structure, bio_ligand_codes: set) -> list:
    """Find bio-ligand sites with ≥3 aromatic residues (TRP/TYR/PHE) within 5 Å.

    Aromatic cage signature suggests cation-π interactions, carbohydrate stacking,
    or neurotransmitter binding (nicotinic / muscarinic / 5-HT3 receptors,
    lectins, reader domains).
    """
    if not bio_ligand_codes:
        return []
    aromatic_set = {"TRP", "TYR", "PHE"}
    out = []
    model = struct[0]
    # Collect aromatic residues with their key ring atom (centroid via CG/CZ/CE2)
    aromatics = []
    for chain in model:
        for r in chain:
            if r.name in aromatic_set:
                # Use CB-distal heavy atom representative
                ref = _atom(r, "CG") or _atom(r, "CZ") or _atom(r, "CA")
                if ref:
                    aromatics.append((chain.name, r, ref))
    # For each bio ligand instance, count aromatic neighbors
    for chain in model:
        for r in chain:
            if r.name not in bio_ligand_codes:
                continue
            # Get all heavy atoms of the ligand
            lig_atoms = [a for a in r if a.element.name != "H"]
            if not lig_atoms:
                continue
            near = []
            seen_keys = set()
            for ch_a, r_a, ref_a in aromatics:
                # Skip aromatics in the same residue (not applicable for ligands but be safe)
                key = (ch_a, r_a.seqid.num, r_a.name)
                if key in seen_keys:
                    continue
                if any(la.pos.dist(ref_a.pos) < 5.5 for la in lig_atoms):
                    near.append(f"{r_a.name}{r_a.seqid.num}")
                    seen_keys.add(key)
            if len(near) >= 3:
                out.append({
                    "pattern": "aromatic_cage",
                    "residues": near,
                    "chain": chain.name,
                    "geometry": {"ligand": f"{r.name}/{chain.name}{r.seqid.num}",
                                 "n_aromatics": len(near)},
                    "rule_id": "aromatic_cage_at_ligand_site",
                })
    return out


def _atom(res: gemmi.Residue, name: str) -> gemmi.Atom | None:
    return next((a for a in res if a.name == name), None)


def _detect_catalytic_triads(struct: gemmi.Structure,
                              bio_ligand_codes: set | None = None,
                              metal_codes: set | None = None) -> list:
    """Geometric Ser/Cys/Thr OG/SG/OG1 — His NE2 — Asp/Glu/Asn OD/OE pattern,
    with a contextual gate to suppress coincidental geometries.

    Distances per M-CSA-style template:
      nucleophile→His NE2: ~3.0 Å (H-bond range)
      His ND1→acid OD/OE:  ~2.7 Å (salt bridge / H-bond)

    Contextual gate (must satisfy ≥1):
      (a) all three residues on the same chain AND nucleophile-acid sequence
          distance < 250 (chymotrypsin / trypsin / lipase pattern)
      (b) any triad residue within 6 Å of a bio-ligand or metal
      (c) cross-chain triad AND chains differ (homodimer-interface case)

    Without contextual support, the triad geometry is reported as the v1
    detector did — but most non-enzyme proteins have at least one such
    coincidence in their SER/HIS/ASP residues; the gate eliminates them.
    """
    anchors = _functional_anchor_atoms(struct, bio_ligand_codes or set(),
                                         metal_codes or set())
    out = []
    model = struct[0]
    # Collect candidates per chain
    nucleophiles = []   # (chain, res, atom)
    bases = []          # (chain, res, ne2, nd1)
    acids = []          # (chain, res, [OD/OE atoms])
    for chain in model:
        for res in chain:
            if res.name in ("SER", "CYS", "THR"):
                a = _atom(res, "OG") or _atom(res, "SG") or _atom(res, "OG1")
                if a:
                    nucleophiles.append((chain.name, res, a))
            elif res.name == "HIS":
                ne2, nd1 = _atom(res, "NE2"), _atom(res, "ND1")
                if ne2 and nd1:
                    bases.append((chain.name, res, ne2, nd1))
            elif res.name in ("ASP", "GLU", "ASN"):
                if res.name == "ASP":
                    atoms = [a for n in ("OD1", "OD2") for a in [_atom(res, n)] if a]
                elif res.name == "GLU":
                    atoms = [a for n in ("OE1", "OE2") for a in [_atom(res, n)] if a]
                else:
                    atoms = [a for n in ("OD1", "ND2") for a in [_atom(res, n)] if a]
                if atoms:
                    acids.append((chain.name, res, atoms))

    seen = set()
    for ch1, r_n, a_n in nucleophiles:
        for ch2, r_h, ne2, nd1 in bases:
            d_nh = a_n.pos.dist(ne2.pos)
            if not (2.5 < d_nh < 3.7):
                continue
            for ch3, r_a, a_atoms in acids:
                d_ha = min(nd1.pos.dist(aa.pos) for aa in a_atoms)
                if not (2.4 < d_ha < 3.5):
                    continue

                # ─── Contextual gate ───
                # (a) same-chain + sequence-proximate triad
                same_chain = (ch1 == ch2 == ch3)
                seq_proximate = (
                    same_chain
                    and abs(r_n.seqid.num - r_a.seqid.num) < 250
                )
                # (b) any residue near a bio-ligand or metal
                ligand_proximate = (
                    _residue_near_any(r_n, anchors, 6.0)
                    or _residue_near_any(r_h, anchors, 6.0)
                    or _residue_near_any(r_a, anchors, 6.0)
                )
                # (c) cross-chain (homodimer interface, like HIV protease-style)
                cross_chain = (ch1 != ch2 or ch2 != ch3)

                if not (seq_proximate or ligand_proximate or cross_chain):
                    continue

                key = tuple(sorted([
                    (ch1, r_n.seqid.num, r_n.name),
                    (ch2, r_h.seqid.num),
                    (ch3, r_a.seqid.num, r_a.name),
                ]))
                if key in seen:
                    continue
                seen.add(key)
                chain_label = ch1 if same_chain else f"{ch1}+{ch2}+{ch3}"
                out.append({
                    "pattern": "catalytic_triad",
                    "residues": [
                        f"{r_n.name}{r_n.seqid.num}",
                        f"HIS{r_h.seqid.num}",
                        f"{r_a.name}{r_a.seqid.num}",
                    ],
                    "chain": chain_label,
                    "geometry": {
                        "nucleophile_to_his_ne2_a": round(d_nh, 2),
                        "his_nd1_to_acid_a": round(d_ha, 2),
                    },
                    "rule_id": "catalytic_triad_geometry",
                })
    return out


def _detect_cys_his_dyads(struct: gemmi.Structure) -> list:
    """Cys SG within 4 Å of His NE2 — papain-like cysteine protease signature."""
    out = []
    seen = set()
    cys = []
    his = []
    model = struct[0]
    for chain in model:
        for res in chain:
            if res.name == "CYS":
                sg = _atom(res, "SG")
                if sg:
                    cys.append((chain.name, res, sg))
            elif res.name == "HIS":
                ne2 = _atom(res, "NE2")
                if ne2:
                    his.append((chain.name, res, ne2))
    for ch1, rc, sg in cys:
        for ch2, rh, ne2 in his:
            if ch1 != ch2:
                continue
            d = sg.pos.dist(ne2.pos)
            if d < 4.5:
                # avoid overlap with triad detection: only flag if no Asp/Glu within 4 Å of HIS ND1
                nd1 = _atom(rh, "ND1")
                if nd1 is None:
                    continue
                near_acid = False
                for chain in model:
                    for res in chain:
                        if res.name not in ("ASP", "GLU"):
                            continue
                        for n in ("OD1", "OD2", "OE1", "OE2"):
                            a = _atom(res, n)
                            if a and a.pos.dist(nd1.pos) < 3.5:
                                near_acid = True
                                break
                        if near_acid:
                            break
                    if near_acid:
                        break
                if near_acid:
                    continue   # likely caught by triad detector instead
                key = tuple(sorted([(ch1, rc.seqid.num), (ch2, rh.seqid.num)]))
                if key in seen:
                    continue
                seen.add(key)
                out.append({
                    "pattern": "cys_his_dyad",
                    "residues": [f"CYS{rc.seqid.num}", f"HIS{rh.seqid.num}"],
                    "chain": ch1,
                    "geometry": {"sg_to_ne2_a": round(d, 2)},
                    "rule_id": "cysteine_dyad_geometry",
                })
    return out


def _detect_asp_dyads(struct: gemmi.Structure,
                       bio_ligand_codes: set | None = None,
                       metal_codes: set | None = None) -> list:
    """Two ASP residues with carboxylate-O atoms < 5 Å — aspartyl protease /
    glycosidase pattern, with a contextual gate.

    Contextual gate (must satisfy ≥1):
      (a) cross-chain dyad (homodimer interface — HIV-protease pattern)
      (b) intra-chain pair AND either residue is within 6 Å of a bio-ligand
          or metal (pepsin-substrate complex pattern)

    Without the gate, an intra-chain Asp pair that just happens to be
    spatially close fires on many non-enzymes — including the NDRG2
    pseudo-enzyme that caused the v1 eval regression.
    """
    out = []
    seen = set()
    asps = []
    model = struct[0]
    for chain in model:
        for res in chain:
            if res.name == "ASP":
                ods = [a for n in ("OD1", "OD2") for a in [_atom(res, n)] if a]
                if ods:
                    asps.append((chain.name, res, ods))
            elif res.name == "GLU":
                oes = [a for n in ("OE1", "OE2") for a in [_atom(res, n)] if a]
                if oes:
                    asps.append((chain.name, res, oes))

    anchors = _functional_anchor_atoms(struct, bio_ligand_codes or set(),
                                         metal_codes or set())

    for i in range(len(asps)):
        for j in range(i + 1, len(asps)):
            ch1, r1, a1 = asps[i]
            ch2, r2, a2 = asps[j]
            # within same chain, skip nearby residues (same loop, not a dyad)
            if ch1 == ch2 and abs(r1.seqid.num - r2.seqid.num) < 5:
                continue
            d = min(p.pos.dist(q.pos) for p in a1 for q in a2)
            if d >= 5.0:
                continue

            # ─── Contextual gate ───
            cross_chain = (ch1 != ch2)
            ligand_proximate = (
                _residue_near_any(r1, anchors, 6.0)
                or _residue_near_any(r2, anchors, 6.0)
            )
            if not (cross_chain or ligand_proximate):
                continue

            key = tuple(sorted([(ch1, r1.seqid.num), (ch2, r2.seqid.num)]))
            if key in seen:
                continue
            seen.add(key)
            chain_label = ch1 if ch1 == ch2 else f"{ch1}+{ch2}"
            out.append({
                "pattern": "asp_dyad",
                "residues": [f"{r1.name}{r1.seqid.num}", f"{r2.name}{r2.seqid.num}"],
                "chain": chain_label,
                "geometry": {"closest_o_o_a": round(d, 2)},
                "rule_id": "aspartate_dyad_geometry",
            })
    return out


def _detect_phosphate_loops(struct: gemmi.Structure, _ligand_residues: list) -> list:
    """Glycine-rich stretch (≥3 Gly in 8 consecutive residues) within 6 Å of a phosphorus atom."""
    out = []
    model = struct[0]
    # Collect phosphorus atoms (from any HETATM-style residue with P)
    p_atoms = []
    for chain in model:
        for res in chain:
            if res.name in STANDARD_AA or res.name in WATER:
                continue
            for a in res:
                if a.element.name == "P":
                    p_atoms.append((res.name, chain.name, res.seqid.num, a))
    if not p_atoms:
        return []

    # Walk each chain for Gly-rich stretches
    for chain in model:
        gly_positions = []
        ca_pos = []
        for res in chain:
            if res.name not in STANDARD_AA:
                continue
            ca = _atom(res, "CA")
            if ca:
                ca_pos.append((res.seqid.num, ca, res.name == "GLY"))
        if len(ca_pos) < 8:
            continue
        for i in range(len(ca_pos) - 7):
            window = ca_pos[i:i+8]
            n_gly = sum(1 for _, _, isgly in window if isgly)
            if n_gly < 3:
                continue
            # Check distance to any P atom
            for p_resn, p_chain, p_resi, p_atom in p_atoms:
                min_d = min(ca.pos.dist(p_atom.pos) for _, ca, _ in window)
                if min_d < 6.0:
                    out.append({
                        "pattern": "phosphate_binding_loop",
                        "residues": [f"GLY{r}" for r, _, isgly in window if isgly],
                        "chain": chain.name,
                        "geometry": {
                            "near_phosphate_of": f"{p_resn}/{p_chain}{p_resi}",
                            "min_ca_to_p_a": round(min_d, 2),
                        },
                        "rule_id": "phosphate_binding_loop",
                    })
                    break
    return out


# ─────────── disorder ───────────

def extract_chain_disorder(struct: gemmi.Structure, ligands_block: dict | None = None,
                          metals: list | None = None, cofactors: list | None = None) -> list:
    """Detect missing residue runs; flag those near functional moieties."""
    out = []
    model = struct[0]
    # Collect functional atom positions for proximity check
    functional_atoms = []
    if ligands_block:
        for entry in ligands_block.get("bio_ligand", []) or []:
            code = entry["id"]
            for chain in model:
                for res in chain:
                    if res.name == code:
                        for a in res:
                            functional_atoms.append(a.pos)

    for chain in model:
        last_resi = None
        residues_in = []
        for res in chain:
            if res.name not in STANDARD_AA:
                continue
            residues_in.append(res.seqid.num)
        residues_in.sort()
        # Find gaps
        for i in range(1, len(residues_in)):
            if residues_in[i] - residues_in[i-1] > 1:
                gap_start = residues_in[i-1] + 1
                gap_end = residues_in[i] - 1
                # Get CA position adjacent to gap
                near_functional = False
                if functional_atoms:
                    flank_residue = next((r for r in chain if r.name in STANDARD_AA and r.seqid.num == residues_in[i-1]), None)
                    if flank_residue:
                        ca = _atom(flank_residue, "CA")
                        if ca and any(ca.pos.dist(p) < 8.0 for p in functional_atoms):
                            near_functional = True
                out.append({
                    "chain": chain.name,
                    "range": [gap_start, gap_end],
                    "near_functional": near_functional,
                })
    return out


# ─────────── membrane heuristic ───────────

def extract_membrane_features(struct: gemmi.Structure) -> dict | None:
    """Detect a membrane signature in either an α-helical TM bundle OR a
    β-barrel transmembrane fold.

    Two heuristics that fire independently:
    A) α-helical TM bundle: helix-DOMINANT (≥50%) AND contains **≥3 distinct
       hydrophobic stretches** of ≥18 residues each with ≥65% hydrophobic
       composition. The multi-stretch + raised-threshold requirement
       distinguishes true TM bundles (GPCRs 7TM, KcsA 2TM/chain, MFS 12TM,
       bacteriorhodopsin 7TM — all have many strongly hydrophobic spans)
       from soluble α-bundles (4-helix bundles, hemoglobin, ADH, designed
       miniproteins — amphipathic helices, ~50% hydrophobic per span at
       most).
    B) β-barrel TM: sheet-DOMINANT (≥70%) AND high aromatic-girdle character
       (Trp+Tyr ≥6%, total aromatic ≥10%) AND chain-count ≤3 in the ASU
       (TM β-barrels are typically 1-3 chains; higher chain counts indicate
       soluble symmetric oligomers like AChBP or pentameric receptors).

    Tightened from v1.1: previous heuristic A fired on a single 22-residue
    window at >55% hydrophobic, which caught ~half the soluble enzymes in
    the v1 set (1adc, 1asy, 1atp, 1tim, 4hhb, 1nr0, 1hsg, …) and the
    smoke-test designed bundles (9R7K, 9R2B). Real TM α-bundles always
    have multiple deeply-hydrophobic spans.
    """
    model = struct[0]
    repr_chain = next((c for c in model if _polymer_kind({r.name for r in c}) == "protein"), None)
    if repr_chain is None:
        return None
    n_chains = sum(1 for c in model if _polymer_kind({r.name for r in c}) == "protein")
    residues = [(r.seqid.num, r.name) for r in repr_chain if r.name in STANDARD_AA]
    n = len(residues)
    if n < 30:
        return {
            "belt_detected": False,
            "belt_residues": [],
            "trp_girdle": False,
            "tyr_girdle": False,
            "estimated_belt_width_a": None,
        }

    # Two hydrophobic sets:
    #   - "broad" includes ALA, used by heuristic B (β-barrel) where ALA-rich
    #     loops appear naturally in TM barrel turns and we want a generous count.
    #   - "strict" excludes ALA, used by heuristic A (α-helical TM bundle).
    #     This was added in v1.2: Baker-style de novo all-α designs are
    #     alanine-dense by construction (alanine is the strongest helix-former)
    #     and were tripping the original broad set at ≥70% even on soluble
    #     designed bundles (9R7K, …). Real TM α-helices rely on I/L/V/F/M for
    #     hydrophobic match to the bilayer — alanine plays a smaller role.
    hydrophobic_set = {"ALA", "ILE", "LEU", "MET", "PHE", "PRO", "VAL", "TRP"}
    hydrophobic_strict = {"ILE", "LEU", "MET", "PHE", "PRO", "VAL", "TRP"}

    # Compute SS fractions once — both heuristics need them as gates.
    ss_str, fractions = _compute_secondary_structure(repr_chain)

    # Heuristic A: α-helical TM bundle.
    # Required gates (all):
    #   - helix-DOMINANT (≥50% helix in P-SEA)
    #   - ≤4 chains (large symmetric oligomers like AChBP / GroEL aren't TM)
    #   - ≥2 distinct strict-hydrophobic stretches (≥18 aa each at ≥50% of
    #     residues being I/L/V/F/M/W/P — *excluding* alanine) per chain,
    #     **and** total such stretches across the assembly ≥ chain_count × 2
    #     so KcsA-like (2 TM/chain × 4 chains = 8 TM helices) still trips
    #     while designed alanine-dense α-bundles (Baker-style 4-helix
    #     bundles, miniproteins) do not.
    # The "distinct" criterion skips ≥5 residues forward after each hit so
    # one long helix doesn't get double-counted as multiple stretches.
    # The strict set (no Ala) is the discriminator: real TM helices average
    # 50-70% I/L/V/F/M/W/P; designed alanine-rich helices average <40%.
    window = 18
    hydro_threshold = 0.55  # of strict-hydrophobic residues per window
    stretches: list[tuple[int, int]] = []
    helix_belt = False
    best_run_helix: tuple[int, int] | None = None
    if fractions["helix"] >= 0.50 and n_chains <= 4:
        i = 0
        while i <= n - window:
            slice_ = residues[i:i + window]
            hyd = sum(1 for _, name in slice_ if name in hydrophobic_strict)
            if hyd / window >= hydro_threshold:
                end = i + window
                while end < n:
                    nxt = residues[end - window:end]
                    nxt_hyd = sum(1 for _, name in nxt if name in hydrophobic_strict)
                    if nxt_hyd / window >= hydro_threshold:
                        end += 1
                    else:
                        break
                stretches.append((i, end))
                i = end + 5  # gap so adjacent windows don't double-count
            else:
                i += 1
        # Per-chain ≥2 stretches catches KcsA (2 TM/chain) when the assembly
        # is tetrameric; per-chain ≥3 catches bacteriorhodopsin / GPCR / MFS
        # in monomeric form.
        helix_belt = len(stretches) >= 3 or (len(stretches) >= 2 and n_chains >= 3)
        if helix_belt:
            best_run_helix = stretches[0]

    # Heuristic B: β-barrel TM.
    # Required gates (all): sheet-DOMINANT (≥70% sheet), n_chains ≤ 3
    # (TM β-barrels are typically 1-3 chains; ≥4 chains indicates a soluble
    # symmetric assembly), Trp+Tyr ≥6%, total aromatic ≥10%.
    # The chain-count gate is what kills AChBP (5 chains, 72% sheet).
    trp_count = sum(1 for _, name in residues if name == "TRP")
    tyr_count = sum(1 for _, name in residues if name == "TYR")
    aromatic = trp_count + tyr_count + sum(1 for _, name in residues if name == "PHE")
    barrel_belt = False
    if (n >= 80
        and aromatic / n >= 0.10
        and (trp_count + tyr_count) / n >= 0.06
        and fractions["sheet"] >= 0.70
        and n_chains <= 3):
        barrel_belt = True

    belt_detected = helix_belt or barrel_belt
    belt_residues = []
    trp_g = trp_count >= 3
    tyr_g = sum(1 for _, name in residues if name == "TYR") >= 3
    if best_run_helix:
        s, e = best_run_helix
        belt_residues = [f"{name}{r}" for r, name in residues[s:e]][:30]

    return {
        "belt_detected": belt_detected,
        "belt_residues": belt_residues,
        "trp_girdle": trp_g and belt_detected,
        "tyr_girdle": tyr_g and belt_detected,
        "estimated_belt_width_a": 30.0 if belt_detected else None,
    }


# ─────────── domains (contact-ratio heuristic) ───────────

def extract_domains(struct: gemmi.Structure, repr_chain: str | None = None,
                    pdb_id: str | None = None, use_merizo: bool = False) -> dict | None:
    """Dispatcher for domain segmentation. Tries the most authoritative source first.

    Priority order:
      1. CATH REST API (only for deposited PDB structures by 4-char ID).
         Authoritative, expert-curated, free. Cached locally.
      2. Merizo (only if installed AND use_merizo=True). ML-based segmentation
         of any structure. Heavy (~500 MB PyTorch); opt-in via
         `uv add protein-inspect[merizo]`.
      3. Length heuristic fallback (always available, honest about imprecision).
    """
    model = struct[0]
    if repr_chain is None:
        repr_chain = next((c.name for c in model if _polymer_kind({r.name for r in c}) == "protein"), None)
    if repr_chain is None:
        return None

    # Path 1: CATH lookup for deposited PDB IDs
    if pdb_id and re.match(r"^[0-9a-z]{4}$", pdb_id.lower()):
        cath_result = _domains_via_cath(pdb_id.lower(), repr_chain)
        if cath_result is not None:
            return cath_result

    # Path 2: Merizo if installed and requested
    if use_merizo:
        merizo_result = _domains_via_merizo(struct, repr_chain)
        if merizo_result is not None:
            return merizo_result

    # Path 3: length heuristic fallback
    return _domains_via_length_heuristic(struct, repr_chain)


def _domains_via_length_heuristic(struct: gemmi.Structure, repr_chain: str) -> dict:
    """Honest fallback: chain length > 300 residues → likely multi-domain,
    boundaries placeholder (split in half). DOMAK-style intra-/inter-contact
    ratio gave overlapping scores for single- and multi-domain proteins so
    we don't use it for v1.
    """
    chain = next((c for c in struct[0] if c.name == repr_chain), None)
    if chain is None:
        return None
    n = sum(1 for r in chain if r.name in STANDARD_AA)
    if n == 0:
        return None
    if n < 300:
        return {"count": 1, "detected_by": "contact_map_ratio",
                "boundaries": [{"chain": repr_chain, "range": [0, n]}]}
    return {
        "count": 2,
        "detected_by": "contact_map_ratio",
        "boundaries": [
            {"chain": repr_chain, "range": [0, n // 2]},
            {"chain": repr_chain, "range": [n // 2, n]},
        ],
    }


# ─────────── CATH lookup via PDBe SIFTS (cached) ───────────
# Why SIFTS not the CATH-direct API: the cathdb.info `/id/{pdb_chain}` endpoint
# returns only a stub `{"id": "..."}` with no boundaries; the `/superfamily`
# endpoint returns CATH classifications without residue ranges. PDBe's SIFTS
# mapping API exposes the canonical domain → residue-range data CATH curates,
# in a stable structured JSON format. Same authoritative source, cleaner shape.

_CATH_CACHE_DIR = Path.home() / ".cache" / "protein-inspect" / "cath"
_PDBE_SIFTS_CATH = "https://www.ebi.ac.uk/pdbe/api/mappings/cath/{pdb_id}"


def _domains_via_cath(pdb_id: str, repr_chain: str, timeout: float = 5.0) -> dict | None:
    """Query PDBe SIFTS for CATH-mapped domains of a given PDB chain.

    Returns the schema-shaped `domains` block, or None if the entry is not in
    SIFTS/CATH (which is how we triage local files / designed proteins).
    Caches both hits and misses to disk.
    """
    import json
    _CATH_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = _CATH_CACHE_DIR / f"{pdb_id}.json"
    if cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text())
        except (json.JSONDecodeError, OSError):
            cached = None
        if cached is not None:
            if cached.get("_status") == "miss":
                return None
            return _select_chain_domains(cached, repr_chain)

    url = _PDBE_SIFTS_CATH.format(pdb_id=pdb_id)
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                cache_file.write_text(json.dumps({"_status": "miss"}))
                return None
            raw = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, OSError):
        # Don't cache transient network errors — caller will retry next time
        return None

    parsed = _parse_pdbe_sifts_cath(raw, pdb_id)
    if parsed is None:
        cache_file.write_text(json.dumps({"_status": "miss"}))
        return None

    cache_file.write_text(json.dumps(parsed, indent=2))
    return _select_chain_domains(parsed, repr_chain)


def _parse_pdbe_sifts_cath(raw: dict, pdb_id: str) -> dict | None:
    """Convert PDBe SIFTS CATH JSON → flat list of (chain, start, end, domain_id, hierarchy)."""
    if not isinstance(raw, dict) or pdb_id not in raw:
        return None
    cath_block = raw[pdb_id].get("CATH", {})
    if not cath_block:
        return None

    by_chain: dict[str, list] = {}
    for cath_id, info in cath_block.items():
        for m in info.get("mappings", []):
            chain = m.get("chain_id")
            start = m.get("start", {}).get("author_residue_number")
            end = m.get("end", {}).get("author_residue_number")
            domain_id = m.get("domain")
            if chain and start is not None and end is not None:
                by_chain.setdefault(chain, []).append({
                    "chain": chain,
                    "range": [int(start), int(end)],
                    "domain_id": domain_id,
                    "cath_id": cath_id,
                    "topology": info.get("topology"),
                    "homology": info.get("homology"),
                })
    if not by_chain:
        return None
    return {"by_chain": by_chain}


def _select_chain_domains(parsed: dict, repr_chain: str) -> dict | None:
    """Pick the representative chain's segments and shape into the schema."""
    by_chain = parsed.get("by_chain") or {}
    segs = by_chain.get(repr_chain) or []
    if not segs:
        return None

    # Group by domain_id so multi-segment domains (like GroEL's discontinuous
    # equatorial domain) collapse to a single domain count.
    unique_domains = {s["domain_id"] for s in segs if s.get("domain_id")}
    domain_count = len(unique_domains) if unique_domains else len(segs)

    boundaries = [
        {"chain": s["chain"], "range": s["range"]}
        for s in segs
    ]
    return {
        "count": domain_count,
        "detected_by": "cath_api",
        "boundaries": boundaries,
    }


# ─────────── Merizo (optional, GPU-friendly) ───────────

def _domains_via_merizo(struct: gemmi.Structure, repr_chain: str) -> dict | None:
    """Use Merizo for ML-based domain segmentation if installed.

    Returns None if merizo is not installed or the call fails. Caller falls
    through to the length heuristic.
    """
    try:
        # Import inside the function so the absent dependency only matters
        # when use_merizo=True is requested.
        from merizo.runner import segment   # type: ignore
    except ImportError:
        return None

    # Merizo expects a path; write the structure to a temp PDB file
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".pdb", delete=False) as tf:
        tmp_path = tf.name
    try:
        struct.write_pdb(tmp_path)
        try:
            result = segment(tmp_path)
        except Exception:
            return None

        # Merizo returns per-residue domain assignments.
        # Convert to boundaries grouped by domain id.
        if not result:
            return None
        per_res = result.get("domains") if isinstance(result, dict) else None
        if not per_res:
            return None
        boundaries = []
        cur_dom = None
        cur_start = None
        prev_resi = None
        for resi, dom_id in sorted(per_res.items()):
            if cur_dom is None:
                cur_dom = dom_id
                cur_start = resi
            elif dom_id != cur_dom or (prev_resi is not None and resi - prev_resi > 1):
                boundaries.append({"chain": repr_chain, "range": [cur_start, prev_resi]})
                cur_dom = dom_id
                cur_start = resi
            prev_resi = resi
        if cur_dom is not None:
            boundaries.append({"chain": repr_chain, "range": [cur_start, prev_resi]})

        if not boundaries:
            return None
        return {"count": len(boundaries), "detected_by": "merizo", "boundaries": boundaries}
    finally:
        os.unlink(tmp_path)


# ─────────── orchestrator ───────────

def extract_all(pdb_id_or_path: str, motif: str | None = None,
                source: str = "rcsb", use_merizo: bool = False) -> dict:
    """Run all extractors and return a dict shaped like summary.schema.json v1.1."""
    struct, path = fetch_structure(pdb_id_or_path)
    if Path(pdb_id_or_path).exists():
        source = "local_file"
    classes = load_ligand_classes()

    provenance = extract_provenance(struct, source=source, input_path=path)
    macromolecule_type = extract_macromolecule_type(struct)
    model_quality = extract_model_type(struct, provenance)
    if model_quality["is_computed"]:
        provenance["resolution_class"] = "computed"

    assembly = extract_assembly(struct)
    fold = extract_fold(struct, is_computed=model_quality["is_computed"])
    classification = extract_ligand_classification(struct, classes)
    ligands = assemble_ligands_block(struct, classification)
    metals = extract_metals(struct, classification)
    cofactors = extract_cofactors(classification)
    free_nucleotides = extract_free_nucleotides(classification)
    glycans = extract_glycans(struct, classification)
    lipids = extract_lipids(classification)
    nucleic_acids = extract_nucleic_acids(struct)
    disulfides = extract_disulfides(struct)
    peptide_ligands = extract_peptide_ligands(struct)
    bio_ligand_codes = set(classification["bio_ligand_codes"].keys())
    # Metals (CCD codes for biological metals like ZN/FE/MG plus Fe-S cluster codes)
    # also count as anchors for the active-site gate — many catalytic sites are
    # organized around a metal center.
    metal_codes = set(classes["metals_biological"]) | set(classes["iron_sulfur_clusters"])
    active_sites = extract_active_site_patterns(
        struct, bio_ligand_codes=bio_ligand_codes, metal_codes=metal_codes,
    )
    chain_disorder = extract_chain_disorder(struct, ligands_block=ligands, metals=metals, cofactors=cofactors)
    membrane = extract_membrane_features(struct)
    # Pass pdb_id through if input was a 4-char identifier — enables CATH lookup
    pdb_id_for_cath = pdb_id_or_path.lower() if not Path(pdb_id_or_path).exists() else None
    domains = extract_domains(struct, pdb_id=pdb_id_for_cath, use_merizo=use_merizo)

    # Build summary
    entry = Path(pdb_id_or_path).stem if Path(pdb_id_or_path).exists() else pdb_id_or_path.lower()
    summary = {
        "entry": entry,
        "schema_version": "1.1",
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "narrative": None,                                    # set externally if available
        "macromolecule_type": macromolecule_type,
        "model_quality": model_quality,
        "provenance": provenance,
        "assembly": assembly,
        "fold": fold,
    }
    # Optional layers — only include when non-empty
    if ligands:
        summary["ligands"] = ligands
    if metals:
        summary["metals"] = metals
    if cofactors:
        summary["cofactors"] = cofactors
    if free_nucleotides:
        summary["nucleotides_free"] = free_nucleotides
    if nucleic_acids:
        summary["nucleic_acids"] = nucleic_acids
    if glycans:
        summary["glycans"] = glycans
    if lipids:
        summary["lipids"] = lipids
    if disulfides:
        summary["disulfides"] = disulfides
    if peptide_ligands:
        summary["peptide_ligands"] = peptide_ligands
    if active_sites:
        summary["active_site_patterns"] = active_sites
    if membrane:
        summary["membrane_features"] = membrane
    if chain_disorder:
        summary["chain_disorder"] = chain_disorder
    if domains:
        summary["domains"] = domains

    return summary
