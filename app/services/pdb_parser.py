import os  # noqa: E402
import logging  # noqa: E402
from typing import List, Tuple, Optional  # noqa: E402
from Bio.PDB import PDBParser, NeighborSearch, Structure, Residue, Atom  # noqa: E402

logger = logging.getLogger("KineticSketch.PDBParser")

PDB_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "scratch", "pdb_cache")
os.makedirs(PDB_CACHE_DIR, exist_ok=True)

def fetch_pdb_file(pdb_id: str) -> str:
    """
    Downloads a PDB file from RCSB PDB database and saves it to local scratch cache.
    Returns the absolute path to the file.
    """
    pdb_id = pdb_id.strip().upper()
    if len(pdb_id) != 4 or not pdb_id.isalnum():
        raise ValueError(f"Invalid PDB ID format: '{pdb_id}'")

    filepath = os.path.join(PDB_CACHE_DIR, f"{pdb_id}.pdb")
    if os.path.exists(filepath):
        logger.info(f"Using cached PDB file for {pdb_id}")
        return filepath

    url = f"https://files.rcsb.org/download/{pdb_id}.pdb"
    # Security: always validate the scheme is https before downloading
    if not url.startswith("https://"):
        raise ValueError(f"Refusing to download from non-HTTPS URL: {url}")
    logger.info(f"Downloading PDB structure from {url}...")
    try:
        import requests
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        with open(filepath, 'wb') as f:
            f.write(response.content)
        logger.info(f"Saved PDB file to {filepath}")
        return filepath
    except Exception as e:
        logger.error(f"Failed to fetch PDB {pdb_id}: {e}")
        if os.path.exists(filepath):
            os.remove(filepath)
        raise RuntimeError(f"Could not download PDB {pdb_id}: {e}")

def parse_pdb_structure(filepath: str) -> Structure.Structure:
    """Parses a PDB file using Bio.PDB.PDBParser."""
    parser = PDBParser(QUIET=True)
    structure_id = os.path.basename(filepath).split(".")[0]
    return parser.get_structure(structure_id, filepath)

def get_ligands_in_structure(structure: Structure.Structure) -> List[Tuple[str, str, int]]:
    """
    Scans the structure for non-water HETATM residues with > 10 atoms.
    Returns list of (residue_name, chain_id, seq_number).
    """
    ligands = []
    for model in structure:
        for chain in model:
            for residue in chain:
                res_id = residue.get_id()
                # HETATM residues have a flag in res_id[0] starting with H_ or W_
                # We want to ignore water (H_HOH, H_WAT)
                is_het = res_id[0].strip() != "" and not res_id[0].startswith("W")
                if is_het:
                    resname = residue.get_resname().strip()
                    if resname not in ["HOH", "WAT", "DOD"]:
                        atom_count = len(list(residue.get_atoms()))
                        if atom_count > 10:
                            ligands.append((resname, chain.get_id(), res_id[1]))
    return ligands

def _find_ligand_atoms(structure: Structure.Structure, ligand_resname: str, ligand_chain: str = None, ligand_seq: int = None, sdf_path: Optional[str] = None) -> Tuple[List[Atom.Atom], Optional[Residue.Residue]]:
    if ligand_resname == "SKETCH":
        import os
        from rdkit import Chem
        from Bio.PDB import PDBParser
        if not sdf_path:
            raise ValueError("sdf_path is required for SKETCH ligand parsing.")
        target_sdf = sdf_path
        if os.path.exists(target_sdf):
            mol = Chem.SDMolSupplier(target_sdf)[0]
            if mol:
                temp_pdb = os.path.join(os.path.dirname(os.path.abspath(target_sdf)), "temp_sketch.pdb")
                Chem.MolToPDBFile(mol, temp_pdb)
                temp_parser = PDBParser(QUIET=True)
                temp_struct = temp_parser.get_structure("sketch", temp_pdb)
                ligand_atoms = list(temp_struct.get_atoms())
                if os.path.exists(temp_pdb):
                    os.remove(temp_pdb)
                return ligand_atoms, None
        raise ValueError("No sketched molecule found. Please run 3D optimization first.")

    for model in structure:
        for chain in model:
            for residue in chain:
                if residue.get_resname().strip() == ligand_resname.upper():
                    if ligand_chain is not None and chain.get_id() != ligand_chain:
                        continue
                    if ligand_seq is not None and residue.get_id()[1] != ligand_seq:
                        continue
                    atoms = list(residue.get_atoms())
                    if not atoms:
                        raise ValueError(f"Ligand residue '{ligand_resname}' contains no atoms.")
                    return atoms, residue
    raise ValueError(f"Ligand '{ligand_resname}' not found in structure.")


def _get_all_other_atoms(structure: Structure.Structure, ligand_residue: Optional[Residue.Residue]) -> List[Atom.Atom]:
    all_atoms = []
    for model in structure:
        for chain in model:
            for residue in chain:
                if residue == ligand_residue:
                    continue
                if residue.get_resname().strip() in ["HOH", "WAT", "DOD"]:
                    continue
                all_atoms.extend(residue.get_atoms())
    return all_atoms


def extract_pocket_residues(
    structure: Structure.Structure,
    ligand_resname: str,
    ligand_chain: str = None,
    ligand_seq: int = None,
    cutoff_angstrom: float = 6.0,
    sdf_path: Optional[str] = None
) -> Tuple[List[Atom.Atom], List[Residue.Residue]]:
    """
    Finds the specified ligand in the structure and extracts all protein residues
    within the cutoff distance of any ligand atom.
    """
    ligand_atoms, ligand_residue = _find_ligand_atoms(structure, ligand_resname, ligand_chain, ligand_seq, sdf_path)

    all_atoms = _get_all_other_atoms(structure, ligand_residue)
    if not all_atoms:
        return ligand_atoms, []

    ns = NeighborSearch(all_atoms)
    pocket_residues_set = set()
    for latom in ligand_atoms:
        near_atoms = ns.search(latom.get_coord(), cutoff_angstrom, level="R")
        for res in near_atoms:
            pocket_residues_set.add(res)

    return ligand_atoms, sorted(list(pocket_residues_set), key=lambda r: (r.get_parent().get_id(), r.get_id()[1]))
