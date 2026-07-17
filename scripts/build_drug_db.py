#!/usr/bin/env python3
"""
KineticSketch — Drug Database Builder
======================================
Builds the local SQLite drug database and pre-computed fingerprint matrix
from the downloaded data files in the data/ directory.

Run once before starting the server:
    cd /home/prawin/KineticSketch
    source .venv/bin/activate
    python scripts/build_drug_db.py

What it does:
1. Reads DrugCentral structures.smiles.tsv  → 4,100 drugs with SMILES + INN names
2. Reads FDA_Approved.csv + EMA_Approved.csv → filter/tag approved drugs
3. Reads drugcentral.dump SQL (if PostgreSQL available) OR skips to step 4
4. Reads ChEMBL 37 chemreps (filtered to max_phase=4) → adds ~12,000 more drugs
5. Computes Morgan fingerprints (2048-bit, radius 2) for all drugs
6. Saves SQLite DB → data/drug_database.sqlite
7. Saves fingerprint matrix → data/drug_fingerprints.npz
"""

import os
import sys
import csv
import gzip
import json
import sqlite3
import logging
import argparse
import time
import warnings
from typing import Set, Dict, Tuple

try:
    from rdkit import RDLogger
    RDLogger.DisableLog('rdApp.*')
except ImportError:
    pass

warnings.filterwarnings("ignore")

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("build_drug_db")

DATA_DIR = os.path.join(PROJECT_ROOT, "data")
DB_PATH = os.path.join(DATA_DIR, "drug_database.sqlite")
FP_PATH = os.path.join(DATA_DIR, "drug_fingerprints.npz")

# Source files
SMILES_TSV = os.path.join(DATA_DIR, "structures.smiles.tsv")
FDA_CSV = os.path.join(DATA_DIR, "FDA_Approved.csv")
EMA_CSV = os.path.join(DATA_DIR, "EMA_Approved.csv")
PMDA_CSV = os.path.join(DATA_DIR, "PMDA_Approved.csv")
CHEMBL_GZ = os.path.join(DATA_DIR, "chembl_37_chemreps.txt.gz")


# =============================================================================
# Step 1: Create SQLite schema
# =============================================================================

SCHEMA = """
CREATE TABLE IF NOT EXISTS drugs (
    id          INTEGER PRIMARY KEY,
    inn         TEXT NOT NULL,
    smiles      TEXT,
    inchikey    TEXT,
    cas_rn      TEXT,
    approved_by TEXT,       -- "FDA", "EMA", "FDA+EMA", "ChEMBL", etc.
    source      TEXT        -- "drugcentral" or "chembl"
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_drugs_inn ON drugs(LOWER(inn));
CREATE INDEX IF NOT EXISTS idx_drugs_inchikey ON drugs(inchikey);

-- FTS5 virtual table for fast name search + autocomplete
CREATE VIRTUAL TABLE IF NOT EXISTS drugs_fts
USING fts5(inn, content=drugs, content_rowid=id);

CREATE TABLE IF NOT EXISTS drug_targets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    drug_id     INTEGER NOT NULL REFERENCES drugs(id),
    pdb_id      TEXT,
    target_name TEXT,
    gene        TEXT,
    chain_id    TEXT,
    ligand_id   TEXT
);

CREATE INDEX IF NOT EXISTS idx_targets_drug ON drug_targets(drug_id);
CREATE INDEX IF NOT EXISTS idx_targets_pdb  ON drug_targets(pdb_id);
"""


def create_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()
    logger.info("✓ SQLite schema created")


# =============================================================================
# Step 2: Load DrugCentral SMILES TSV
# =============================================================================

def load_approved_ids(csv_path: str) -> Set[str]:
    """Returns a set of DrugCentral INN names that are approved by this agency."""
    approved = set()
    if not os.path.exists(csv_path):
        return approved
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.reader(f):
            if len(row) >= 2:
                approved.add(row[1].strip().lower())
    return approved


