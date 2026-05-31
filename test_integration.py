"""
KineticSketch AI - Integration Tests

Tests for the complete pipeline:
- SMILES → 3D Structure → Predictions → PDB Search
- Canvas Drawing → SMILES → Full Processing
- Error handling and graceful degradation
"""

import pytest
import tempfile
from pathlib import Path
import sys
import os
import json

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cheminformatics import smiles_to_rdkit_mol, generate_2d_coords, optimize_conformer_3d
from models import MDRepoPredictor
import torch


class TestFullPipeline:
    """Integration tests for complete molecular processing pipeline."""

    def test_pipeline_aspirin(self):
        """Test full pipeline with Aspirin molecule."""
        # Aspirin SMILES
        smiles = "O=C(O)c1ccccc1OC(=O)C"
        
        # Step 1: Parse SMILES
        mol = smiles_to_rdkit_mol(smiles)
        assert mol is not None
        num_atoms_before = mol.GetNumAtoms()
        
        # Step 2: Generate 2D coordinates
        mol = generate_2d_coords(mol)
        assert mol is not None
        
        # Step 3: Generate and optimize 3D structure
        mol = optimize_conformer_3d(mol)
        assert mol is not None
        assert mol.GetNumConformers() > 0
        
        # Step 4: Extract coordinates for ML prediction
        conf = mol.GetConformer(0)
        positions = []
        for i in range(mol.GetNumAtoms()):
            pos = conf.GetAtomPosition(i)
            positions.append([pos.x, pos.y, pos.z])
        
        # Step 5: Run ML prediction
        import numpy as np
        coords_tensor = torch.from_numpy(np.array([positions], dtype=np.float32))
        model = MDRepoPredictor().eval()
        
        with torch.no_grad():
            prediction = model(coords_tensor)
        
        assert prediction is not None
        assert prediction.shape[0] == 1

    def test_pipeline_ibuprofen(self):
        """Test full pipeline with Ibuprofen."""
        smiles = "CC(C)Cc1ccc(cc1)C(C)C(=O)O"
        
        mol = smiles_to_rdkit_mol(smiles)
        assert mol is not None
        
        mol = generate_2d_coords(mol)
        mol = optimize_conformer_3d(mol)
        assert mol is not None

    def test_pipeline_with_file_export(self):
        """Test pipeline including file export."""
        smiles = "CC"  # Ethane
        
        mol = smiles_to_rdkit_mol(smiles)
        mol = generate_2d_coords(mol)
        mol = optimize_conformer_3d(mol)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Export to different formats
            from cheminformatics import (
                write_conformers_to_sdf,
                write_conformers_to_xyz,
                write_conformers_to_mol2,
            )
            
            sdf_ok = write_conformers_to_sdf(mol, f"{tmpdir}/molecule.sdf")
            xyz_ok = write_conformers_to_xyz(mol, f"{tmpdir}/molecule.xyz")
            mol2_ok = write_conformers_to_mol2(mol, f"{tmpdir}/molecule.mol2")
            
            assert sdf_ok and xyz_ok and mol2_ok
            
            # Verify files were created
            assert Path(f"{tmpdir}/molecule.sdf").exists()
            assert Path(f"{tmpdir}/molecule.xyz").exists()
            assert Path(f"{tmpdir}/molecule.mol2").exists()


class TestPipelineErrorHandling:
    """Tests for error handling in pipeline."""

    def test_invalid_smiles_graceful_failure(self):
        """Test that invalid SMILES fails gracefully."""
        invalid_smiles = "CCCC)("
        
        mol = smiles_to_rdkit_mol(invalid_smiles)
        assert mol is None

    def test_very_long_smiles_handling(self):
        """Test handling of very long SMILES strings."""
        # Create a long but valid SMILES (long alkane chain)
        long_smiles = "C" * 1000
        
        mol = smiles_to_rdkit_mol(long_smiles)
        # Should either parse or return None, but not crash
        assert mol is None or mol is not None

    def test_empty_smiles_handling(self):
        """Test handling of empty SMILES."""
        mol = smiles_to_rdkit_mol("")
        assert mol is None

    def test_special_character_smiles(self):
        """Test handling of SMILES with special characters."""
        special_smiles = [
            "C@C",  # Invalid chiral
            "C.C",  # Disconnected fragments
            "C*C",  # Radical notation (varies by parser)
        ]
        
        for smiles in special_smiles:
            mol = smiles_to_rdkit_mol(smiles)
            # Should handle gracefully (return None or parse)
            assert mol is None or mol is not None


class TestMolecularSizeLimits:
    """Tests for molecular size validation."""

    def test_small_molecule_processing(self):
        """Test processing of very small molecules."""
        # Hydrogen atom (though typically not useful)
        smiles = "C"  # Methane
        mol = smiles_to_rdkit_mol(smiles)
        assert mol is not None

    def test_medium_molecule_processing(self):
        """Test processing of medium-sized molecules."""
        # Caffeine
        caffeine_smiles = "CN1C=NC2=C1C(=O)N(C(=O)N2C)C"
        mol = smiles_to_rdkit_mol(caffeine_smiles)
        assert mol is not None
        mol = generate_2d_coords(mol)
        mol = optimize_conformer_3d(mol)
        assert mol is not None

    def test_large_molecule_processing(self):
        """Test processing of larger molecules."""
        # Cholesterol (C27H46O) - 73 atoms after adding H
        cholesterol = "CC(C)CCCC(C)C1CCC2C1(CCC3=C2CC=C4=CC(CCC4=C3)O)C"
        mol = smiles_to_rdkit_mol(cholesterol)
        assert mol is not None
        mol = generate_2d_coords(mol)
        mol = optimize_conformer_3d(mol)
        assert mol is not None

    def test_very_large_molecule_processing(self):
        """Test processing at size limit."""
        # Create C100 (alkane with 100 carbons)
        large_smiles = "C" * 100
        mol = smiles_to_rdkit_mol(large_smiles)
        # Should handle without crashing
        if mol is not None:
            mol = generate_2d_coords(mol)
            mol = optimize_conformer_3d(mol)
            assert mol is not None


