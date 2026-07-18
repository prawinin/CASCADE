import os  # noqa: E402
import urllib.request  # noqa: E402
import logging  # noqa: E402
from typing import List, Tuple  # noqa: E402
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
        urllib.request.urlretrieve(url, filepath)
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

def extract_pocket_residues(
    structure: Structure.Structure,
    ligand_resname: str,
    ligand_chain: str = None,
    ligand_seq: int = None,
    cutoff_angstrom: float = 6.0
) -> Tuple[List[Atom.Atom], List[Residue.Residue]]:
    """
    Finds the specified ligand in the structure and extracts all protein residues
    within the cutoff distance of any ligand atom.
    
    Returns:
        ligand_atoms: list of Bio.PDB.Atom objects representing the ligand
        pocket_residues: list of Bio.PDB.Residue objects representing the pocket
    """
    # 1. Locate the ligand
    ligand_residue = None
    for model in structure:
        for chain in model:
            for residue in chain:
                resname = residue.get_resname().strip()
                res_id = residue.get_id()
                
                # Check match criteria
                if resname == ligand_resname.upper():
                    if ligand_chain is not None and chain.get_id() != ligand_chain:
                        continue
                    if ligand_seq is not None and res_id[1] != ligand_seq:
                        continue
                    ligand_residue = residue
                    break
            if ligand_residue:
                break
        if ligand_residue:
            break
            
    if ligand_residue is None:
        raise ValueError(f"Ligand '{ligand_resname}' not found in structure.")
        
    ligand_atoms = list(ligand_residue.get_atoms())
    if not ligand_atoms:
        raise ValueError(f"Ligand residue '{ligand_resname}' contains no atoms.")
        
    # 2. Gather all other atoms in the structure for neighbor search
    all_atoms = []
    for model in structure:
        for chain in model:
            for residue in chain:
                # Skip the ligand residue itself and waters
                if residue == ligand_residue:
                    continue
                resname = residue.get_resname().strip()
                if resname in ["HOH", "WAT", "DOD"]:
                    continue
                # We only want protein or standard nucleic acid residues
                # Typically, standard residues have blank heteroflag
                all_atoms.extend(residue.get_atoms())
                
    if not all_atoms:
        return ligand_atoms, []
        
    # 3. neighbor search
    ns = NeighborSearch(all_atoms)
    
    pocket_residues_set = set()
    for latom in ligand_atoms:
        near_atoms = ns.search(latom.get_coord(), cutoff_angstrom, level="R") # returns residues
        for res in near_atoms:
            # Check that it's a protein residue (or at least not a ligand and not water)
            pocket_residues_set.add(res)
            
    return ligand_atoms, sorted(list(pocket_residues_set), key=lambda r: (r.get_parent().get_id(), r.get_id()[1]))
