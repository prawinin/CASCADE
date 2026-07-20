"""
KineticSketch — Real-Time Design Score Calculator
Computes a gamified score (0–100) based on drug-likeness metrics.
Designed to be called on every canvas update for live feedback.
"""

import logging  # noqa: E402
from typing import Dict, Any  # noqa: E402

logger = logging.getLogger("KineticSketch.DesignScore")


#  Per-criterion scoring helpers 

def _score_lipinski(mw: float, logp: float, hbd: int, hba: int) -> Dict[str, Any]:
    """Lipinski Rule-of-5 compliance (25 points max, -6.25 per violation)."""
    violations = sum([mw >= 500, logp >= 5, hbd > 5, hba > 10])
    pts = max(0.0, 25.0 - violations * 6.25)
    return {"points": round(pts, 1), "violations": violations}


def _score_veber(rotatable: int, tpsa: float) -> Dict[str, Any]:
    """Veber oral bioavailability rules (15 points max, -7.5 per violation)."""
    violations = sum([rotatable > 10, tpsa > 140])
    pts = max(0.0, 15.0 - violations * 7.5)
    return {"points": round(pts, 1), "violations": violations}


def _score_mw_sweetspot(mw: float) -> Dict[str, Any]:
    """Molecular weight sweet spot 200–500 Da (15 points max)."""
    if 200 <= mw <= 500:
        pts = 15.0
    elif mw < 200:
        pts = max(0.0, 15.0 * (mw / 200))
    else:
        pts = max(0.0, 15.0 * (1 - (mw - 500) / 500))
    return {"points": round(pts, 1), "value": round(mw, 1)}


def _score_logp_sweetspot(logp: float) -> Dict[str, Any]:
    """LogP sweet spot 1–3 (10 points max)."""
    if 1 <= logp <= 3:
        pts = 10.0
    elif logp < 1:
        pts = max(0.0, 10.0 * (1 - abs(logp - 1) / 3))
    else:
        pts = max(0.0, 10.0 * (1 - (logp - 3) / 4))
    return {"points": round(pts, 1), "value": round(logp, 2)}


def _score_synthetic_accessibility(mol) -> Dict[str, Any]:
    """Synthetic accessibility via RDKit SA_Score (15 points max)."""
    try:
        from rdkit.Chem import RDConfig
        import os
        import sys
        sa_path = os.path.join(RDConfig.RDContribDir, "SA_Score")
        if sa_path not in sys.path:
            sys.path.insert(0, sa_path)
        from sascorer import calculateScore
        sa = calculateScore(mol)  # 1 (easy) → 10 (hard)
        pts = max(0.0, 15.0 * (1 - (sa - 1) / 9))
    except Exception:
        sa = 5.0
        pts = 7.5  # neutral when scorer unavailable
    return {"points": round(pts, 1), "sa_score": round(sa, 2)}


def _score_qed(mol) -> Dict[str, Any]:
    """QED drug-likeness score (20 points max)."""
    try:
        from rdkit.Chem import QED
        qed_val = QED.qed(mol)
        pts = qed_val * 20.0
    except Exception:
        qed_val = 0.5
        pts = 10.0
    return {"points": round(pts, 1), "value": round(qed_val, 3)}


def _grade(score: float):
    """Convert numeric score to letter grade and display colour."""
    if score >= 85:
        return "A", "#10B981"
    if score >= 70:
        return "B", "#3B82F6"
    if score >= 55:
        return "C", "#F59E0B"
    if score >= 40:
        return "D", "#F97316"
    return "F", "#EF4444"


#  Public API 

def calculate_design_score(smiles: str) -> Dict[str, Any]:
    """
    Calculate a real-time design score for the given molecule.

    Scoring criteria (100 points total):
        - Lipinski compliance: 25 pts (lose 6.25 per violation)
        - Veber compliance: 15 pts (lose 7.5 per violation)
        - Molecular weight sweet spot (200–500 Da): 15 pts
        - LogP sweet spot (1–3): 10 pts
        - Synthetic accessibility score: 15 pts
        - Drug-likeness (QED): 20 pts

    Returns:
        Dict with score (0–100), breakdown, grade (A/B/C/D/F), and color
    """
    try:
        from rdkit import Chem
        from rdkit.Chem import Descriptors, rdMolDescriptors

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return {"ok": False, "score": 0, "grade": "F", "color": "#EF4444", "error": "Invalid structure"}

        mw = Descriptors.ExactMolWt(mol)
        logp = Descriptors.MolLogP(mol)
        hbd = rdMolDescriptors.CalcNumHBD(mol)
        hba = rdMolDescriptors.CalcNumHBA(mol)
        tpsa = Descriptors.TPSA(mol)
        rotatable = rdMolDescriptors.CalcNumRotatableBonds(mol)

        breakdown = {
            "lipinski":               _score_lipinski(mw, logp, hbd, hba),
            "veber":                  _score_veber(rotatable, tpsa),
            "mw_sweetspot":           _score_mw_sweetspot(mw),
            "logp_sweetspot":         _score_logp_sweetspot(logp),
            "synthetic_accessibility": _score_synthetic_accessibility(mol),
            "qed":                    _score_qed(mol),
        }

        score = round(min(100.0, max(0.0, sum(v["points"] for v in breakdown.values()))), 1)
        grade, color = _grade(score)

        return {
            "ok": True,
            "score": score,
            "grade": grade,
            "color": color,
            "breakdown": breakdown,
        }

    except Exception as e:
        logger.error("Design score calculation error: %s", e)
        return {"ok": False, "score": 0, "grade": "F", "color": "#EF4444", "error": str(e)}
