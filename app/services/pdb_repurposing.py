import logging
import os
from typing import List, Dict, Any

logger = logging.getLogger("KineticSketch.PDBRepurposing")

# ─── Hardcoded fallback reference set (used when local DB is not built yet) ───
REFERENCE_DRUGS = [
    {
        "name": "Aspirin",
        "smiles": "CC(=O)OC1=CC=CC=C1C(=O)O",
        "targets": [
            {"pdb_id": "1EQG", "name": "Cyclooxygenase-1 (COX-1)", "function": "Inhibits thromboxane production; regulates vascular homeostasis."},
            {"pdb_id": "1CX2", "name": "Cyclooxygenase-2 (COX-2)", "function": "Mediates inflammatory response, pain signaling, and fever."}
        ]
    },
    {
        "name": "Ibuprofen",
        "smiles": "CC(C)CC1=CC=C(C=C1)C(C)C(=O)O",
        "targets": [
            {"pdb_id": "4COX", "name": "Cyclooxygenase-2 (COX-2) Complex", "function": "Non-steroidal anti-inflammatory target; reduces prostaglandin synthesis."},
            {"pdb_id": "3STN", "name": "Fatty Acid-Binding Protein 4", "function": "Involved in lipid transport and intracellular metabolic signaling."}
        ]
    },
    {
        "name": "Acetaminophen",
        "smiles": "CC(=O)NC1=CC=C(O)C=C1",
        "targets": [
            {"pdb_id": "1CX2", "name": "Prostaglandin G/H Synthase 2", "function": "Involved in synthesis of central nervous system inflammatory prostaglandins."},
            {"pdb_id": "6V9V", "name": "Transient Receptor Potential TRPA1", "function": "Ankyrin-like ion channel involved in thermal pain sensation pathways."}
        ]
    },
    {
        "name": "Imatinib (Gleevec)",
        "smiles": "CC1=C(C=C(C=C1)NC(=O)C2=CC=C(C=C2)CN3CCN(CC3)C)NC4=NC=CC(=N4)C5=CN=CC=C5",
        "targets": [
            {"pdb_id": "1OPJ", "name": "Tyrosine-Protein Kinase BCR-ABL", "function": "Oncogenic fusion protein target; essential for CML cell survival."},
            {"pdb_id": "1T46", "name": "Proto-oncogene Tyrosine Kinase KIT", "function": "Receptor tyrosine kinase governing stem cell growth and GIST cell division."}
        ]
    },
    {
        "name": "Metformin",
        "smiles": "CN(C)C(=N)N=C(N)N",
        "targets": [
            {"pdb_id": "4CFE", "name": "AMP-Activated Protein Kinase (AMPK)", "function": "Master regulator of energy homeostasis; coordinates glucose uptake."}
        ]
    },
    {
        "name": "Atorvastatin (Lipitor)",
        "smiles": "CC(C)C1=C(C(=C(N1CC(CC(CC(=O)O)O)O)C2=CC=C(C=C2)F)C3=CC=CC=C3)C(=O)NC4=CC=CC=C4",
        "targets": [
            {"pdb_id": "1HWK", "name": "HMG-CoA Reductase", "function": "Rate-limiting enzyme of the mevalonate pathway; key cardiovascular target."}
        ]
    },
    {
        "name": "Albuterol",
        "smiles": "CC(C)(C)NCC(C1=CC(CO)=C(O)C=C1)O",
        "targets": [
            {"pdb_id": "3NY8", "name": "Beta-2 Adrenergic Receptor", "function": "G-protein coupled receptor; induces bronchodilation in asthma."}
        ]
    },
    {
        "name": "Penicillin V",
        "smiles": "CC1(C(N2C(S1)C(C2=O)NC(=O)COC3=CC=CC=C3)C(=O)O)C",
        "targets": [
            {"pdb_id": "1PBP", "name": "Penicillin-Binding Protein 5", "function": "Bacterial cell-wall DD-peptidase; key target for beta-lactam antibiotics."},
            {"pdb_id": "3G29", "name": "Beta-Lactamase Class A Tem-1", "function": "Mediates penicillin resistance via beta-lactam ring cleavage."}
        ]
    },
    {
        "name": "Ethanol",
        "smiles": "CCO",
        "targets": [
            {"pdb_id": "1ADC", "name": "Alcohol Dehydrogenase 1A", "function": "Catalyzes oxidation of primary alcohols to aldehydes; primary metabolic pathway."},
            {"pdb_id": "4COF", "name": "GABA-A Receptor Ligand-Gated Channel", "function": "Mediates inhibitory neurotransmission; primary CNS pharmacological target."}
        ]
    },
    {
        "name": "Benzene",
        "smiles": "C1=CC=CC=C1",
        "targets": [
            {"pdb_id": "1ERE", "name": "Estrogen Receptor Alpha", "function": "Binds weak aromatic ligands; nuclear hormone receptor governing transcription."}
        ]
    }
]