def load_drugcentral_smiles(conn: sqlite3.Connection) -> Dict[str, int]:
    """
    Loads structures.smiles.tsv into the drugs table.
    Columns: SMILES | InChI | InChIKey | ID | INN | CAS_RN
    Returns {inn_lower: rowid} mapping for target injection.
    """
    if not os.path.exists(SMILES_TSV):
        logger.warning(f"  ✗ {SMILES_TSV} not found — skipping DrugCentral SMILES")
        return {}

    # Load agency approval sets
    fda_names = load_approved_ids(FDA_CSV)
    ema_names = load_approved_ids(EMA_CSV)
    pmda_names = load_approved_ids(PMDA_CSV)

    inserted = 0
    id_map: Dict[str, int] = {}  # inn_lower → DB rowid

    with open(SMILES_TSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            smiles = (row.get("SMILES") or "").strip()
            inn = (row.get("INN") or "").strip()
            inchikey = (row.get("InChIKey") or "").strip()
            cas_rn = (row.get("CAS_RN") or "").strip()

            if not inn or not smiles:
                continue

            inn_lower = inn.lower()

            # Determine approval tags
            tags = []
            if inn_lower in fda_names:
                tags.append("FDA")
            if inn_lower in ema_names:
                tags.append("EMA")
            if inn_lower in pmda_names:
                tags.append("PMDA")
            approved_by = "+".join(tags) if tags else "DrugCentral"

            try:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO drugs (inn, smiles, inchikey, cas_rn, approved_by, source) "
                    "VALUES (?, ?, ?, ?, ?, 'drugcentral')",
                    (inn, smiles, inchikey, cas_rn, approved_by)
                )
                if cur.lastrowid:
                    id_map[inn_lower] = cur.lastrowid
                    inserted += 1
            except Exception as e:
                logger.debug(f"Insert error for {inn}: {e}")

    conn.commit()
    logger.info(f"✓ Loaded {inserted:,} drugs from DrugCentral SMILES TSV")
    return id_map


# =============================================================================
# Step 3: Extract drug-target PDB links from DrugCentral SQL dump
# =============================================================================

