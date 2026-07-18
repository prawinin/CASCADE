"""
KineticSketch — Real-Time Design Score Calculator
Computes a gamified score (0–100) based on drug-likeness metrics.
Designed to be called on every canvas update for live feedback.
"""

import logging
from typing import Dict, Any

logger = logging.getLogger("KineticSketch.DesignScore")


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
        from rdkit.Chem import Descriptors, rdMolDescriptors, QED
        
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return {"ok": False, "score": 0, "grade": "F", "color": "#EF4444", "error": "Invalid structure"}
        
        mw = Descriptors.ExactMolWt(mol)
        logp = Descriptors.MolLogP(mol)
        hbd = rdMolDescriptors.CalcNumHBD(mol)
        hba = rdMolDescriptors.CalcNumHBA(mol)
        tpsa = Descriptors.TPSA(mol)
        rotatable = rdMolDescriptors.CalcNumRotatableBonds(mol)
        
        score = 0.0
        breakdown = {}
        
        # 1. Lipinski (25 pts)
        lipinski_violations = 0
        if mw >= 500: lipinski_violations += 1
        if logp >= 5: lipinski_violations += 1
        if hbd > 5: lipinski_violations += 1
        if hba > 10: lipinski_violations += 1
        lipinski_pts = max(0, 25 - lipinski_violations * 6.25)
        score += lipinski_pts
        breakdown["lipinski"] = {"points": round(lipinski_pts, 1), "violations": lipinski_violations}
        
        # 2. Veber (15 pts)
        veber_violations = 0
        if rotatable > 10: veber_violations += 1
        if tpsa > 140: veber_violations += 1
        veber_pts = max(0, 15 - veber_violations * 7.5)
        score += veber_pts
        breakdown["veber"] = {"points": round(veber_pts, 1), "violations": veber_violations}
        
        # 3. MW sweet spot (15 pts): peak at 200–500 Da
        if 200 <= mw <= 500:
            mw_pts = 15.0
        elif mw < 200:
            mw_pts = max(0, 15 * (mw / 200))
        else:
            mw_pts = max(0, 15 * (1 - (mw - 500) / 500))
        score += mw_pts
        breakdown["mw_sweetspot"] = {"points": round(mw_pts, 1), "value": round(mw, 1)}
        
        # 4. LogP sweet spot (10 pts): peak at 1–3
        if 1 <= logp <= 3:
            logp_pts = 10.0
        elif logp < 1:
            logp_pts = max(0, 10 * (1 - abs(logp - 1) / 3))
        else:
            logp_pts = max(0, 10 * (1 - (logp - 3) / 4))
        score += logp_pts
        breakdown["logp_sweetspot"] = {"points": round(logp_pts, 1), "value": round(logp, 2)}
        
        # 5. Synthetic accessibility (15 pts)
        try:
            from rdkit.Chem import RDConfig
            import os, sys
            sa_path = os.path.join(RDConfig.RDContribDir, 'SA_Score')
            if sa_path not in sys.path:
                sys.path.insert(0, sa_path)
            from sascorer import calculateScore
            sa = calculateScore(mol)  # 1 (easy) to 10 (hard)
            sa_pts = max(0, 15 * (1 - (sa - 1) / 9))
        except Exception:
            sa = 5.0
            sa_pts = 7.5  # neutral if scorer unavailable
        score += sa_pts
        breakdown["synthetic_accessibility"] = {"points": round(sa_pts, 1), "sa_score": round(sa, 2)}
        
        # 6. QED drug-likeness (20 pts)
        try:
            qed_val = QED.qed(mol)
            qed_pts = qed_val * 20
        except Exception:
            qed_val = 0.5
            qed_pts = 10
        score += qed_pts
        breakdown["qed"] = {"points": round(qed_pts, 1), "value": round(qed_val, 3)}
        
        # Final score and grade
        score = round(min(100, max(0, score)), 1)
        if score >= 85: grade, color = "A", "#10B981"
        elif score >= 70: grade, color = "B", "#3B82F6"
        elif score >= 55: grade, color = "C", "#F59E0B"
        elif score >= 40: grade, color = "D", "#F97316"
        else: grade, color = "F", "#EF4444"
        
        return {
            "ok": True,
            "score": score,
            "grade": grade,
            "color": color,
            "breakdown": breakdown,
        }
    
    except Exception as e:
        logger.error(f"Design score calculation error: {e}")
        return {"ok": False, "score": 0, "grade": "F", "color": "#EF4444", "error": str(e)}