def find_repurposing_targets(query_smiles: str) -> List[Dict[str, Any]]:
    """
    Finds drug repurposing targets for the query SMILES.

    Strategy (with graceful degradation):
    1. If local drug database is built → use DrugDatabase.fast_repurposing_search()
       (up to ~16,000 approved drugs, vectorized Tanimoto, ~50ms)
    2. If not built → fall back to 10 hardcoded REFERENCE_DRUGS
       (always available, no external dependency)
    """
    # ── Primary path: local DrugDatabase ──────────────────────────────────────
    try:
        from app.services.drug_database import fast_repurposing_search, is_available
        if is_available():
            results = fast_repurposing_search(query_smiles, top_k=10, min_similarity=0.10)
            if results:
                logger.debug(f"DrugDatabase returned {len(results)} repurposing hits")
                return results
            logger.debug("DrugDatabase returned 0 hits — falling through to hardcoded fallback")
    except Exception as e:
        logger.warning(f"DrugDatabase unavailable ({e}) — using hardcoded fallback")

    # ── Fallback: hardcoded REFERENCE_DRUGS ───────────────────────────────────
    return _fallback_search(query_smiles)


def _fallback_search(query_smiles: str) -> List[Dict[str, Any]]:
    """
    Original hardcoded 10-drug Tanimoto search.
    Used when the local DrugDatabase is not built yet.
    """
    from rdkit import Chem
    from rdkit.Chem import AllChem
    from rdkit import DataStructs

    query_mol = Chem.MolFromSmiles(query_smiles)
    if query_mol is None:
        return []

    try:
        query_fp = AllChem.GetMorganFingerprintAsBitVect(query_mol, 2, nBits=1024)
    except Exception as e:
        logger.error(f"Failed to generate fingerprint for {query_smiles}: {e}")
        return []

    results = []

    for ref in REFERENCE_DRUGS:
        ref_mol = Chem.MolFromSmiles(ref["smiles"])
        if ref_mol is None:
            continue
        try:
            ref_fp = AllChem.GetMorganFingerprintAsBitVect(ref_mol, 2, nBits=1024)
            similarity = DataStructs.TanimotoSimilarity(query_fp, ref_fp)
        except Exception as e:
            logger.error(f"Tanimoto error for {ref['name']}: {e}")
            continue

        if similarity > 0.1:
            for target in ref["targets"]:
                affinity_kcal = -(similarity * 9.5 + 2.0)
                results.append({
                    "matched_drug": ref["name"],
                    "pdb_id": target["pdb_id"],
                    "target_name": target["name"],
                    "similarity": similarity,
                    "binding_probability": f"{similarity * 100:.1f}%",
                    "affinity_estimate": f"{affinity_kcal:.2f} kcal/mol",
                    "function": target["function"],
                    "approved_by": "Reference"
                })

    results.sort(key=lambda x: x["similarity"], reverse=True)
    return results
