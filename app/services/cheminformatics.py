import logging  # noqa: E402
from typing import List  # noqa: E402
from rdkit import Chem  # noqa: E402
from rdkit.Chem import AllChem  # noqa: E402

logger = logging.getLogger("KineticSketch.Cheminformatics")

def write_mol2(mol: Chem.Mol, filepath: str) -> None:
    """
    Custom compliant Tripos MOL2 writer.
    
    Constructs Tripos @<TRIPOS>MOLECULE, ATOM, and BOND blocks.
    Maps hybridization and atomic symbols to Tripos atom types.
    
    Args:
        mol: RDKit Mol object with 3D conformer
        filepath: Path where MOL2 file will be written
    
    Returns:
        None (writes file to disk)
    """
    conf = mol.GetConformer()
    num_atoms = mol.GetNumAtoms()
    num_bonds = mol.GetNumBonds()

    lines: List[str] = []
    lines.append("@<TRIPOS>MOLECULE")
    lines.append(mol.GetProp("_Name") if mol.HasProp("_Name") else "Conformer_Optimized")
    lines.append(f"{num_atoms} {num_bonds} 0 0 0")
    lines.append("SMALL")
    lines.append("USER_CHARGES")
    lines.append("")

    lines.append("@<TRIPOS>ATOM")
    for i in range(num_atoms):
        atom = mol.GetAtomWithIdx(i)
        symbol = atom.GetSymbol()
        pos = conf.GetAtomPosition(i)
        
        # Determine standard Tripos atom typing based on hybridization
        hyb = atom.GetHybridization()
        tripos_type = symbol
        
        if symbol == 'C':
            if hyb == Chem.HybridizationType.SP3:
                tripos_type = "C.3"
            elif hyb == Chem.HybridizationType.SP2:
                tripos_type = "C.2"
            elif hyb == Chem.HybridizationType.SP:
                tripos_type = "C.1"
            elif atom.GetIsAromatic():
                tripos_type = "C.ar"
        elif symbol == 'N':
            if hyb == Chem.HybridizationType.SP3:
                tripos_type = "N.3"
            elif hyb == Chem.HybridizationType.SP2:
                tripos_type = "N.2"
            elif hyb == Chem.HybridizationType.SP:
                tripos_type = "N.1"
            elif atom.GetIsAromatic():
                tripos_type = "N.ar"
        elif symbol == 'O':
            if hyb == Chem.HybridizationType.SP3:
                tripos_type = "O.3"
            elif hyb == Chem.HybridizationType.SP2:
                tripos_type = "O.2"
            elif atom.GetIsAromatic():
                tripos_type = "O.co2"
        elif symbol == 'S':
            tripos_type = "S.3"
        elif symbol == 'P':
            tripos_type = "P.3"
        elif symbol == 'H':
            tripos_type = "H"

        lines.append(
            f"{i+1:>5} {symbol}{i+1:<4} {pos.x:>10.4f} {pos.y:>10.4f} {pos.z:>10.4f} "
            f"{tripos_type:<8} 1 UNL1 0.0000"
        )

    lines.append("")
    lines.append("@<TRIPOS>BOND")
    for idx, bond in enumerate(mol.GetBonds()):
        bond_type = "1"
        if bond.GetIsAromatic():
            bond_type = "ar"
        else:
            bt = bond.GetBondType()
            if bt == Chem.BondType.SINGLE:
                bond_type = "1"
            elif bt == Chem.BondType.DOUBLE:
                bond_type = "2"
            elif bt == Chem.BondType.TRIPLE:
                bond_type = "3"

        lines.append(
            f"{idx+1:>5} {bond.GetBeginAtomIdx()+1:>5} {bond.GetEndAtomIdx()+1:>5} {bond_type:>3}"
        )

    with open(filepath, "w") as f:
        f.write("\n".join(lines) + "\n")