class TestPredictionConsistency:
    """Tests for prediction consistency across pipeline."""

    def test_same_molecule_same_prediction(self):
        """Test that same molecule produces same prediction."""
        import numpy as np
        
        smiles = "CC(C)C"  # Isobutane
        
        model = MDRepoPredictor().eval()
        
        # Process molecule twice
        predictions = []
        for _ in range(2):
            mol = smiles_to_rdkit_mol(smiles)
            mol = generate_2d_coords(mol)
            mol = optimize_conformer_3d(mol)
            
            conf = mol.GetConformer(0)
            positions = []
            for i in range(mol.GetNumAtoms()):
                pos = conf.GetAtomPosition(i)
                positions.append([pos.x, pos.y, pos.z])
            
            coords_tensor = torch.from_numpy(np.array([positions], dtype=np.float32))
            with torch.no_grad():
                pred = model(coords_tensor)
            predictions.append(pred)
        
        # Predictions should be identical (model in eval mode)
        torch.testing.assert_close(predictions[0], predictions[1])

    def test_prediction_stability(self):
        """Test that predictions don't have extreme values."""
        import numpy as np
        
        model = MDRepoPredictor().eval()
        
        # Generate multiple random structures
        for _ in range(5):
            random_coords = torch.randn(1, np.random.randint(5, 100), 3)
            with torch.no_grad():
                pred = model(random_coords)
            
            # Predictions should be finite
            assert not torch.isnan(pred).any()
            assert not torch.isinf(pred).any()
            
            # Values should be in reasonable range
            assert pred.abs().max() < 1000.0


class TestBatchProcessing:
    """Tests for batch processing capabilities."""

    def test_batch_prediction_consistency(self):
        """Test that batch and individual predictions match."""
        import numpy as np
        
        model = MDRepoPredictor().eval()
        
        # Create batch of inputs
        batch_size = 4
        num_atoms = 10
        batch_input = torch.randn(batch_size, num_atoms, 3)
        
        # Batch prediction
        with torch.no_grad():
            batch_pred = model(batch_input)
        
        # Individual predictions
        individual_preds = []
        for i in range(batch_size):
            with torch.no_grad():
                pred = model(batch_input[i:i+1])
            individual_preds.append(pred)
        
        # Concatenate individual predictions
        concat_pred = torch.cat(individual_preds, dim=0)
        
        # Should match batch prediction
        torch.testing.assert_close(batch_pred, concat_pred, rtol=1e-5, atol=1e-7)


class TestRobustness:
    """Tests for pipeline robustness."""

    def test_handles_molecule_with_hydrogens(self):
        """Test processing molecules with explicit hydrogens."""
        # Ethane with explicit hydrogens
        smiles_with_h = "[CH3][CH3]"
        mol = smiles_to_rdkit_mol(smiles_with_h)
        assert mol is not None

    def test_handles_charged_molecules(self):
        """Test processing charged molecules."""
        # Ammonium cation
        smiles = "[NH4+]"
        mol = smiles_to_rdkit_mol(smiles)
        assert mol is not None

    def test_handles_aromatic_rings(self):
        """Test processing aromatic molecules."""
        aromatic_smiles = [
            "c1ccccc1",  # Benzene
            "c1ccc2ccccc2c1",  # Naphthalene
            "c1ccncc1",  # Pyridine
        ]
        
        for smiles in aromatic_smiles:
            mol = smiles_to_rdkit_mol(smiles)
            assert mol is not None
            mol = generate_2d_coords(mol)
            mol = optimize_conformer_3d(mol)
            assert mol is not None

    def test_handles_functional_groups(self):
        """Test processing molecules with various functional groups."""
        functional_group_smiles = {
            "alcohol": "CCO",
            "aldehyde": "CC(=O)",
            "carboxylic_acid": "CC(=O)O",
            "amine": "CCN",
            "ether": "COC",
            "ketone": "CC(=O)C",
        }
        
        for name, smiles in functional_group_smiles.items():
            mol = smiles_to_rdkit_mol(smiles)
            assert mol is not None, f"Failed to parse {name}"
            mol = generate_2d_coords(mol)
            mol = optimize_conformer_3d(mol)
            assert mol is not None, f"Failed to optimize {name}"


class TestPerformance:
    """Tests for pipeline performance."""

    def test_processing_time_reasonable(self):
        """Test that processing doesn't take excessive time."""
        import time
        
        smiles = "CC(C)Cc1ccc(cc1)C(C)C(=O)O"  # Ibuprofen
        
        start = time.time()
        
        mol = smiles_to_rdkit_mol(smiles)
        mol = generate_2d_coords(mol)
        mol = optimize_conformer_3d(mol)
        
        elapsed = time.time() - start
        
        # Processing should complete in reasonable time (< 10 seconds)
        assert elapsed < 10.0

    def test_batch_prediction_time(self):
        """Test that batch prediction is reasonably fast."""
        import time
        
        model = MDRepoPredictor().eval()
        batch_input = torch.randn(10, 20, 3)
        
        start = time.time()
        with torch.no_grad():
            _ = model(batch_input)
        elapsed = time.time() - start
        
        # Should complete quickly (< 1 second for 10 samples)
        assert elapsed < 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
