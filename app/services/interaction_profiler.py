import logging  # noqa: E402
import numpy as np  # noqa: E402
from typing import List, Dict, Any, Tuple  # noqa: E402
from Bio.PDB import Residue, Atom  # noqa: E402

logger = logging.getLogger("KineticSketch.InteractionProfiler")

# Protein Chemistry Definitions
PROTEIN_DONORS = {
    # Residue name -> atom names that can be H-bond donors
    "ARG": ["NE", "NH1", "NH2"],
    "ASN": ["ND2"],
    "GLN": ["NE2"],
    "HIS": ["ND1", "NE2"],
    "LYS": ["NZ"],
    "SER": ["OG"],
    "THR": ["OG1"],
    "TRP": ["NE1"],
    "TYR": ["OH"],
    # Backbone amide N is donor for all amino acids except Proline
    "BACKBONE": ["N"]
}

PROTEIN_ACCEPTORS = {
    # Residue name -> atom names that can be H-bond acceptors
    "ASP": ["OD1", "OD2"],
    "GLU": ["OE1", "OE2"],
    "ASN": ["OD1"],
    "GLN": ["OE1"],
    "HIS": ["ND1", "NE2"],
    "SER": ["OG"],
    "THR": ["OG1"],
    "TYR": ["OH"],
    # Backbone carbonyl O is acceptor for all amino acids
    "BACKBONE": ["O"]
}

PROTEIN_CATIONS = {
    "ARG": ["CZ", "NH1", "NH2", "NE"],
    "LYS": ["NZ"],
    "HIS": ["ND1", "NE2", "CG"]
}

PROTEIN_ANIONS = {
    "ASP": ["CG", "OD1", "OD2"],
    "GLU": ["CD", "OE1", "OE2"]
}

PROTEIN_AROMATIC_RINGS = {
    # Residue -> atom names in the aromatic ring
    "PHE": ["CG", "CD1", "CD2", "CE1", "CE2", "CZ"],
    "TYR": ["CG", "CD1", "CD2", "CE1", "CE2", "CZ"],
    "TRP": ["CG", "CD1", "CD2", "NE1", "CE2", "CE3", "CZ2", "CZ3", "CH2"], # 5-ring and 6-ring combined or separate
    "HIS": ["CG", "ND1", "CD2", "CE1", "NE2"]
}