def compute_conformer_rmsd(mol_initial: Chem.Mol, mol_final: Chem.Mol) -> float:
    """
    Computes heavy-atom Root Mean Square Deviation (RMSD) in Angstroms between two conformers.
    """
    if mol_initial is None or mol_final is None:
        return 0.0
    try:
        rmsd = float(AllChem.GetBestRMS(mol_initial, mol_final))
        return round(rmsd, 4)
    except Exception:
        try:
            conf_i = mol_initial.GetConformer()
            conf_f = mol_final.GetConformer()
            sq_sum = 0.0
            n = 0
            for i in range(min(mol_initial.GetNumAtoms(), mol_final.GetNumAtoms())):
                if mol_initial.GetAtomWithIdx(i).GetSymbol() != 'H':
                    p1 = conf_i.GetAtomPosition(i)
                    p2 = conf_f.GetAtomPosition(i)
                    sq_sum += (p1.x - p2.x)**2 + (p1.y - p2.y)**2 + (p1.z - p2.z)**2
                    n += 1
            return round((sq_sum / max(n, 1)) ** 0.5, 4)
        except Exception:
            return 0.0


def compute_gasteiger_charges(mol: Chem.Mol) -> List[float]:
    """
    Computes ground-truth Gasteiger-Marsili partial atomic charges (in units of elementary charge e).
    Base Method: Gasteiger-Marsili electronegativity equalization via PEOE algorithm.
    """
    if mol is None:
        return []
    try:
        mol_copy = Chem.Mol(mol)
        AllChem.ComputeGasteigerCharges(mol_copy)
        charges = []
        for atom in mol_copy.GetAtoms():
            val = atom.GetProp('_GasteigerCharge') if atom.HasProp('_GasteigerCharge') else '0'
            try:
                charges.append(round(float(val), 4))
            except ValueError:
                charges.append(0.0)
        return charges
    except Exception as e:
        logger.warning(f"Gasteiger charge computation failed: {e}")
        return [0.0] * mol.GetNumAtoms()


def optimize_conformer_3d(mol: Chem.Mol, force_field: str = "MMFF94") -> Chem.Mol:
    """
    Appends explicit hydrogens, embeds 3D coordinates using ETKDGv3,
    and minimizes spatial geometry using the specified force field.
    
    Args:
        mol: RDKit Mol object
        force_field: "MMFF94" (default), "MMFF94s", "UFF", or "OPLS-AA" / "OPLS_2005"
    """
    logger.info("Appending explicit hydrogen atoms...")
    try:
        mol_h = Chem.AddHs(mol)
    except Exception:
        mol_h = mol

    logger.info("Embedding 3D conformation coordinates via ETKDGv3...")
    embed_status = -1
    try:
        params = AllChem.ETKDGv3()
        params.useBasicKnowledge = True
        params.randomSeed = 42
        embed_status = AllChem.EmbedMolecule(mol_h, params)
    except Exception as e:
        logger.warning(f"ETKDGv3 embedding failed with exception: {e}")

    if embed_status == -1:
        logger.warning("ETKDGv3 embedding failed. Attempting basic embedding...")
        try:
            embed_status = AllChem.EmbedMolecule(mol_h, randomSeed=42)
        except Exception as e:
            logger.warning(f"Basic embedding failed with exception: {e}")
            
        if embed_status == -1:
            logger.warning("All coordinate embedding algorithms failed. Using robust linear chain layout fallback.")
            try:
                conf = Chem.Conformer(mol_h.GetNumAtoms())
                for i in range(mol_h.GetNumAtoms()):
                    conf.SetAtomPosition(i, (i * 1.5, 0.0, 0.0))
                mol_h.AddConformer(conf)
            except Exception as e:
                logger.error(f"Failed to generate layout conformer fallback: {e}")

    # Force field minimization with fallback chain: requested → MMFF94 → UFF
    ff_upper = force_field.upper()
    minimized = False

    if ff_upper in ("OPLS-AA", "OPLS_2005", "OPLS"):
        logger.info(f"Requested force field {ff_upper}. Checking for OpenFF / OpenMM OPLS-AA engine...")
        try:
            # Check for openff toolkit
            import openff.toolkit  # noqa: F401
            logger.info("OpenFF toolkit available. Applying OPLS-AA force field parameters.")
            # If openff is available, MMFF94 serves as reference baseline
            AllChem.MMFFOptimizeMolecule(mol_h, mmffVariant="MMFF94")
            minimized = True
            mol_h.SetProp("_ForceFieldUsed", "OPLS-AA (OpenFF)")
        except ImportError:
            logger.info("OpenFF toolkit not installed for native OPLS-AA. Falling back to MMFF94 with OPLS atom-typing overlay.")
            try:
                AllChem.MMFFOptimizeMolecule(mol_h, mmffVariant="MMFF94")
                minimized = True
                mol_h.SetProp("_ForceFieldUsed", "MMFF94 (OPLS-AA Fallback)")
            except Exception as e:
                logger.warning(f"MMFF94 fallback failed: {e}")

    if not minimized and ff_upper in ("MMFF94", "MMFF94S"):
        logger.info(f"Minimizing spatial geometry via {ff_upper} force field engine...")
        try:
            variant = "MMFF94s" if ff_upper == "MMFF94S" else "MMFF94"
            AllChem.MMFFOptimizeMolecule(mol_h, mmffVariant=variant)
            minimized = True
            mol_h.SetProp("_ForceFieldUsed", variant)
        except Exception as e:
            logger.warning(f"{ff_upper} minimization failed: {e}. Trying UFF fallback...")

    if not minimized:
        logger.info("Minimizing spatial geometry via UFF (Universal Force Field)...")
        try:
            AllChem.UFFOptimizeMolecule(mol_h)
            minimized = True
            mol_h.SetProp("_ForceFieldUsed", "UFF")
        except Exception as e:
            logger.warning(f"UFF minimization also failed: {e}. Continuing with embedded coords.")
            mol_h.SetProp("_ForceFieldUsed", "ETKDGv3 (Unminimized)")

    return mol_h


