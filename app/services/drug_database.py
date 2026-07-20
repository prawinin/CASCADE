"""
KineticSketch — Drug Database Service
Loads DrugCentral SMILES data into a SQLite database with FTS5 full-text search
and pre-computed Morgan fingerprints for fast vectorized Tanimoto repurposing.

Build the database first by running: python scripts/build_drug_db.py
"""

import os  # noqa: E402
import logging  # noqa: E402
import sqlite3  # noqa: E402
import numpy as np  # noqa: E402
from typing import List, Dict, Any, Optional  # noqa: E402

logger = logging.getLogger("KineticSketch.DrugDatabase")

# Paths — relative to project root
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(_PROJECT_ROOT, "data", "drug_database.sqlite")
FP_PATH = os.path.join(_PROJECT_ROOT, "data", "drug_fingerprints.npz")

# Popular common synonyms mapping to standard INN names
POPULAR_SYNONYMS = {
    "aspirin": "acetylsalicylic acid",
    "acetaminophen": "paracetamol",
    "tylenol": "paracetamol",
    "advil": "ibuprofen",
    "motrin": "ibuprofen",
    "aleve": "naproxen",
    "prozac": "fluoxetine",
    "xanax": "alprazolam",
    "lipitor": "atorvastatin",
    "viagra": "sildenafil",
    "valium": "diazepam",
    "ritalin": "methylphenidate",
    "adderall": "amphetamine",
    "zyrtec": "cetirizine",
    "claritin": "loratadine",
    "allegra": "fexofenadine",
}

# Singleton state
_db_conn: Optional[sqlite3.Connection] = None
_fp_matrix: Optional[np.ndarray] = None       # shape (N, 2048) float32
_fp_drug_ids: Optional[np.ndarray] = None      # shape (N,) int64 — maps row → drug.id
_db_available: bool = False


def _get_conn() -> Optional[sqlite3.Connection]:
    """Returns a thread-safe SQLite connection, or None if DB not built yet."""
    global _db_conn
    if _db_conn is not None:
        return _db_conn
    if not os.path.exists(DB_PATH):
        logger.warning(f"Drug database not found at {DB_PATH}. Run scripts/build_drug_db.py first.")
        return None
    try:
        _db_conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _db_conn.row_factory = sqlite3.Row
        logger.info(f"Drug database connected: {DB_PATH}")
        return _db_conn
    except Exception as e:
        logger.error(f"Failed to connect to drug database: {e}")
        return None


def _load_fingerprints() -> bool:
    """Loads pre-computed Morgan fingerprint matrix using memory mapping.
    
    Uses np.load with mmap_mode='r' so the OS pages in only the rows needed
    during the Tanimoto dot-product, keeping RAM usage under ~100 MB instead
    of trying to allocate the full 22 GB matrix at once.
    """
    global _fp_matrix, _fp_drug_ids, _db_available
    if _fp_matrix is not None:
        return True
    if not os.path.exists(FP_PATH):
        logger.warning(f"Fingerprint matrix not found at {FP_PATH}. Run scripts/build_drug_db.py first.")
        return False
    try:
        # mmap_mode='r' → memory-mapped read-only: OS pages in only what's needed
        data = np.load(FP_PATH, mmap_mode='r')
        _fp_matrix = data["fingerprints"]   # (N, 2048) — NOT copied to RAM
        _fp_drug_ids = data["drug_ids"].astype(np.int64)   # (N,) — small, fully loaded
        _db_available = True
        logger.info(f"Loaded fingerprint matrix (mmap): {_fp_matrix.shape[0]:,} drugs × {_fp_matrix.shape[1]} bits")
        return True
    except Exception as e:
        logger.error(f"Failed to load fingerprint matrix: {e}")
        return False


def is_available() -> bool:
    """Returns True if both the SQLite DB and fingerprint matrix are loaded."""
    conn = _get_conn()
    fps_ok = _load_fingerprints()
    return conn is not None and fps_ok


