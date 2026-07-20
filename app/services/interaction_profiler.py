import logging  # noqa: E402
import numpy as np  # noqa: E402
from typing import List, Dict, Any, Tuple, TypedDict, Optional  # noqa: E402
from Bio.PDB import Residue, Atom  # noqa: E402

logger = logging.getLogger("KineticSketch.InteractionProfiler")

# TypedDicts to resolve Mypy indexing errors
class AtomDict(TypedDict):
    name: str
    element: str
    coord: List[float]

class ResidueDict(TypedDict):
    name: str
    chain: str
    seq: int

class InteractionDict(TypedDict, total=False):
    type: str
    ligand_atom: AtomDict
    residue: ResidueDict
    protein_atom: AtomDict
    distance_angstrom: float
    angle_deg: float

# Protein Chemistry Definitions
PROTEIN_DONORS = {
    "ARG": ["NE", "NH1", "NH2"], "ASN": ["ND2"], "GLN": ["NE2"],
    "HIS": ["ND1", "NE2"], "LYS": ["NZ"], "SER": ["OG"],
    "THR": ["OG1"], "TRP": ["NE1"], "TYR": ["OH"],
    "BACKBONE": ["N"]
}

PROTEIN_ACCEPTORS = {
    "ASP": ["OD1", "OD2"], "GLU": ["OE1", "OE2"], "ASN": ["OD1"],
    "GLN": ["OE1"], "HIS": ["ND1", "NE2"], "SER": ["OG"],
    "THR": ["OG1"], "TYR": ["OH"], "BACKBONE": ["O"]
}

PROTEIN_CATIONS = {
    "ARG": ["CZ", "NH1", "NH2", "NE"], "LYS": ["NZ"], "HIS": ["ND1", "NE2", "CG"]
}

PROTEIN_ANIONS = {
    "ASP": ["CG", "OD1", "OD2"], "GLU": ["CD", "OE1", "OE2"]
}

PROTEIN_AROMATIC_RINGS = {
    "PHE": ["CG", "CD1", "CD2", "CE1", "CE2", "CZ"],
    "TYR": ["CG", "CD1", "CD2", "CE1", "CE2", "CZ"],
    "TRP": ["CG", "CD1", "CD2", "NE1", "CE2", "CE3", "CZ2", "CZ3", "CH2"],
    "HIS": ["CG", "ND1", "CD2", "CE1", "NE2"]
}