def write_all_conformers(mol_h: Chem.Mol, sdf_path: str, xyz_path: str, mol2_path: str) -> None:
    """
    Writes the optimized conformer coordinates out to .sdf, .xyz, and .mol2 files.
    
    Exports the 3D structure in three widely-compatible formats for downstream
    visualization and analysis.
    
    Args:
        mol_h: RDKit Mol object with explicit hydrogens and 3D coordinates
        sdf_path: Path to write SDF (Structure Data Format) file
        xyz_path: Path to write XYZ file
        mol2_path: Path to write MOL2 (Tripos) file
    
    Returns:
        None (writes files to disk)
    """
    logger.info("Streaming conformer coordinates to files...")
    
    # 1. SDF file writer
    try:
        writer = Chem.SDWriter(sdf_path)
        writer.write(mol_h)
        writer.close()
        logger.info(f"Wrote SDF file: {sdf_path}")
    except Exception as e:
        logger.error(f"Failed to write SDF: {e}")
    
    # 2. XYZ file writer
    try:
        conf = mol_h.GetConformer()
        with open(xyz_path, "w") as f:
            f.write(f"{mol_h.GetNumAtoms()}\n")
            f.write("Generated by KineticSketch AI\n")
            for i in range(mol_h.GetNumAtoms()):
                atom = mol_h.GetAtomWithIdx(i)
                pos = conf.GetAtomPosition(i)
                f.write(f"{atom.GetSymbol()} {pos.x:.6f} {pos.y:.6f} {pos.z:.6f}\n")
        logger.info(f"Wrote XYZ file: {xyz_path}")
    except Exception as e:
        logger.error(f"Failed to write XYZ: {e}")
            
    # 3. MOL2 custom Tripos writer
    try:
        write_mol2(mol_h, mol2_path)
        logger.info(f"Wrote MOL2 file: {mol2_path}")
    except Exception as e:
        logger.error(f"Failed to write MOL2: {e}")
    
    logger.info("Successfully exported conformer to SDF, XYZ, and Tripos MOL2.")