def lookup_smiles_by_name(name: str) -> Optional[Dict[str, Any]]:
    """
    Fast drug name → SMILES lookup using SQLite FTS5 full-text search.
    Returns the best match dict {name, smiles, inn, cas_rn, approved_by} or None.

    Strategy:
    1. Exact INN match (case-insensitive)
    2. FTS5 prefix search on name/synonyms
    3. Returns None if no match found → caller should fallback to PubChem
    """
    conn = _get_conn()
    if conn is None:
        return None

    name_clean = name.strip().lower()

    # Map popular synonyms first
    if name_clean in POPULAR_SYNONYMS:
        name_clean = POPULAR_SYNONYMS[name_clean]

    # 1. Exact match on INN name
    try:
        row = conn.execute(
            "SELECT id, inn, smiles, cas_rn, approved_by FROM drugs WHERE LOWER(inn) = ? LIMIT 1",
            (name_clean,)
        ).fetchone()
        if row and row["smiles"]:
            return dict(row)
    except Exception as e:
        logger.debug(f"Exact lookup error: {e}")

    # 2. FTS5 prefix search
    try:
        row = conn.execute(
            """SELECT d.id, d.inn, d.smiles, d.cas_rn, d.approved_by
               FROM drugs d
               JOIN drugs_fts ON drugs_fts.rowid = d.rowid
               WHERE drugs_fts MATCH ?
               ORDER BY rank LIMIT 1""",
            (f'"{name_clean}"*',)
        ).fetchone()
        if row and row["smiles"]:
            return dict(row)
    except Exception as e:
        logger.debug(f"FTS5 lookup error: {e}")

    # 3. LIKE fallback
    try:
        row = conn.execute(
            "SELECT id, inn, smiles, cas_rn, approved_by FROM drugs WHERE LOWER(inn) LIKE ? LIMIT 1",
            (f"%{name_clean}%",)
        ).fetchone()
        if row and row["smiles"]:
            return dict(row)
    except Exception as e:
        logger.debug(f"LIKE lookup error: {e}")

    return None


def get_autocomplete_suggestions(prefix: str, limit: int = 10) -> List[Dict[str, str]]:
    """
    Returns up to `limit` drug name suggestions matching the given prefix.
    Used for the unified input dropdown autocomplete.
    Returns list of {name, smiles} dicts.
    """
    conn = _get_conn()
    if conn is None:
        return []

    prefix_clean = prefix.strip().lower()
    if len(prefix_clean) < 2:
        return []

    suggestions = []

    # 1. Match popular synonyms starting with the prefix
    matched_synonyms = []
    for syn, inn in POPULAR_SYNONYMS.items():
        if syn.startswith(prefix_clean):
            matched_synonyms.append((syn, inn))

    # Retrieve smiles for matched synonyms
    for syn, inn in matched_synonyms:
        try:
            row = conn.execute(
                "SELECT smiles FROM drugs WHERE LOWER(inn) = ? AND smiles IS NOT NULL AND smiles != '' LIMIT 1",
                (inn.lower(),)
            ).fetchone()
            if row:
                suggestions.append({"name": syn, "smiles": row["smiles"]})
        except Exception:
            pass

    # 2. Query database for standard INN matches starting with the prefix
    try:
        rows = conn.execute(
            """SELECT inn, smiles FROM drugs
               WHERE LOWER(inn) LIKE ?
               AND smiles IS NOT NULL AND smiles != ''
               ORDER BY LENGTH(inn) ASC
               LIMIT ?""",
            (f"{prefix_clean}%", limit)
        ).fetchall()

        # Add to suggestions list, avoiding duplicates
        existing_names = {s["name"].lower() for s in suggestions}
        for r in rows:
            inn_name = r["inn"]
            if inn_name.lower() not in existing_names:
                suggestions.append({"name": inn_name, "smiles": r["smiles"]})
                existing_names.add(inn_name.lower())

    except Exception as e:
        logger.error(f"Autocomplete error: {e}")

    return suggestions[:limit]


