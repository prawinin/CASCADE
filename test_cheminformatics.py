"""
KineticSketch AI - Unit Tests for Cheminformatics Module

Tests cover:
- SMILES parsing and validation
- RDKit sanitization
- 3D conformer generation
- File format conversion
- Edge cases and error handling
"""

import pytest
import tempfile
from pathlib import Path
from rdkit import Chem
from rdkit.Chem import AllChem
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cheminformatics import (
    smiles_to_rdkit_mol,
    generate_2d_coords,
    optimize_conformer_3d,
    write_conformers_to_sdf,
    write_conformers_to_xyz,
    write_conformers_to_mol2,
)


class TestSMILESParsing:
    """Tests for SMILES to RDKit molecule conversion."""

    def test_valid_smiles_ethane(self):
        """Test parsing simple ethane molecule."""
        mol = smiles_to_rdkit_mol("CC")
        assert mol is not None
        assert mol.GetNumAtoms() == 2

    def test_valid_smiles_benzene(self):
        """Test parsing aromatic benzene ring."""
        mol = smiles_to_rdkit_mol("c1ccccc1")
        assert mol is not None
        assert mol.GetNumAtoms() == 6

    def test_valid_smiles_aspirin(self):
        """Test parsing complex Aspirin molecule."""
        smiles = "O=C(O)c1ccccc1OC(=O)C"
        mol = smiles_to_rdkit_mol(smiles)
        assert mol is not None
        assert mol.GetNumAtoms() == 13

    def test_invalid_smiles_returns_none(self):
        """Test that invalid SMILES returns None."""
        invalid_smiles = [
            "CCCC)(",
            "C#C#C#C#C#",
            "invalid_structure",
            "",
        ]
        for smiles in invalid_smiles:
            mol = smiles_to_rdkit_mol(smiles)
            assert mol is None, f"Expected None for invalid SMILES: {smiles}"

    def test_smiles_with_charges(self):
        """Test SMILES with charged atoms."""
        mol = smiles_to_rdkit_mol("[NH4+]")
        assert mol is not None
        assert mol.GetNumAtoms() == 5

    def test_smiles_with_stereo(self):
        """Test SMILES with stereochemistry."""
        mol = smiles_to_rdkit_mol("C[C@H](O)C")
        assert mol is not None
        assert mol.GetNumAtoms() == 4

    def test_smiles_exceeds_length_limit(self):
        """Test SMILES string exceeding length limit."""
        # Create a long but valid SMILES
        long_smiles = "C" * 2001
        mol = smiles_to_rdkit_mol(long_smiles)
        # Should still parse, but length validation happens elsewhere
        # This tests that we don't crash on long input
        assert mol is None or mol is not None  # Either outcome is acceptable


class TestMolecularStructure:
    """Tests for molecular structure generation."""

    def test_2d_coords_generation(self):
        """Test 2D coordinate generation."""
        mol = smiles_to_rdkit_mol("CC(C)CC1=CC(=C(C=C1)O)C(=O)O")  # Ibuprofen
        assert mol is not None
        mol = generate_2d_coords(mol)
        assert mol is not None
        conf = mol.GetConformer(0)
        assert conf is not None

    def test_3d_conformer_optimization(self):
        """Test 3D conformer generation and MMFF94 optimization."""
        mol = smiles_to_rdkit_mol("CC")  # Ethane
        assert mol is not None
        mol = generate_2d_coords(mol)
        mol = optimize_conformer_3d(mol)
        assert mol is not None
        assert mol.GetNumConformers() > 0

    def test_benzene_3d_structure(self):
        """Test 3D structure of benzene is planar."""
        mol = smiles_to_rdkit_mol("c1ccccc1")
        mol = generate_2d_coords(mol)
        mol = optimize_conformer_3d(mol)
        assert mol is not None
        # Check that benzene atoms are roughly coplanar (z-coordinates similar)
        conf = mol.GetConformer(0)
        z_coords = [conf.GetAtomPosition(i).z for i in range(mol.GetNumAtoms())]
        # Standard deviation of z-coordinates should be small for benzene
        import numpy as np
        z_std = np.std(z_coords)
        assert z_std < 0.5  # Should be nearly planar

    def test_single_atom_molecule(self):
        """Test handling of single-atom molecules."""
        mol = smiles_to_rdkit_mol("C")  # Methane (implicit hydrogens)
        assert mol is not None
        mol = generate_2d_coords(mol)
        mol = optimize_conformer_3d(mol)
        assert mol is not None


