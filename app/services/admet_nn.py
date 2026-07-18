"""
KineticSketch — Neural Network ADMET Prediction Service
Uses ADMET-AI / OpenADMET neural network models when available,
falls back to RDKit descriptor-based heuristics.

Install: pip install admet-ai  (optional — graceful degradation if not installed)
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("KineticSketch.ADMET_NN")

# Try importing ADMET-AI neural network library
_admet_ai_available = False
try:
    from admet_ai import ADMETModel
    _admet_ai_available = True
    logger.info("ADMET-AI neural network library loaded successfully")
except ImportError:
    logger.info("ADMET-AI not installed — using RDKit descriptor fallback for ADMET predictions")


def predict_admet_nn(smiles: str) -> Dict[str, Any]:
    """
    Predicts ADMET properties using neural network models.
    Falls back to RDKit descriptors if ADMET-AI is not installed.
    
    Returns dict with keys:
        - absorption: dict of absorption predictions
        - distribution: dict of distribution predictions
        - metabolism: dict of metabolism predictions
        - excretion: dict of excretion predictions  
        - toxicity: dict of toxicity predictions
        - source: "admet_ai" or "rdkit_heuristic"
    """
    if _admet_ai_available:
        return _predict_with_admet_ai(smiles)
    else:
        return _predict_with_rdkit_fallback(smiles)


def _predict_with_admet_ai(smiles: str) -> Dict[str, Any]:
    """Use ADMET-AI neural network for predictions."""
    try:
        model = ADMETModel()
        predictions = model.predict(smiles=smiles)
        
        return {
            "ok": True,
            "source": "admet_ai",
            "absorption": {
                "caco2_permeability": predictions.get("Caco2_Wang", None),
                "hia": predictions.get("HIA_Hou", None),
                "bioavailability_f": predictions.get("Bioavailability_Ma", None),
                "pgp_substrate": predictions.get("Pgp_Broccatelli", None),
            },
            "distribution": {
                "bbb_penetration": predictions.get("BBB_Martins", None),
                "ppb": predictions.get("PPBR_AZ", None),
                "vdss": predictions.get("VDss_Lombardo", None),
            },
            "metabolism": {
                "cyp2d6_inhibitor": predictions.get("CYP2D6_Veith", None),
                "cyp3a4_inhibitor": predictions.get("CYP3A4_Veith", None),
                "cyp2c19_inhibitor": predictions.get("CYP2C19_Veith", None),
            },
            "excretion": {
                "half_life": predictions.get("Half_Life_Obach", None),
                "clearance_hepatocyte": predictions.get("Clearance_Hepatocyte_AZ", None),
            },
            "toxicity": {
                "herg_inhibition": predictions.get("hERG", None),
                "ames_mutagenicity": predictions.get("AMES", None),
                "ld50": predictions.get("LD50_Zhu", None),
                "dili": predictions.get("DILI", None),
            },
        }
    except Exception as e:
        logger.error(f"ADMET-AI prediction failed: {e}")
        return _predict_with_rdkit_fallback(smiles)


def _predict_with_rdkit_fallback(smiles: str) -> Dict[str, Any]:
    """RDKit descriptor-based heuristic ADMET predictions."""
    try:
        from rdkit import Chem
        from rdkit.Chem import Descriptors, rdMolDescriptors
        
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return {"ok": False, "error": "Invalid SMILES"}
        
        mw = Descriptors.ExactMolWt(mol)
        logp = Descriptors.MolLogP(mol)
        tpsa = Descriptors.TPSA(mol)
        hbd = rdMolDescriptors.CalcNumHBD(mol)
        hba = rdMolDescriptors.CalcNumHBA(mol)
        rotatable = rdMolDescriptors.CalcNumRotatableBonds(mol)
        aromatic_rings = rdMolDescriptors.CalcNumAromaticRings(mol)
        
        # Heuristic absorption estimates
        hia_score = 1.0
        if mw > 500: hia_score -= 0.3
        if logp > 5 or logp < -1: hia_score -= 0.2
        if tpsa > 140: hia_score -= 0.3
        if hbd > 5: hia_score -= 0.1
        hia_score = max(0.0, min(1.0, hia_score))
        
        # Heuristic BBB penetration
        bbb_score = 1.0
        if mw > 400: bbb_score -= 0.3
        if tpsa > 90: bbb_score -= 0.4
        if hbd > 3: bbb_score -= 0.2
        bbb_score = max(0.0, min(1.0, bbb_score))
        
        return {
            "ok": True,
            "source": "rdkit_heuristic",
            "absorption": {
                "caco2_permeability": round(-5.5 + logp * 0.3, 3) if logp > 0 else -6.5,
                "hia": round(hia_score, 3),
                "bioavailability_f": round(hia_score * 0.8, 3),
                "pgp_substrate": logp < 3 and mw < 800,
            },
            "distribution": {
                "bbb_penetration": round(bbb_score, 3),
                "ppb": round(min(99, 50 + logp * 10), 1),
                "vdss": round(0.5 + logp * 0.3, 3),
            },
            "metabolism": {
                "cyp2d6_inhibitor": aromatic_rings >= 2 and mw > 300,
                "cyp3a4_inhibitor": mw > 400 and logp > 3,
                "cyp2c19_inhibitor": aromatic_rings >= 2,
            },
            "excretion": {
                "half_life": round(2.0 + logp * 1.5, 2),
                "clearance_hepatocyte": round(max(1, 50 - logp * 8), 2),
            },
            "toxicity": {
                "herg_inhibition": logp > 3.5 and mw > 350,
                "ames_mutagenicity": aromatic_rings >= 3,
                "ld50": round(max(10, 2000 - mw * 2), 1),
                "dili": mw > 600 and logp > 4,
            },
        }
    except Exception as e:
        logger.error(f"RDKit ADMET fallback error: {e}")
        return {"ok": False, "error": str(e)}