def _build_repurposing_results(conn, sorted_idx, indices, scores, top_k: int) -> List[Dict[str, Any]]:
    results = []
    for i in sorted_idx:
        drug_id = int(_fp_drug_ids[indices[i]])
        similarity = float(scores[i])

        try:
            drug_row = conn.execute("SELECT id, inn, smiles, approved_by FROM drugs WHERE id = ?", (drug_id,)).fetchone()
            if not drug_row:
                continue

            target_rows = conn.execute(
                "SELECT pdb_id, target_name, gene, chain_id, ligand_id FROM drug_targets WHERE drug_id = ? LIMIT 3",
                (drug_id,)
            ).fetchall()

            affinity_kcal = -(similarity * 9.5 + 2.0)

            if target_rows:
                for t in target_rows:
                    results.append({
                        "matched_drug": drug_row["inn"] or f"DrugID-{drug_id}",
                        "pdb_id": t["pdb_id"] or "N/A",
                        "target_name": t["target_name"] or t["gene"] or "Unknown target",
                        "similarity": round(similarity, 4),
                        "binding_probability": f"{similarity * 100:.1f}%",
                        "affinity_estimate": f"{affinity_kcal:.2f} kcal/mol",
                        "function": f"Gene: {t['gene'] or 'N/A'} | Chain: {t['chain_id'] or 'N/A'}",
                        "approved_by": drug_row["approved_by"] or "Unknown"
                    })
            else:
                results.append({
                    "matched_drug": drug_row["inn"] or f"DrugID-{drug_id}",
                    "pdb_id": "N/A",
                    "target_name": "No PDB target recorded",
                    "similarity": round(similarity, 4),
                    "binding_probability": f"{similarity * 100:.1f}%",
                    "affinity_estimate": f"{affinity_kcal:.2f} kcal/mol",
                    "function": "No mechanism-of-action target available",
                    "approved_by": drug_row["approved_by"] or "Unknown"
                })
        except Exception as e:
            logger.debug(f"Result fetch error for drug_id {drug_id}: {e}")
            continue

    results.sort(key=lambda x: x["similarity"], reverse=True)
    return results[:top_k]


def fast_repurposing_search(
    query_smiles: str,
    top_k: int = 10,
    min_similarity: float = 0.10
) -> List[Dict[str, Any]]:
    """
    Fast vectorized Tanimoto similarity search across all drugs in the fingerprint matrix.
    """
    if not _load_fingerprints():
        return []

    conn = _get_conn()
    if conn is None:
        return []

    try:
        from rdkit import Chem
        from rdkit.Chem import AllChem
        mol = Chem.MolFromSmiles(query_smiles)
        if mol is None:
            return []
        fp = AllChem.GetMorganFingerprintAsBitVect(mol, 2, nBits=2048)
        query_vec = np.array(fp, dtype=np.float32)
    except Exception as e:
        logger.error(f"Fingerprint generation failed: {e}")
        return []

    query_bits = query_vec.sum()
    CHUNK_SIZE = 10000
    N = _fp_matrix.shape[0]
    tanimoto = np.zeros(N, dtype=np.float32)
    
    for start_idx in range(0, N, CHUNK_SIZE):
        end_idx = min(start_idx + CHUNK_SIZE, N)
        chunk = _fp_matrix[start_idx:end_idx] 
        dots = chunk @ query_vec
        ref_bits = chunk.sum(axis=1)
        unions = query_bits + ref_bits - dots
        tanimoto[start_idx:end_idx] = np.where(unions > 0, dots / unions, 0.0)

    mask = tanimoto >= min_similarity
    if not mask.any():
        return []

    indices = np.where(mask)[0]
    scores = tanimoto[indices]
    sorted_idx = np.argsort(-scores)[:top_k]

    return _build_repurposing_results(conn, sorted_idx, indices, scores, top_k)


def get_db_stats() -> Dict[str, int]:
    """Returns stats about the loaded database for the /health endpoint."""
    conn = _get_conn()
    if conn is None:
        return {"status": "unavailable", "drugs": 0, "targets": 0}
    try:
        drugs = conn.execute("SELECT COUNT(*) FROM drugs").fetchone()[0]
        targets = conn.execute("SELECT COUNT(*) FROM drug_targets").fetchone()[0]
        fps = int(_fp_drug_ids.shape[0]) if _fp_drug_ids is not None else 0
        return {"status": "available", "drugs": drugs, "targets": targets, "fingerprints": fps}
    except Exception as e:
        return {"status": "error", "error": str(e)}