def get_ring_centroid_and_normal(coords: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Computes the 3D centroid and the unit normal vector of a set of ring coordinates."""
    centroid = np.mean(coords, axis=0)
    # Fit plane to coordinates using SVD
    centered = coords - centroid
    _, _, vh = np.linalg.svd(centered)
    # The normal vector is the last row of V (the column corresponding to smallest singular value)
    normal = vh[2, :]
    normal = normal / np.linalg.norm(normal)
    return centroid, normal

def detect_interactions(ligand_atoms: List[Atom.Atom], pocket_residues: List[Residue.Residue]) -> List[Dict[str, Any]]:
    """
    Analyzes the coordinates of ligand atoms and pocket residues to identify
    non-covalent interactions: hydrogen bonds, pi-stacking, pi-cation, salt bridges,
    halogen bonds, and hydrophobic contacts.
    """
    interactions = []
    
    # 1. Build ligand info: coordinates, elements, donors, acceptors, rings
    
    # Helper to check if a ligand atom is donor/acceptor
    # For ligand, any N or O can be donor or acceptor; Halogens F, Cl, Br, I are acceptors.
    # Hydrogens are usually not present, so we treat N, O, S as potential donors/acceptors.
    
    # Detect rings in ligand
    # Since we don't have RDKit bonding from PDB Atom objects easily, we find rings geometrically:
    # Look for planar cycles of length 5 or 6 among C, N, O, S atoms.
    ligand_rings = []
    atom_coords_arr = np.array([a.get_coord() for a in ligand_atoms])
    
    # Simple cycle finder for 5 and 6 membered rings based on distance (< 1.8 Å)
    n_atoms = len(ligand_atoms)
    adj = np.zeros((n_atoms, n_atoms), dtype=bool)
    for i in range(n_atoms):
        for j in range(i+1, n_atoms):
            d = np.linalg.norm(atom_coords_arr[i] - atom_coords_arr[j])
            if d < 1.8: # Typical bond distance
                adj[i, j] = adj[j, i] = True
                
    # Find cycles of size 5 and 6
    visited_cycles = set()
    for start in range(n_atoms):
        # Find rings of size 6
        # DFS path of length 5 ending in neighbor
        stack = [(start, [start])]
        while stack:
            curr, path = stack.pop()
            if len(path) in [5, 6]:
                # Check if neighboring start
                if adj[curr, start]:
                    cycle = tuple(sorted(path))
                    if cycle not in visited_cycles:
                        visited_cycles.add(cycle)
                        ring_coords = atom_coords_arr[path]
                        # Verify planarity
                        centroid, normal = get_ring_centroid_and_normal(ring_coords)
                        dists_to_plane = np.abs(np.dot(ring_coords - centroid, normal))
                        if np.max(dists_to_plane) < 0.4: # Planar ring
                            # Map to ligand atoms
                            ring_atoms = [ligand_atoms[idx] for idx in path]
                            ligand_rings.append({
                                "atoms": ring_atoms,
                                "centroid": centroid,
                                "normal": normal,
                                "size": len(path)
                            })
            if len(path) < 6:
                for neighbor in range(n_atoms):
                    if adj[curr, neighbor] and neighbor not in path:
                        stack.append((neighbor, path + [neighbor]))

    # Now iterate over pocket residues
    for residue in pocket_residues:
        resname = residue.get_resname().strip().upper()
        res_seq = residue.get_id()[1]
        chain_id = residue.get_parent().get_id()
        
        # Extract residue atoms
        res_atoms = list(residue.get_atoms())
        res_atom_dict = {a.get_name().strip(): a for a in res_atoms}
        
        # ----------------------------------------------------
        # Rule 1 & 6: Hydrogen Bonds & Halogen Bonds
        # ----------------------------------------------------
        # Ligand N/O/S/F (and Cl/Br/I for halogen) -> Protein N/O/S/backbone
        for latom in ligand_atoms:
            l_elem = latom.element.upper().strip()
            l_coord = latom.get_coord()
            
            # Check Hydrogen Bonds
            if l_elem in ["N", "O", "S", "F"]:
                for patom in res_atoms:
                    p_name = patom.get_name().strip()
                    p_elem = patom.element.upper().strip()
                    p_coord = patom.get_coord()
                    
                    if p_elem in ["N", "O", "S"]:
                        # Calculate distance
                        dist = np.linalg.norm(l_coord - p_coord)
                        if dist <= 3.5:
                            # Add H-bond
                            interactions.append({
                                "type": "hydrogen_bond",
                                "ligand_atom": {
                                    "name": latom.get_name(),
                                    "element": l_elem,
                                    "coord": l_coord.tolist()
                                },
                                "residue": {
                                    "name": resname,
                                    "chain": chain_id,
                                    "seq": res_seq
                                },
                                "protein_atom": {
                                    "name": p_name,
                                    "element": p_elem,
                                    "coord": p_coord.tolist()
                                },
                                "distance_angstrom": float(round(dist, 2))
                            })
                            
            # Check Halogen Bonds (C-X ... O/N/S acceptor)
            # X = Cl, Br, I (and F, but typically Cl/Br/I are strong halogen bond donors)
            if l_elem in ["CL", "BR", "I"]:
                for patom in res_atoms:
                    p_name = patom.get_name().strip()
                    p_elem = patom.element.upper().strip()
                    p_coord = patom.get_coord()
                    
                    # Acceptors are typically N, O, S in protein
                    if p_elem in ["N", "O", "S"]:
                        dist = np.linalg.norm(l_coord - p_coord)
                        if dist <= 3.7:
                            # Find the carbon connected to this halogen in ligand
                            # We check distance < 2.0 Å to find the parent carbon
                            parent_carbon = None
                            for neighbor_idx in range(n_atoms):
                                if ligand_atoms[neighbor_idx].get_name() == latom.get_name():
                                    # Find neighbors in adj
                                    for adj_idx in range(n_atoms):
                                        if adj[neighbor_idx, adj_idx] and ligand_atoms[adj_idx].element.upper() == "C":
                                            parent_carbon = ligand_atoms[adj_idx]
                                            break
                            
                            # Validate angle C-X...Acceptor >= 140 deg
                            if parent_carbon is not None:
                                v_cx = l_coord - parent_carbon.get_coord()
                                v_xa = p_coord - l_coord
                                v_cx_u = v_cx / np.linalg.norm(v_cx)
                                v_xa_u = v_xa / np.linalg.norm(v_xa)
                                angle_rad = np.arccos(np.clip(np.dot(v_cx_u, v_xa_u), -1.0, 1.0))
                                angle_deg = np.degrees(angle_rad)
                                
                                if angle_deg >= 130.0: # standard cutoff is >= 140, but 130 is robust for crystal structures
                                    interactions.append({
                                        "type": "halogen_bond",
                                        "ligand_atom": {
                                            "name": latom.get_name(),
                                            "element": l_elem,
                                            "coord": l_coord.tolist()
                                        },
                                        "residue": {
                                            "name": resname,
                                            "chain": chain_id,
                                            "seq": res_seq
                                        },
                                        "protein_atom": {
                                            "name": p_name,
                                            "element": p_elem,
                                            "coord": p_coord.tolist()
                                        },
                                        "distance_angstrom": float(round(dist, 2)),
                                        "angle_deg": float(round(angle_deg, 1))
                                    })

        # ----------------------------------------------------
        # Rule 5: Salt Bridges
        # ----------------------------------------------------
        # Negatively charged ASP/GLU O atoms to Positively charged LYS/ARG/HIS N atoms
        # Check if residue is anionic or cationic
        is_p_anionic = resname in ["ASP", "GLU"]
        is_p_cationic = resname in ["ARG", "LYS", "HIS"]
        
        if is_p_anionic or is_p_cationic:
            # Check ligand atoms that could be cationic (basic nitrogen, e.g. amine, guanidine)
            # or anionic (carboxylic acid, phosphate, sulfonate oxygen)
            for latom in ligand_atoms:
                l_elem = latom.element.upper().strip()
                l_coord = latom.get_coord()
                
                # Check cationic ligand + anionic residue
                if is_p_anionic and l_elem == "N":
                    for p_atom_name in PROTEIN_ANIONS.get(resname, []):
                        if p_atom_name in res_atom_dict:
                            patom = res_atom_dict[p_atom_name]
                            dist = np.linalg.norm(l_coord - patom.get_coord())
                            if dist <= 4.2:
                                interactions.append({
                                    "type": "salt_bridge",
                                    "ligand_atom": {
                                        "name": latom.get_name(),
                                        "element": l_elem,
                                        "coord": l_coord.tolist()
                                    },
                                    "residue": {
                                        "name": resname,
                                        "chain": chain_id,
                                        "seq": res_seq
                                    },
                                    "protein_atom": {
                                        "name": patom.get_name(),
                                        "element": patom.element.upper(),
                                        "coord": patom.get_coord().tolist()
                                    },
                                    "distance_angstrom": float(round(dist, 2))
                                })
                                
                # Check anionic ligand + cationic residue
                if is_p_cationic and l_elem in ["O", "S", "P"]:
                    for p_atom_name in PROTEIN_CATIONS.get(resname, []):
                        if p_atom_name in res_atom_dict:
                            patom = res_atom_dict[p_atom_name]
                            dist = np.linalg.norm(l_coord - patom.get_coord())
                            if dist <= 4.2:
                                interactions.append({
                                    "type": "salt_bridge",
                                    "ligand_atom": {
                                        "name": latom.get_name(),
                                        "element": l_elem,
                                        "coord": l_coord.tolist()
                                    },
                                    "residue": {
                                        "name": resname,
                                        "chain": chain_id,
                                        "seq": res_seq
                                    },
                                    "protein_atom": {
                                        "name": patom.get_name(),
                                        "element": patom.element.upper(),
                                        "coord": patom.get_coord().tolist()
                                    },
                                    "distance_angstrom": float(round(dist, 2))
                                })

        # ----------------------------------------------------
        # Rule 2 & 3: Pi-Pi Stacking (Parallel & T-shaped)
        # ----------------------------------------------------
        # Aromatic residue (PHE, TYR, TRP, HIS) to Aromatic ligand ring
        if resname in PROTEIN_AROMATIC_RINGS and ligand_rings:
            # Get protein ring atoms
            ring_atom_names = PROTEIN_AROMATIC_RINGS[resname]
            p_ring_atoms = [res_atom_dict[name] for name in ring_atom_names if name in res_atom_dict]
            
            # TRP has two rings (indole), but let's treat it as a single center of all aromatic atoms
            # or separate rings if needed. Let's do single center for HIS, PHE, TYR.
            if len(p_ring_atoms) >= 5:
                p_ring_coords = np.array([a.get_coord() for a in p_ring_atoms])
                p_centroid, p_normal = get_ring_centroid_and_normal(p_ring_coords)
                
                for l_ring in ligand_rings:
                    l_centroid = l_ring["centroid"]
                    l_normal = l_ring["normal"]
                    
                    dist = np.linalg.norm(l_centroid - p_centroid)
                    
                    # 1. Parallel Stacking: dist 3.5 - 5.5 Å, angle < 30 deg
                    # 2. T-shaped Stacking: dist 4.5 - 7.0 Å, angle 60 - 90 deg
                    angle_rad = np.arccos(np.clip(np.abs(np.dot(l_normal, p_normal)), 0.0, 1.0))
                    angle_deg = np.degrees(angle_rad)
                    
                    if 3.3 <= dist <= 5.8 and angle_deg < 35.0:
                        # Parallel Stacking
                        interactions.append({
                            "type": "pi_stacking_parallel",
                            "ligand_atom": {
                                "name": l_ring["atoms"][0].get_name(), # Use first atom as handle
                                "element": "Ring",
                                "coord": l_centroid.tolist()
                            },
                            "residue": {
                                "name": resname,
                                "chain": chain_id,
                                "seq": res_seq
                            },
                            "protein_atom": {
                                "name": "Centroid",
                                "element": "Ring",
                                "coord": p_centroid.tolist()
                            },
                            "distance_angstrom": float(round(dist, 2)),
                            "angle_deg": float(round(angle_deg, 1))
                        })
                    elif 4.0 <= dist <= 7.2 and 55.0 <= angle_deg <= 90.0:
                        # T-shaped Stacking
                        interactions.append({
                            "type": "pi_stacking_t_shaped",
                            "ligand_atom": {
                                "name": l_ring["atoms"][0].get_name(),
                                "element": "Ring",
                                "coord": l_centroid.tolist()
                            },
                            "residue": {
                                "name": resname,
                                "chain": chain_id,
                                "seq": res_seq
                            },
                            "protein_atom": {
                                "name": "Centroid",
                                "element": "Ring",
                                "coord": p_centroid.tolist()
                            },
                            "distance_angstrom": float(round(dist, 2)),
                            "angle_deg": float(round(angle_deg, 1))
                        })

        # ----------------------------------------------------
        # Rule 4: Pi-Cation Interactions
        # ----------------------------------------------------
        # Ligand ring centroid to Protein cationic group, OR
        # Protein ring centroid to Ligand cationic N (e.g. protonated amine)
        # Check Protein cationic residue -> Ligand Ring
        if resname in PROTEIN_CATIONS and ligand_rings:
            for p_atom_name in PROTEIN_CATIONS[resname]:
                if p_atom_name in res_atom_dict:
                    patom = res_atom_dict[p_atom_name]
                    p_coord = patom.get_coord()
                    
                    for l_ring in ligand_rings:
                        l_centroid = l_ring["centroid"]
                        dist = np.linalg.norm(l_centroid - p_coord)
                        if dist <= 6.0:
                            interactions.append({
                                "type": "pi_cation",
                                "ligand_atom": {
                                    "name": l_ring["atoms"][0].get_name(),
                                    "element": "Ring",
                                    "coord": l_centroid.tolist()
                                },
                                "residue": {
                                    "name": resname,
                                    "chain": chain_id,
                                    "seq": res_seq
                                },
                                "protein_atom": {
                                    "name": patom.get_name(),
                                    "element": patom.element.upper(),
                                    "coord": p_coord.tolist()
                                },
                                "distance_angstrom": float(round(dist, 2))
                            })
                            
        # Check Protein Ring -> Ligand Cationic N
        if resname in PROTEIN_AROMATIC_RINGS:
            ring_atom_names = PROTEIN_AROMATIC_RINGS[resname]
            p_ring_atoms = [res_atom_dict[name] for name in ring_atom_names if name in res_atom_dict]
            if len(p_ring_atoms) >= 5:
                p_ring_coords = np.array([a.get_coord() for a in p_ring_atoms])
                p_centroid, p_normal = get_ring_centroid_and_normal(p_ring_coords)
                
                for latom in ligand_atoms:
                    l_elem = latom.element.upper().strip()
                    l_coord = latom.get_coord()
                    
                    if l_elem == "N": # Cationic nitrogen
                        dist = np.linalg.norm(p_centroid - l_coord)
                        if dist <= 6.0:
                            interactions.append({
                                "type": "pi_cation",
                                "ligand_atom": {
                                    "name": latom.get_name(),
                                    "element": l_elem,
                                    "coord": l_coord.tolist()
                                },
                                "residue": {
                                    "name": resname,
                                    "chain": chain_id,
                                    "seq": res_seq
                                },
                                "protein_atom": {
                                    "name": "Centroid",
                                    "element": "Ring",
                                    "coord": p_centroid.tolist()
                                },
                                "distance_angstrom": float(round(dist, 2))
                            })

        # ----------------------------------------------------
        # Rule 7: Hydrophobic Contacts
        # ----------------------------------------------------
        # Carbon of ligand to Carbon of Val/Leu/Ile/Phe/Trp/Met/Pro/Ala
        is_p_hydrophobic = resname in ["ALA", "VAL", "LEU", "ILE", "PHE", "TRP", "MET", "PRO"]
        if is_p_hydrophobic:
            for latom in ligand_atoms:
                if latom.element.upper().strip() == "C":
                    l_coord = latom.get_coord()
                    
                    for patom in res_atoms:
                        if patom.element.upper().strip() == "C" and patom.get_name().strip() not in ["C", "CA"]: # sidechain carbons only
                            dist = np.linalg.norm(l_coord - patom.get_coord())
                            if dist <= 4.5:
                                interactions.append({
                                    "type": "hydrophobic_contact",
                                    "ligand_atom": {
                                        "name": latom.get_name(),
                                        "element": "C",
                                        "coord": l_coord.tolist()
                                    },
                                    "residue": {
                                        "name": resname,
                                        "chain": chain_id,
                                        "seq": res_seq
                                    },
                                    "protein_atom": {
                                        "name": patom.get_name(),
                                        "element": "C",
                                        "coord": patom.get_coord().tolist()
                                    },
                                    "distance_angstrom": float(round(dist, 2))
                                })

    # Filter/Deduplicate Interactions:
    # If the exact same ligand-protein atom pair matches multiple times, keep the closest one.
    unique_interactions = []
    seen_pairs = set()
    for item in sorted(interactions, key=lambda x: x["distance_angstrom"]):
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
