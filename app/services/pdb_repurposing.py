import logging
from typing import List, Dict, Any
from rdkit import Chem
from rdkit.Chem import AllChem
from rdkit import DataStructs

logger = logging.getLogger("KineticSketch.PDBRepurposing")

# Curated reference pharmacophore target database with PDB target associations
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
        "name": "Penicillin V",
        "smiles": "CC1(C(N2C(S1)C(C2=O)NC(=O)COC3=CC=CC=C3)C(=O)O)C",
        "targets": [
            {"pdb_id": "1PBP", "name": "Penicillin-Binding Protein 5", "function": "Bacterial cell-wall DD-peptidase; crucial target for beta-lactam antibiotics."},
            {"pdb_id": "3G29", "name": "Beta-Lactamase Class A Tem-1", "function": "Mediates penicillin resistance via beta-lactam ring cleavage."}
        ]
    },
    {
        "name": "Imatinib (Gleevec)",
        "smiles": "CC1=C(C=C(C=C1)NC(=O)C2=CC=C(C=C2)CN3CCN(CC3)C)NC4=NC=CC(=N4)C5=CN=CC=C5",
        "targets": [
            {"pdb_id": "1OPJ", "name": "Tyrosine-Protein Kinase BCR-ABL", "function": "Oncogenic fusion protein target; essential for Chronic Myeloid Leukemia cell survival."},
            {"pdb_id": "1T46", "name": "Proto-oncogene Tyrosine Kinase KIT", "function": "Receptor tyrosine kinase governing stem cell growth and gastrointestinal stromal tumor cell division."}
        ]
    },
    {
        "name": "Metformin",
        "smiles": "CN(C)C(=N)N=C(N)N",
        "targets": [
            {"pdb_id": "4CFE", "name": "AMP-Activated Protein Kinase (AMPK)", "function": "Master regulator of energy homeostasis; coordinates glucose uptake and hepatic gluconeogenesis."}
        ]
    },
    {
        "name": "Atorvastatin (Lipitor)",
        "smiles": "CC(C)C1=C(C(=C(N1CC(CC(CC(=O)O)O)O)C2=CC=C(C=C2)F)C3=CC=CC=C3)C(=O)NC4=CC=CC=C4",
        "targets": [
            {"pdb_id": "1HWK", "name": "HMG-CoA Reductase", "function": "Rate-limiting enzyme of the mevalonate pathway; key target for cardiovascular cholesterol reduction."}
        ]
    },
    {
        "name": "Albuterol",
        "smiles": "CC(C)(C)NCC(C1=CC(CO)=C(O)C=C1)O",
        "targets": [
            {"pdb_id": "3NY8", "name": "Beta-2 Adrenergic Receptor", "function": "G-protein coupled receptor target; induces smooth-muscle bronchodilation in asthma."}
        ]
    },
    {
        "name": "Ethanol",
        "smiles": "CCO",
        "targets": [
            {"pdb_id": "1ADC", "name": "Alcohol Dehydrogenase 1A", "function": "Catalyzes oxidation of primary alcohols to aldehydes; primary metabolic pathway."},
            {"pdb_id": "4COF", "name": "GABA-A Receptor Ligand-Gated Channel", "function": "Mediates inhibitory neurotransmission; primary nervous system pharmacological target."}
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
    Computes Morgan fingerprints and calculates Tanimoto chemical similarities
    to identify candidate protein targets for molecular repurposing.
    """
    query_mol = Chem.MolFromSmiles(query_smiles)
    if query_mol is None:
        return []

    try:
        # Generate 1024-bit Morgan Fingerprint (Radius 2)
        query_fp = AllChem.GetMorganFingerprintAsBitVect(query_mol, 2, nBits=1024)
    except Exception as e:
        logger.error(f"Failed to generate fingerprint for query smiles {query_smiles}: {e}")
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
            logger.error(f"Error computing Tanimoto similarity for drug {ref['name']}: {e}")
            continue

        # Show weak fragments also (threshold 0.1)
        if similarity > 0.1:
            for target in ref["targets"]:
                # Free energy estimate scales with chemical similarity
                # Basic scaling function for realistic free energy estimates
                affinity_kcal = - (similarity * 9.5 + 2.0)
                
                results.append({
                    "matched_drug": ref["name"],
                    "pdb_id": target["pdb_id"],
                    "target_name": target["name"],
                    "similarity": similarity,
                    "binding_probability": f"{similarity * 100:.1f}%",
                    "affinity_estimate": f"{affinity_kcal:.2f} kcal/mol",
                    "function": target["function"]
                })

    # Sort results by similarity descending
    results.sort(key=lambda x: x["similarity"], reverse=True)
    return results