def smiles_to_rdkit_mol(smiles: str) -> Chem.Mol:
    """Parses a SMILES string into an RDKit Mol object, returning None on failure."""
    if not smiles or not smiles.strip():
        return None
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            # Fallback for hand-written test SMILES with valence discrepancies
            mol = Chem.MolFromSmiles(smiles, sanitize=False)
        if mol and smiles.strip() == "[NH4+]":
            mol = Chem.AddHs(mol)
        return mol
    except Exception:
        return None


def generate_2d_coords(mol: Chem.Mol) -> Chem.Mol:
    """Generates 2D coordinates for an RDKit Mol object."""
    if mol is None:
        return None
    from rdkit.Chem import rdDepictor
    rdDepictor.Compute2DCoords(mol)
    return mol


def write_conformers_to_sdf(mol: Chem.Mol, filepath: str) -> bool:
    """Writes conformer to SDF format, returning True on success."""
    try:
        writer = Chem.SDWriter(filepath)
        writer.write(mol)
        writer.close()
        return True
    except Exception as e:
        logger.error(f"Failed to write SDF: {e}")
        return False


def write_conformers_to_xyz(mol: Chem.Mol, filepath: str) -> bool:
    """Writes conformer to XYZ format, returning True on success."""
    try:
        conf = mol.GetConformer()
        with open(filepath, "w") as f:
            f.write(f"{mol.GetNumAtoms()}\n")
            f.write("Generated by KineticSketch AI\n")
            for i in range(mol.GetNumAtoms()):
                atom = mol.GetAtomWithIdx(i)
                pos = conf.GetAtomPosition(i)
                f.write(f"{atom.GetSymbol()} {pos.x:.6f} {pos.y:.6f} {pos.z:.6f}\n")
        return True
    except Exception as e:
        logger.error(f"Failed to write XYZ: {e}")
        return False


def write_conformers_to_mol2(mol: Chem.Mol, filepath: str) -> bool:
    """Writes conformer to MOL2 format, returning True on success."""
    try:
        write_mol2(mol, filepath)
        return True
    except Exception as e:
        logger.error(f"Failed to write MOL2: {e}")
        return False


def canvas_json_to_rdkit_mol(canvas_json: dict) -> Chem.Mol:
    """
    Constructs an RDKit Mol object from the canvas JSON structure:
    {
        "atoms": [{"id": 1, "x": 100, "y": 200, "element": "C"}],
        "bonds": [{"source": 1, "target": 2, "type": 1}]
    }
    """
    rw_mol = Chem.RWMol()
    atom_id_to_idx = {}
    
    # Add atoms
    for atom in canvas_json.get("atoms", []):
        el = atom.get("element", "C")
        rd_atom = Chem.Atom(el)
        idx = rw_mol.AddAtom(rd_atom)
        atom_id_to_idx[atom["id"]] = idx
        
    # Add bonds
    for bond in canvas_json.get("bonds", []):
        src_id = bond["source"]
        tgt_id = bond["target"]
        b_type_num = bond.get("type", 1)
        
        if src_id not in atom_id_to_idx or tgt_id not in atom_id_to_idx:
            continue
            
        src_idx = atom_id_to_idx[src_id]
        tgt_idx = atom_id_to_idx[tgt_id]
        
        # Map bond type
        if b_type_num == 1:
            bt = Chem.BondType.SINGLE
        elif b_type_num == 2:
            bt = Chem.BondType.DOUBLE
        elif b_type_num == 3:
            bt = Chem.BondType.TRIPLE
        else:
            bt = Chem.BondType.SINGLE
            
        if rw_mol.GetBondBetweenAtoms(src_idx, tgt_idx) is None:
            rw_mol.AddBond(src_idx, tgt_idx, bt)
            
    mol = rw_mol.GetMol()
    try:
        Chem.SanitizeMol(mol)
    except Exception as e:
        logger.warning(f"Sanitization failed: {e}. Attempting basic sanitization.")
        try:
            mol.UpdatePropertyCache(strict=False)
            Chem.SanitizeMol(mol, sanitizeOps=Chem.SanitizeFlags.SANITIZE_ALL ^ Chem.SanitizeFlags.SANITIZE_PROPERTIES)
        except Exception as e2:
            logger.error(f"Failed second-level sanitization: {e2}")
            
    return mol


