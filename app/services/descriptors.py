import logging  # noqa: E402
from rdkit import Chem  # noqa: E402
from rdkit.Chem import Descriptors, rdMolDescriptors  # noqa: E402

logger = logging.getLogger("KineticSketch.Descriptors")

def get_molecular_formula_html(mol: Chem.Mol) -> str:
    """Generates molecular formula with subscript HTML for presentation."""
    formula = rdMolDescriptors.CalcMolFormula(mol)
    html_formula = ""
    i = 0
    while i < len(formula):
        char = formula[i]
        if char.isdigit():
            # Gather all consecutive digits
            num = ""
            while i < len(formula) and formula[i].isdigit():
                num += formula[i]
                i += 1
            html_formula += f"<sub>{num}</sub>"
            continue
        else:
            html_formula += char
            i += 1
    return html_formula

def calculate_adme_descriptors(mol: Chem.Mol) -> dict:
    """
    Computes standard ADME descriptors and rule checks (Lipinski, Veber).
    """
    if mol is None:
        return {"ok": False, "error": "Invalid molecule"}

    try:
        # Basic properties
        mw = Descriptors.ExactMolWt(mol)
        logp = Descriptors.MolLogP(mol)
        hbd = rdMolDescriptors.CalcNumHBD(mol)
        hba = rdMolDescriptors.CalcNumHBA(mol)
        tpsa = Descriptors.TPSA(mol)
        rotatable_bonds = rdMolDescriptors.CalcNumRotatableBonds(mol)
        
        # Additional counts
        ring_count = rdMolDescriptors.CalcNumRings(mol)
        aromatic_ring_count = rdMolDescriptors.CalcNumAromaticRings(mol)
        heavy_atom_count = mol.GetNumHeavyAtoms()
        formula_html = get_molecular_formula_html(mol)

        # Lipinski Rule of 5 checks:
        # MW < 500, LogP < 5, HBD <= 5, HBA <= 10
        mw_pass = mw < 500
        logp_pass = logp < 5
        hbd_pass = hbd <= 5
        hba_pass = hba <= 10
        
        lipinski_violations = 0
        if not mw_pass:
            lipinski_violations += 1
        if not logp_pass:
            lipinski_violations += 1
        if not hbd_pass:
            lipinski_violations += 1
        if not hba_pass:
            lipinski_violations += 1
        lipinski_pass = lipinski_violations <= 1 # Can violate at most 1 rule

        # Veber Rule checks:
        # Rotatable Bonds <= 10, TPSA <= 140
        rb_pass = rotatable_bonds <= 10
        tpsa_pass = tpsa <= 140
        
        veber_violations = 0
        if not rb_pass:
            veber_violations += 1
        if not tpsa_pass:
            veber_violations += 1
        veber_pass = veber_violations == 0

        return {
            "ok": True,
            "mw": round(mw, 2),
            "mw_pass": mw_pass,
            "logp": round(logp, 2),
            "logp_pass": logp_pass,
            "hbd": hbd,
            "hbd_pass": hbd_pass,
            "hba": hba,
            "hba_pass": hba_pass,
            "tpsa": round(tpsa, 2),
            "tpsa_pass": tpsa_pass,
            "rotatable_bonds": rotatable_bonds,
            "rb_pass": rb_pass,
            "lipinski_pass": lipinski_pass,
            "lipinski_violations": lipinski_violations,
            "veber_pass": veber_pass,
            "veber_violations": veber_violations,
            "molecular_formula": formula_html,
            "ring_count": ring_count,
            "aromatic_ring_count": aromatic_ring_count,
            "heavy_atom_count": heavy_atom_count
        }
    except Exception as e:
        logger.error(f"Error calculating descriptors: {e}")
        return {"ok": False, "error": "Descriptor calculation failed"}