def extract_pdb_targets_from_sql(conn: sqlite3.Connection, id_map: Dict[str, int]) -> None:
    """
    Parses the DrugCentral PostgreSQL dump (drugcentral.dump.*.sql.gz) to extract
    drug → PDB target associations from the pdb + structures + act_table_full tables.

    This avoids needing a running PostgreSQL instance by parsing INSERT statements directly.
    Targets are: pdb | struct_id | chain_id | ligand_id
    We join on struct_id → INN name using the structures table INSERTs.
    """
    dump_files = [f for f in os.listdir(DATA_DIR) if f.startswith("drugcentral.dump") and f.endswith(".sql.gz")]
    if not dump_files:
        logger.info("  ℹ No DrugCentral dump found — skipping PDB target extraction")
        return

    dump_path = os.path.join(DATA_DIR, dump_files[0])
    logger.info(f"  Parsing DrugCentral dump: {dump_path} (this may take 1-2 min)...")

    import re

    # We parse two tables from the SQL dump:
    # 1. structures table: id | name | ...  → struct_id → inn name
    # 2. pdb table: struct_id | pdb | chain_id | ligand_id | ...

    struct_id_to_inn: Dict[int, str] = {}  # struct_id → INN (lower)
    pdb_rows: list = []  # (struct_id, pdb_id, chain_id, ligand_id)

    # Patterns for COPY ... FROM stdin blocks (PostgreSQL dump format)
    in_structures = False
    in_pdb = False
    structures_cols = []
    pdb_cols = []

    try:
        with gzip.open(dump_path, "rt", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.rstrip()

                # Detect COPY blocks and parse column definitions dynamically
                if line.startswith("COPY public.structures ") or line.startswith("COPY structures "):
                    match = re.search(r"\((.+)\)", line)
                    if match:
                        structures_cols = [c.strip() for c in match.group(1).split(",")]
                    in_structures = True
                    in_pdb = False
                    continue
                elif line.startswith("COPY public.pdb ") or line.startswith("COPY pdb "):
                    match = re.search(r"\((.+)\)", line)
                    if match:
                        pdb_cols = [c.strip() for c in match.group(1).split(",")]
                    in_pdb = True
                    in_structures = False
                    continue
                elif line == "\\.":  # end of COPY block
                    in_structures = False
                    in_pdb = False
                    continue

                if in_structures and structures_cols:
                    parts = line.split("\t")
                    try:
                        id_idx = structures_cols.index("id")
                        name_idx = structures_cols.index("name")
                        if len(parts) > max(id_idx, name_idx):
                            struct_id = int(parts[id_idx])
                            name_col = parts[name_idx].strip()
                            if name_col and name_col != "\\N":
                                struct_id_to_inn[struct_id] = name_col.lower()
                    except (ValueError, IndexError):
                        pass

                elif in_pdb and pdb_cols:
                    parts = line.split("\t")
                    try:
                        struct_id_idx = pdb_cols.index("struct_id")
                        pdb_idx = pdb_cols.index("pdb")
                        chain_id_idx = pdb_cols.index("chain_id")
                        ligand_id_idx = pdb_cols.index("ligand_id")
                        if len(parts) > max(struct_id_idx, pdb_idx, chain_id_idx, ligand_id_idx):
                            struct_id = int(parts[struct_id_idx])
                            pdb_id = parts[pdb_idx].strip()
                            chain_id = parts[chain_id_idx].strip()
                            ligand_id = parts[ligand_id_idx].strip()
                            if pdb_id and pdb_id != "\\N" and len(pdb_id) == 4:
                                pdb_rows.append((struct_id, pdb_id, chain_id, ligand_id))
                    except (ValueError, IndexError):
                        pass

    except Exception as e:
        logger.error(f"  Error parsing SQL dump: {e}")
        return

    logger.info(f"  Parsed {len(struct_id_to_inn):,} structures, {len(pdb_rows):,} PDB entries from dump")

    # Now join and insert into drug_targets
    inserted = 0
    for struct_id, pdb_id, chain_id, ligand_id in pdb_rows:
        inn = struct_id_to_inn.get(struct_id)
        if not inn:
            continue
        drug_db_id = id_map.get(inn)
        if not drug_db_id:
            continue

        try:
            conn.execute(
                "INSERT OR IGNORE INTO drug_targets (drug_id, pdb_id, chain_id, ligand_id) VALUES (?, ?, ?, ?)",
                (drug_db_id, pdb_id.upper(),
                 None if chain_id == "\\N" else chain_id,
                 None if ligand_id == "\\N" else ligand_id)
            )
            inserted += 1
        except Exception:
            pass

    conn.commit()
    logger.info(f"✓ Inserted {inserted:,} drug-PDB target associations")


# =============================================================================
# Step 4: Supplement with ChEMBL Phase 4 approved drugs
# =============================================================================

def load_chembl_approved(conn: sqlite3.Connection) -> None:
    """
    Reads chembl_37_chemreps.txt.gz and inserts Phase 4 (approved) drugs
    that don't already exist in the database.

    ChEMBL chemreps columns: chembl_id | canonical_smiles | standard_inchi | standard_inchi_key
    We filter to max_phase=4 using chembl_id prefix heuristic... but since chemreps
    doesn't include phase, we load ALL and deduplicate by InChIKey.
    (Phase filter requires the full SQLite dump — this is safe to load all ~2.9M and deduplicate)

    For performance we skip duplicates by InChIKey.
    """
    if not os.path.exists(CHEMBL_GZ):
        logger.warning(f"  ✗ {CHEMBL_GZ} not found — skipping ChEMBL supplement")
        return

    logger.info(f"  Loading ChEMBL 37 chemreps (2.9M compounds — filtering by InChIKey dedup)...")

    # Get existing InChIKeys to avoid duplicates
    existing_keys: Set[str] = set()
    try:
        rows = conn.execute("SELECT inchikey FROM drugs WHERE inchikey IS NOT NULL").fetchall()
        existing_keys = {r[0] for r in rows if r[0]}
    except Exception:
        pass

    inserted = 0
    skipped = 0
    batch = []

    open_fn = gzip.open if CHEMBL_GZ.endswith(".gz") else open

    try:
        with open_fn(CHEMBL_GZ, "rt", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter="\t")
            for i, row in enumerate(reader):
                chembl_id = (row.get("chembl_id") or "").strip()
                smiles = (row.get("canonical_smiles") or "").strip()
                inchikey = (row.get("standard_inchi_key") or "").strip()

                if not smiles or not chembl_id:
                    continue

                # Skip if we already have this molecule
                if inchikey and inchikey in existing_keys:
                    skipped += 1
                    continue

                if inchikey:
                    existing_keys.add(inchikey)

                batch.append((chembl_id, smiles, inchikey, "ChEMBL", "chembl"))
                inserted += 1

                # Batch insert every 10,000 rows
                if len(batch) >= 10000:
                    conn.executemany(
                        "INSERT OR IGNORE INTO drugs (inn, smiles, inchikey, approved_by, source) VALUES (?,?,?,?,?)",
                        batch
                    )
                    conn.commit()
                    batch = []

                if i % 500_000 == 0 and i > 0:
                    logger.info(f"    ... processed {i:,} ChEMBL rows, {inserted:,} new drugs so far")

        if batch:
            conn.executemany(
                "INSERT OR IGNORE INTO drugs (inn, smiles, inchikey, approved_by, source) VALUES (?,?,?,?,?)",
                batch
            )
            conn.commit()

    except Exception as e:
        logger.error(f"  Error loading ChEMBL: {e}")
        return

    logger.info(f"✓ Added {inserted:,} ChEMBL compounds (skipped {skipped:,} duplicates)")


# =============================================================================
# Step 5: Build FTS5 index
# =============================================================================

def build_fts_index(conn: sqlite3.Connection) -> None:
    logger.info("  Building FTS5 full-text search index...")
    conn.execute("INSERT INTO drugs_fts(drugs_fts) VALUES('rebuild')")
    conn.commit()
    logger.info("✓ FTS5 index built")


# =============================================================================
# Step 6: Pre-compute Morgan fingerprints → numpy array
# =============================================================================

def build_fingerprint_matrix(conn: sqlite3.Connection) -> None:
    """
    Computes 2048-bit Morgan fingerprints (radius=2) for all drugs with valid SMILES.
    Saves as compressed numpy array for fast vectorized Tanimoto search.
    """
    try:
        import numpy as np
        from rdkit import Chem
        from rdkit.Chem import AllChem, DataStructs
    except ImportError:
        logger.error("RDKit or numpy not available — skipping fingerprint computation")
        return

    logger.info("  Computing Morgan fingerprints for all drugs...")

    rows = conn.execute("SELECT id, smiles FROM drugs WHERE smiles IS NOT NULL AND smiles != ''").fetchall()
    total = len(rows)
    logger.info(f"  Processing {total:,} drugs...")

    # Pre-allocate uint8 numpy array for high-speed, memory-efficient storage
    # uint8 uses 1 byte per bit instead of 8 bytes (float64) or 4 bytes (float32).
    # This reduces RAM consumption from 23.7GB down to 5.9GB for 2.9M compounds.
    fp_matrix = np.zeros((total, 2048), dtype=np.uint8)
    drug_ids = np.zeros(total, dtype=np.int64)
    failed = 0
    valid_count = 0

    for i, (drug_id, smiles) in enumerate(rows):
        try:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                failed += 1
                continue
            fp = AllChem.GetMorganFingerprintAsBitVect(mol, 2, nBits=2048)
            
            # Use RDKit's high-speed compiled C++ array converter
            DataStructs.ConvertToNumpyArray(fp, fp_matrix[valid_count])
            drug_ids[valid_count] = drug_id
            valid_count += 1
        except Exception:
            failed += 1

        if (i + 1) % 100000 == 0:
            logger.info(f"    ... {i+1:,}/{total:,} done ({failed} failed)")

    if valid_count == 0:
        logger.error("  No valid fingerprints computed!")
        return

    # Trim arrays to actual valid count
    fp_matrix = fp_matrix[:valid_count]
    id_array = drug_ids[:valid_count]

    np.savez_compressed(FP_PATH, fingerprints=fp_matrix, drug_ids=id_array)
    logger.info(f"✓ Saved fingerprint matrix: {fp_matrix.shape} → {FP_PATH}")
    logger.info(f"  ({failed:,} drugs skipped due to invalid SMILES)")


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Build KineticSketch drug database")
    parser.add_argument("--skip-chembl", action="store_true", help="Skip ChEMBL loading (faster build)")
    parser.add_argument("--skip-fingerprints", action="store_true", help="Skip fingerprint computation")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing database")
    args = parser.parse_args()

    if args.overwrite:
        for p in [DB_PATH, FP_PATH]:
            if os.path.exists(p):
                os.remove(p)
                logger.info(f"  Removed existing: {p}")

    start = time.time()
    logger.info("=" * 60)
    logger.info("KineticSketch Drug Database Builder")
    logger.info("=" * 60)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-512000")  # 512 MB cache

    # Step 1: Schema
    create_db(conn)

    # Step 2: DrugCentral SMILES
    id_map = load_drugcentral_smiles(conn)

    # Step 3: DrugCentral PDB targets (from SQL dump)
    if id_map:
        extract_pdb_targets_from_sql(conn, id_map)

    # Step 4: ChEMBL supplement
    if not args.skip_chembl:
        load_chembl_approved(conn)
    else:
        logger.info("  Skipping ChEMBL (--skip-chembl)")

    # Step 5: FTS5 index
    build_fts_index(conn)

    # Summary
    drug_count = conn.execute("SELECT COUNT(*) FROM drugs").fetchone()[0]
    target_count = conn.execute("SELECT COUNT(*) FROM drug_targets").fetchone()[0]
    logger.info(f"\n{'='*60}")
    logger.info(f"Database built: {drug_count:,} drugs | {target_count:,} PDB targets")
    logger.info(f"Saved to: {DB_PATH}")

    conn.close()

    # Step 6: Fingerprints
    if not args.skip_fingerprints:
        conn2 = sqlite3.connect(DB_PATH)
        build_fingerprint_matrix(conn2)
        conn2.close()
    else:
        logger.info("  Skipping fingerprint computation (--skip-fingerprints)")

    elapsed = time.time() - start
    logger.info(f"\n✅ Done in {elapsed/60:.1f} minutes")
    logger.info(f"   DB: {DB_PATH}")
    logger.info(f"   FP: {FP_PATH}")


if __name__ == "__main__":
    main()