def get_ring_centroid_and_normal(coords: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    centroid = np.mean(coords, axis=0)
    centered = coords - centroid
    _, _, vh = np.linalg.svd(centered)
    normal = vh[2, :]
    normal = normal / np.linalg.norm(normal)
    return centroid, normal

def _find_ligand_rings(ligand_atoms: List[Atom.Atom]) -> List[Dict[str, Any]]:
    ligand_rings = []
    atom_coords_arr = np.array([a.get_coord() for a in ligand_atoms])
    n_atoms = len(ligand_atoms)
    adj = np.zeros((n_atoms, n_atoms), dtype=bool)
    
    for i in range(n_atoms):
        for j in range(i+1, n_atoms):
            d = np.linalg.norm(atom_coords_arr[i] - atom_coords_arr[j])
            if d < 1.8:
                adj[i, j] = adj[j, i] = True
                
    visited_cycles = set()
    for start in range(n_atoms):
        stack = [(start, [start])]
        while stack:
            curr, path = stack.pop()
            if len(path) in [5, 6]:
                if adj[curr, start]:
                    cycle = tuple(sorted(path))
                    if cycle not in visited_cycles:
                        visited_cycles.add(cycle)
                        ring_coords = atom_coords_arr[path]
                        centroid, normal = get_ring_centroid_and_normal(ring_coords)
                        dists_to_plane = np.abs(np.dot(ring_coords - centroid, normal))
                        if np.max(dists_to_plane) < 0.4:
                            ring_atoms = [ligand_atoms[idx] for idx in path]
                            ligand_rings.append({
                                "atoms": ring_atoms, "centroid": centroid,
                                "normal": normal, "size": len(path)
                            })
            if len(path) < 6:
                for neighbor in range(n_atoms):
                    if adj[curr, neighbor] and neighbor not in path:
                        stack.append((neighbor, path + [neighbor]))
    return ligand_rings

def _find_h_and_halogen_bonds(ligand_atoms: List[Atom.Atom], res_atoms: List[Atom.Atom], res_info: ResidueDict) -> List[InteractionDict]:
    interactions: List[InteractionDict] = []
    
    # Pre-compute adj for halogen bonds
    n_atoms = len(ligand_atoms)
    atom_coords_arr = np.array([a.get_coord() for a in ligand_atoms])
    adj = np.zeros((n_atoms, n_atoms), dtype=bool)
    for i in range(n_atoms):
        for j in range(i+1, n_atoms):
            d = np.linalg.norm(atom_coords_arr[i] - atom_coords_arr[j])
            if d < 1.8:
                adj[i, j] = adj[j, i] = True

    for latom in ligand_atoms:
        l_elem = latom.element.upper().strip()
        l_coord = latom.get_coord()
        
        if l_elem in ["N", "O", "S", "F"]:
            for patom in res_atoms:
                p_elem = patom.element.upper().strip()
                p_coord = patom.get_coord()
                if p_elem in ["N", "O", "S"]:
                    dist = float(np.linalg.norm(l_coord - p_coord))
                    if dist <= 3.5:
                        interactions.append({
                            "type": "hydrogen_bond",
                            "ligand_atom": {"name": latom.get_name(), "element": l_elem, "coord": l_coord.tolist()},
                            "residue": res_info,
                            "protein_atom": {"name": patom.get_name(), "element": p_elem, "coord": p_coord.tolist()},
                            "distance_angstrom": round(dist, 2)
                        })
                        
        if l_elem in ["CL", "BR", "I"]:
            for patom in res_atoms:
                p_elem = patom.element.upper().strip()
                p_coord = patom.get_coord()
                if p_elem in ["N", "O", "S"]:
                    dist = float(np.linalg.norm(l_coord - p_coord))
                    if dist <= 3.7:
                        parent_carbon = None
                        for n_idx in range(n_atoms):
                            if ligand_atoms[n_idx].get_name() == latom.get_name():
                                for a_idx in range(n_atoms):
                                    if adj[n_idx, a_idx] and ligand_atoms[a_idx].element.upper() == "C":
                                        parent_carbon = ligand_atoms[a_idx]
                                        break
                        if parent_carbon is not None:
                            v_cx = l_coord - parent_carbon.get_coord()
                            v_xa = p_coord - l_coord
                            v_cx_u = v_cx / np.linalg.norm(v_cx)
                            v_xa_u = v_xa / np.linalg.norm(v_xa)
                            angle_deg = float(np.degrees(np.arccos(np.clip(np.dot(v_cx_u, v_xa_u), -1.0, 1.0))))
                            if angle_deg >= 130.0:
                                interactions.append({
                                    "type": "halogen_bond",
                                    "ligand_atom": {"name": latom.get_name(), "element": l_elem, "coord": l_coord.tolist()},
                                    "residue": res_info,
                                    "protein_atom": {"name": patom.get_name(), "element": p_elem, "coord": p_coord.tolist()},
                                    "distance_angstrom": round(dist, 2),
                                    "angle_deg": round(angle_deg, 1)
                                })
    return interactions

def _find_salt_bridges(ligand_atoms: List[Atom.Atom], res_atom_dict: Dict[str, Atom.Atom], resname: str, res_info: ResidueDict) -> List[InteractionDict]:
    interactions: List[InteractionDict] = []
    is_p_anionic = resname in ["ASP", "GLU"]
    is_p_cationic = resname in ["ARG", "LYS", "HIS"]
    if not (is_p_anionic or is_p_cationic):
        return interactions
        
    for latom in ligand_atoms:
        l_elem = latom.element.upper().strip()
        l_coord = latom.get_coord()
        
        if is_p_anionic and l_elem == "N":
            for p_atom_name in PROTEIN_ANIONS.get(resname, []):
                if p_atom_name in res_atom_dict:
                    patom = res_atom_dict[p_atom_name]
                    dist = float(np.linalg.norm(l_coord - patom.get_coord()))
                    if dist <= 4.2:
                        interactions.append({
                            "type": "salt_bridge",
                            "ligand_atom": {"name": latom.get_name(), "element": l_elem, "coord": l_coord.tolist()},
                            "residue": res_info,
                            "protein_atom": {"name": patom.get_name(), "element": patom.element.upper(), "coord": patom.get_coord().tolist()},
                            "distance_angstrom": round(dist, 2)
                        })
                        
        if is_p_cationic and l_elem in ["O", "S", "P"]:
            for p_atom_name in PROTEIN_CATIONS.get(resname, []):
                if p_atom_name in res_atom_dict:
                    patom = res_atom_dict[p_atom_name]
                    dist = float(np.linalg.norm(l_coord - patom.get_coord()))
                    if dist <= 4.2:
                        interactions.append({
                            "type": "salt_bridge",
                            "ligand_atom": {"name": latom.get_name(), "element": l_elem, "coord": l_coord.tolist()},
                            "residue": res_info,
                            "protein_atom": {"name": patom.get_name(), "element": patom.element.upper(), "coord": patom.get_coord().tolist()},
                            "distance_angstrom": round(dist, 2)
                        })
    return interactions

def _find_pi_stacking(ligand_rings: List[Dict[str, Any]], res_atom_dict: Dict[str, Atom.Atom], resname: str, res_info: ResidueDict) -> List[InteractionDict]:
    interactions: List[InteractionDict] = []
    if resname in PROTEIN_AROMATIC_RINGS and ligand_rings:
        ring_atom_names = PROTEIN_AROMATIC_RINGS[resname]
        p_ring_atoms = [res_atom_dict[name] for name in ring_atom_names if name in res_atom_dict]
        
        if len(p_ring_atoms) >= 5:
            p_ring_coords = np.array([a.get_coord() for a in p_ring_atoms])
            p_centroid, p_normal = get_ring_centroid_and_normal(p_ring_coords)
            
            for l_ring in ligand_rings:
                dist = float(np.linalg.norm(l_ring["centroid"] - p_centroid))
                angle_deg = float(np.degrees(np.arccos(np.clip(np.abs(np.dot(l_ring["normal"], p_normal)), 0.0, 1.0))))
                
                if 3.3 <= dist <= 5.8 and angle_deg < 35.0:
                    interactions.append({
                        "type": "pi_stacking_parallel",
                        "ligand_atom": {"name": l_ring["atoms"][0].get_name(), "element": "Ring", "coord": l_ring["centroid"].tolist()},
                        "residue": res_info,
                        "protein_atom": {"name": "Centroid", "element": "Ring", "coord": p_centroid.tolist()},
                        "distance_angstrom": round(dist, 2), "angle_deg": round(angle_deg, 1)
                    })
                elif 4.0 <= dist <= 7.2 and 55.0 <= angle_deg <= 90.0:
                    interactions.append({
                        "type": "pi_stacking_t_shaped",
                        "ligand_atom": {"name": l_ring["atoms"][0].get_name(), "element": "Ring", "coord": l_ring["centroid"].tolist()},
                        "residue": res_info,
                        "protein_atom": {"name": "Centroid", "element": "Ring", "coord": p_centroid.tolist()},
                        "distance_angstrom": round(dist, 2), "angle_deg": round(angle_deg, 1)
                    })
    return interactions

def _find_pi_cation(ligand_atoms: List[Atom.Atom], ligand_rings: List[Dict[str, Any]], res_atom_dict: Dict[str, Atom.Atom], resname: str, res_info: ResidueDict) -> List[InteractionDict]:
    interactions: List[InteractionDict] = []
    
    if resname in PROTEIN_CATIONS and ligand_rings:
        for p_atom_name in PROTEIN_CATIONS[resname]:
            if p_atom_name in res_atom_dict:
                patom = res_atom_dict[p_atom_name]
                p_coord = patom.get_coord()
                for l_ring in ligand_rings:
                    dist = float(np.linalg.norm(l_ring["centroid"] - p_coord))
                    if dist <= 6.0:
                        interactions.append({
                            "type": "pi_cation",
                            "ligand_atom": {"name": l_ring["atoms"][0].get_name(), "element": "Ring", "coord": l_ring["centroid"].tolist()},
                            "residue": res_info,
                            "protein_atom": {"name": patom.get_name(), "element": patom.element.upper(), "coord": p_coord.tolist()},
                            "distance_angstrom": round(dist, 2)
                        })
                        
    if resname in PROTEIN_AROMATIC_RINGS:
        ring_atom_names = PROTEIN_AROMATIC_RINGS[resname]
        p_ring_atoms = [res_atom_dict[name] for name in ring_atom_names if name in res_atom_dict]
        if len(p_ring_atoms) >= 5:
            p_ring_coords = np.array([a.get_coord() for a in p_ring_atoms])
            p_centroid, _ = get_ring_centroid_and_normal(p_ring_coords)
            for latom in ligand_atoms:
                l_elem = latom.element.upper().strip()
                if l_elem == "N":
                    dist = float(np.linalg.norm(p_centroid - latom.get_coord()))
                    if dist <= 6.0:
                        interactions.append({
                            "type": "pi_cation",
                            "ligand_atom": {"name": latom.get_name(), "element": l_elem, "coord": latom.get_coord().tolist()},
                            "residue": res_info,
                            "protein_atom": {"name": "Centroid", "element": "Ring", "coord": p_centroid.tolist()},
                            "distance_angstrom": round(dist, 2)
                        })
    return interactions

def _find_hydrophobic(ligand_atoms: List[Atom.Atom], res_atoms: List[Atom.Atom], resname: str, res_info: ResidueDict) -> List[InteractionDict]:
    interactions: List[InteractionDict] = []
    if resname in ["ALA", "VAL", "LEU", "ILE", "PHE", "TRP", "MET", "PRO"]:
        for latom in ligand_atoms:
            if latom.element.upper().strip() == "C":
                l_coord = latom.get_coord()
                for patom in res_atoms:
                    if patom.element.upper().strip() == "C" and patom.get_name().strip() not in ["C", "CA"]:
                        dist = float(np.linalg.norm(l_coord - patom.get_coord()))
                        if dist <= 4.5:
                            interactions.append({
                                "type": "hydrophobic_contact",
                                "ligand_atom": {"name": latom.get_name(), "element": "C", "coord": l_coord.tolist()},
                                "residue": res_info,
                                "protein_atom": {"name": patom.get_name(), "element": "C", "coord": patom.get_coord().tolist()},
                                "distance_angstrom": round(dist, 2)
                            })
    return interactions

def detect_interactions(ligand_atoms: List[Atom.Atom], pocket_residues: List[Residue.Residue]) -> List[InteractionDict]:
    interactions: List[InteractionDict] = []
    ligand_rings = _find_ligand_rings(ligand_atoms)
    
    for residue in pocket_residues:
        resname = residue.get_resname().strip().upper()
        res_info: ResidueDict = {
            "name": resname,
            "chain": residue.get_parent().get_id(),
            "seq": residue.get_id()[1]
        }
        res_atoms = list(residue.get_atoms())
        res_atom_dict = {a.get_name().strip(): a for a in res_atoms}
        
        interactions.extend(_find_h_and_halogen_bonds(ligand_atoms, res_atoms, res_info))
        interactions.extend(_find_salt_bridges(ligand_atoms, res_atom_dict, resname, res_info))
        interactions.extend(_find_pi_stacking(ligand_rings, res_atom_dict, resname, res_info))
        interactions.extend(_find_pi_cation(ligand_atoms, ligand_rings, res_atom_dict, resname, res_info))
        interactions.extend(_find_hydrophobic(ligand_atoms, res_atoms, resname, res_info))

    # Deduplicate
    unique_interactions = []
    seen_pairs = set()
    
    def get_sort_key(item: InteractionDict) -> float:
        return item.get("distance_angstrom", 999.0)
        
    for item in sorted(interactions, key=get_sort_key):
        pair_key = (
            item["type"],
            item["ligand_atom"]["name"],
            item["residue"]["name"],
            item["residue"]["chain"],
            item["residue"]["seq"],
            item["protein_atom"]["name"]
        )
        if pair_key not in seen_pairs:
            seen_pairs.add(pair_key)
            unique_interactions.append(item)
            
    return unique_interactions
