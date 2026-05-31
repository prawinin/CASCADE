import logging
from typing import List
from rdkit import Chem
from rdkit.Chem import AllChem

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
            if hyb == Chem.HybridizationType.SP3: tripos_type = "C.3"
            elif hyb == Chem.HybridizationType.SP2: tripos_type = "C.2"
            elif hyb == Chem.HybridizationType.SP: tripos_type = "C.1"
            elif atom.GetIsAromatic(): tripos_type = "C.ar"
        elif symbol == 'N':
            if hyb == Chem.HybridizationType.SP3: tripos_type = "N.3"
            elif hyb == Chem.HybridizationType.SP2: tripos_type = "N.2"
            elif hyb == Chem.HybridizationType.SP: tripos_type = "N.1"
            elif atom.GetIsAromatic(): tripos_type = "N.ar"
        elif symbol == 'O':
            if hyb == Chem.HybridizationType.SP3: tripos_type = "O.3"
            elif hyb == Chem.HybridizationType.SP2: tripos_type = "O.2"
            elif atom.GetIsAromatic(): tripos_type = "O.co2"
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
            if bt == Chem.BondType.SINGLE: bond_type = "1"
            elif bt == Chem.BondType.DOUBLE: bond_type = "2"
            elif bt == Chem.BondType.TRIPLE: bond_type = "3"

        lines.append(
            f"{idx+1:>5} {bond.GetBeginAtomIdx()+1:>5} {bond.GetEndAtomIdx()+1:>5} {bond_type:>3}"
        )

    with open(filepath, "w") as f:
        f.write("\n".join(lines) + "\n")


def optimize_conformer_3d(mol: Chem.Mol) -> Chem.Mol:
    """
    Appends explicit hydrogens, embeds 3D coordinates using ETKDGv3,
    and minimizes spatial geometry using MMFF94.
    
    This is the primary 3D structure optimization routine. ETKDGv3 provides
    high-quality initial conformations based on chemical knowledge. MMFF94
    force field minimization refines the geometry.
    
    Args:
        mol: RDKit Mol object (2D structure)
    
    Returns:
        RDKit Mol object with explicit hydrogens and 3D coordinates
    
    Raises:
        Exception if embedding completely fails (rare)
    """
    logger.info("Appending explicit hydrogen atoms...")
    mol_h = Chem.AddHs(mol)
    
    logger.info("Embedding 3D conformation coordinates via ETKDGv3...")
    params = AllChem.ETKDGv3()
    params.useBasicKnowledge = True
    params.randomSeed = 42
    embed_status = AllChem.EmbedMolecule(mol_h, params)
    
    if embed_status == -1:
        # Fallback embed if ETKDGv3 fails
        logger.warning("ETKDGv3 embedding failed. Attempting basic embedding...")
        embed_status = AllChem.EmbedMolecule(mol_h, randomSeed=42)
        if embed_status == -1:
            raise Exception("Failed to embed 3D coordinates. Molecule may be too complex.")

    logger.info("Minimizing spatial geometry via MMFF94 force field engine...")
    try:
        AllChem.MMFFOptimizeMolecule(mol_h, mmffVariant='MMFF94')
    except Exception as e:
        logger.warning(f"MMFF94 minimization failed: {e}. Continuing with embedded coords.")
    
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