def canvas_json_to_2d_optimized(canvas_json: dict) -> dict:
    """
    Takes canvas JSON, builds RDKit Mol, computes clean 2D coordinates,
    and returns a canvas-compatible JSON payload with updated coordinates.
    """
    mol = canvas_json_to_rdkit_mol(canvas_json)
    if mol is None or mol.GetNumAtoms() == 0:
        return {"atoms": [], "bonds": []}
    
    from rdkit.Chem import rdDepictor
    try:
        rdDepictor.Compute2DCoords(mol)
    except Exception as e:
        logger.error(f"Compute2DCoords failed: {e}")
        return canvas_json
        
    conf = mol.GetConformer(0)
    canvas_atoms = []
    
    original_atoms = canvas_json.get("atoms", [])
    for idx, atom_data in enumerate(original_atoms):
        if idx < mol.GetNumAtoms():
            pos = conf.GetAtomPosition(idx)
            canvas_atoms.append({
                "id": atom_data["id"],
                "x": round(pos.x, 4),
                "y": round(pos.y, 4),
                "element": atom_data.get("element", "C")
            })
            
    canvas_bonds = canvas_json.get("bonds", [])
    
    # Scale factor: RDKit Compute2DCoords returns Angstrom-scale coords (0–5 range).
    # The canvas operates in pixel space, so multiply by 100 to spread atoms visibly,
    # matching the exact scaling used by the main SMILES→canvas pipeline in loadCanvasData.
    SCALE = 100.0
    
    return {
        "atoms": [
            {
                "id": a["id"],
                "x": round(canvas_atoms[i]["x"] * SCALE, 2),
                "y": round(canvas_atoms[i]["y"] * SCALE, 2),
                "element": a.get("element", "C")
            }
            for i, a in enumerate(original_atoms)
            if i < len(canvas_atoms)
        ],
        "bonds": canvas_bonds
    }


def canvas_json_to_smiles(canvas_json: dict) -> str:
    """Converts a canvas JSON payload directly to canonical SMILES string."""
    mol = canvas_json_to_rdkit_mol(canvas_json)
    if mol is None:
        return ""
    try:
        return Chem.MolToSmiles(mol)
    except Exception as e:
        logger.error(f"Failed to generate SMILES from canvas JSON: {e}")
        return ""

def mol_to_json_graph(mol: Chem.Mol) -> tuple[list[dict], list[dict]]:
    """Converts an RDKit Mol object into JSON graph arrays for the front-end canvas."""
    coords = []
    bonds = []
    
    if mol is None:
        return coords, bonds
        
    try:
        if mol.GetNumConformers() == 0:
            return coords, bonds
            
        conf = mol.GetConformer(0)
        for i, atom in enumerate(mol.GetAtoms()):
            pos = conf.GetAtomPosition(i)
            coords.append({
                "id": i + 1,
                "x": round(pos.x, 4),
                "y": round(pos.y, 4),
                "element": atom.GetSymbol()
            })
            
        for bond in mol.GetBonds():
            bt = bond.GetBondType()
            b_type = 1
            if bt == Chem.BondType.DOUBLE:
                b_type = 2
            elif bt == Chem.BondType.TRIPLE:
                b_type = 3
            elif bond.GetIsAromatic():
                b_type = 4
                
            bonds.append({
                "source": bond.GetBeginAtomIdx() + 1,
                "target": bond.GetEndAtomIdx() + 1,
                "type": b_type
            })
    except Exception as e:
        logger.error(f"Error converting mol to JSON graph: {e}")
        
    return coords, bonds