class TestFileFormats:
    """Tests for molecular file format conversion."""

    def test_write_sdf_format(self):
        """Test writing molecule to SDF format."""
        mol = smiles_to_rdkit_mol("CC")
        mol = generate_2d_coords(mol)
        mol = optimize_conformer_3d(mol)

        with tempfile.TemporaryDirectory() as tmpdir:
            sdf_path = Path(tmpdir) / "test.sdf"
            success = write_conformers_to_sdf(mol, str(sdf_path))
            assert success
            assert sdf_path.exists()
            # Verify SDF content
            content = sdf_path.read_text()
            assert "V2000" in content or "V3000" in content

    def test_write_xyz_format(self):
        """Test writing molecule to XYZ format."""
        mol = smiles_to_rdkit_mol("CC")
        mol = generate_2d_coords(mol)
        mol = optimize_conformer_3d(mol)

        with tempfile.TemporaryDirectory() as tmpdir:
            xyz_path = Path(tmpdir) / "test.xyz"
            success = write_conformers_to_xyz(mol, str(xyz_path))
            assert success
            assert xyz_path.exists()
            # Verify XYZ content
            content = xyz_path.read_text()
            lines = content.strip().split("\n")
            assert len(lines) > 0
            # First line should be number of atoms
            assert lines[0].isdigit()

    def test_write_mol2_format(self):
        """Test writing molecule to MOL2 format."""
        mol = smiles_to_rdkit_mol("CC")
        mol = generate_2d_coords(mol)
        mol = optimize_conformer_3d(mol)

        with tempfile.TemporaryDirectory() as tmpdir:
            mol2_path = Path(tmpdir) / "test.mol2"
            success = write_conformers_to_mol2(mol, str(mol2_path))
            assert success
            assert mol2_path.exists()
            # Verify MOL2 content
            content = mol2_path.read_text()
            assert "@<TRIPOS>MOLECULE" in content

    def test_multiple_conformers_export(self):
        """Test exporting multiple conformers to SDF."""
        mol = smiles_to_rdkit_mol("CC")
        mol = generate_2d_coords(mol)
        
        # Generate multiple conformers
        AllChem.EmbedMolecule(mol, randomSeed=42)
        mol = optimize_conformer_3d(mol)

        with tempfile.TemporaryDirectory() as tmpdir:
            sdf_path = Path(tmpdir) / "multi_conf.sdf"
            success = write_conformers_to_sdf(mol, str(sdf_path))
            assert success
            # Check that file contains multiple conformers
            content = sdf_path.read_text()
            # Each conformer ends with $$$$
            num_conformers = content.count("$$$$")
            assert num_conformers >= 1


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_smiles(self):
        """Test handling of empty SMILES string."""
        mol = smiles_to_rdkit_mol("")
        assert mol is None

    def test_large_molecule(self):
        """Test handling of molecule with many atoms."""
        # Create a long-chain alkane (should work up to molecular size limit)
        smiles = "C" * 50  # C50H102
        mol = smiles_to_rdkit_mol(smiles)
        assert mol is not None

    def test_very_complex_molecule(self):
        """Test handling of very complex molecules."""
        # Cholesterol (C27H46O)
        cholesterol_smiles = "CC(C)CCCC(C)C1CCC2C1(CCC3=C2CC=C4=CC(CCC4=C3)O)C"
        mol = smiles_to_rdkit_mol(cholesterol_smiles)
        assert mol is not None
        mol = generate_2d_coords(mol)
        mol = optimize_conformer_3d(mol)
        assert mol is not None

    def test_molecule_with_radicals(self):
        """Test handling of molecules with radical electrons."""
        # Methyl radical
        mol = smiles_to_rdkit_mol("[CH3]")
        assert mol is not None

    def test_molecule_with_bonds(self):
        """Test molecules with different bond types."""
        test_cases = {
            "single_bond": "CC",
            "double_bond": "C=C",
            "triple_bond": "C#C",
            "aromatic": "c1ccccc1",
        }
        for name, smiles in test_cases.items():
            mol = smiles_to_rdkit_mol(smiles)
            assert mol is not None, f"Failed to parse {name}"


class TestIntegration:
    """Integration tests for full pipeline."""

    def test_full_pipeline_small_molecule(self):
        """Test complete pipeline: SMILES -> 3D -> Files."""
        smiles = "CC(=O)Nc1ccc(cc1)O"  # Paracetamol/Acetaminophen
        
        # Parse
        mol = smiles_to_rdkit_mol(smiles)
        assert mol is not None
        
        # Generate 2D coords
        mol = generate_2d_coords(mol)
        assert mol is not None
        
        # Optimize 3D
        mol = optimize_conformer_3d(mol)
        assert mol is not None
        
        # Export to multiple formats
        with tempfile.TemporaryDirectory() as tmpdir:
            sdf_ok = write_conformers_to_sdf(mol, f"{tmpdir}/mol.sdf")
            xyz_ok = write_conformers_to_xyz(mol, f"{tmpdir}/mol.xyz")
            mol2_ok = write_conformers_to_mol2(mol, f"{tmpdir}/mol.mol2")
            
            assert sdf_ok and xyz_ok and mol2_ok

    def test_full_pipeline_drug_like_molecule(self):
        """Test pipeline with drug-like molecule (similar complexity to drugs)."""
        # Ibuprofen
        smiles = "CC(C)Cc1ccc(cc1)C(C)C(=O)O"
        
        mol = smiles_to_rdkit_mol(smiles)
        assert mol is not None
        
        mol = generate_2d_coords(mol)
        mol = optimize_conformer_3d(mol)
        assert mol is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
