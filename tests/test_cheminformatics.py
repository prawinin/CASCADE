import pytest
from rdkit import Chem
from app.services.cheminformatics import (
    optimize_conformer_3d,
    compute_gasteiger_charges
)
from app.services import calculate_adme_descriptors

def test_optimize_conformer_3d():
    # Test valid SMILES MMFF94 optimization
    mol = Chem.MolFromSmiles("CCO")
    mol_opt = optimize_conformer_3d(mol, force_field="MMFF94")
    assert mol_opt is not None
    assert mol_opt.GetNumConformers() > 0
    assert mol_opt.HasProp("_ForceFieldUsed")
    assert mol_opt.GetProp("_ForceFieldUsed") == "MMFF94"

    # Test that OPLS-AA raises ValueError
    with pytest.raises(ValueError, match="OPLS-AA force field engine is currently unsupported/disabled"):
        optimize_conformer_3d(mol, force_field="OPLS-AA")

def test_calculate_adme_descriptors():
    mol = Chem.MolFromSmiles("CCO")
    desc = calculate_adme_descriptors(mol)
    assert "mw" in desc
    assert "logp" in desc
    assert "hbd" in desc
    assert "hba" in desc
    assert "tpsa" in desc
    assert desc["mw"] == pytest.approx(46.07, abs=0.1)

def test_compute_gasteiger_charges():
    mol = Chem.MolFromSmiles("CCO")
    mol_h = Chem.AddHs(mol)
    charges = compute_gasteiger_charges(mol_h)
    assert len(charges) == mol_h.GetNumAtoms()
    # Check that polar oxygen atom has negative charge
    o_idx = [a.GetIdx() for a in mol_h.GetAtoms() if a.GetSymbol() == "O"][0]
    assert charges[o_idx] < 0.0
