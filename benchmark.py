#!/usr/bin/env python3
"""
KineticSketch Pipeline Benchmark
Measures real-world latency for every module and reports the results.

Run from the project root:
    python benchmark.py
"""

import sys  # noqa: E402
import os  # noqa: E402
import time  # noqa: E402

# --- Setup paths so we can import from the app ---
ROOT = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.join(ROOT, "app")
for p in [ROOT, APP_DIR, os.path.join(APP_DIR, "services")]:
    if p not in sys.path:
        sys.path.insert(0, p)

# --- Test molecule: Aspirin (simple, always works) ---
TEST_SMILES = "CC(=O)Oc1ccccc1C(=O)O"

SEP = "-" * 58

def measure(label, fn, runs=3):
    """
    Run fn() multiple times, report min/avg/max in ms.
    First run is always a warm-up and is excluded from stats.
    """
    try:
        # Warm-up run (excluded from timing)
        fn()

        times = []
        for _ in range(runs):
            t0 = time.perf_counter()
            result = fn()
            times.append((time.perf_counter() - t0) * 1000)

        mn  = min(times)
        avg = sum(times) / len(times)
        mx  = max(times)
        print(f"  {'':<3} {label:<38}  min={mn:6.1f}ms  avg={avg:6.1f}ms  max={mx:6.1f}ms")
        return result
    except Exception as e:
        print(f"  {'':<3} {label:<38}  ERROR: {e}")
        return None


print()
print("=" * 58)
print("  KineticSketch AI — Pipeline Benchmark")
print(f"  Test molecule: Aspirin  ({TEST_SMILES})")
print("=" * 58)

#  1. SMILES Parsing 
print(f"\n{SEP}")
print("  1.  SMILES Validation & Sanitization")
print(SEP)

from rdkit import Chem  # noqa: E402
mol = measure(
    "MolFromSmiles + SanitizeMol",
    fn=lambda: Chem.MolFromSmiles(TEST_SMILES)
)

#  2. 3D Conformer Embedding 
print(f"\n{SEP}")
print("  2.  3D Coordinate Embedding")
print(SEP)

from services.cheminformatics import optimize_conformer_3d  # noqa: E402

mol_3d = measure(
    "ETKDGv3 embed + MMFF94 minimise",
    fn=lambda: optimize_conformer_3d(Chem.AddHs(Chem.MolFromSmiles(TEST_SMILES)))
)

#  3. MDRepoPredictor GNN Inference 
print(f"\n{SEP}")
print("  3.  MDRepoPredictor GNN Inference")
print(SEP)

import torch  # noqa: E402
from services.models import get_predictor, get_one_hot_nodes  # noqa: E402

predictor = get_predictor()
predictor.eval()
_device = next(predictor.parameters()).device
print(f"      Device: {_device}", flush=True)

def run_gnn():
    nodes  = get_one_hot_nodes(mol_3d).to(_device)
    conf   = mol_3d.GetConformer()
    coords = torch.tensor(
        [[conf.GetAtomPosition(i).x,
          conf.GetAtomPosition(i).y,
          conf.GetAtomPosition(i).z]
         for i in range(mol_3d.GetNumAtoms())],
        dtype=torch.float32
    ).to(_device)
    with torch.no_grad():
        return predictor(coords, nodes)

gnn_result = measure("GNN forward pass", fn=run_gnn)

if gnn_result is not None:
    rmsf_10ns = gnn_result[:, 0].mean().item()
    rmsf_1us  = gnn_result[:, 1].mean().item()
    print(f"      Output: {mol_3d.GetNumAtoms()} atoms | "
          f"mean RMSF 10ns={rmsf_10ns:.3f} Å  1µs={rmsf_1us:.3f} Å")

#  4. ADME Profiling 
print(f"\n{SEP}")
print("  4.  ADME Drug-Likeness Profiling")
print(SEP)

from services.descriptors import calculate_adme_descriptors  # noqa: E402

plain_mol = Chem.MolFromSmiles(TEST_SMILES)
adme = measure(
    "Lipinski + Veber descriptors",
    fn=lambda: calculate_adme_descriptors(plain_mol)
)
if adme and adme.get("ok"):
    print(f"      Output: MW={adme['mw']:.1f} Da  LogP={adme['logp']:.2f}  "
          f"Lipinski={'' if adme['lipinski_pass'] else ''}  "
          f"Veber={'' if adme['veber_pass'] else ''}")

#  5. Morgan Similarity Search 
print(f"\n{SEP}")
print("  5.  Morgan Similarity Search")
print(SEP)

from services.pdb_repurposing import find_repurposing_targets  # noqa: E402

repurpose = measure(
    "Tanimoto similarity search",
    fn=lambda: find_repurposing_targets(TEST_SMILES)
)
if repurpose:
    print(f"      Output: {len(repurpose)} similar drugs found")

#  6. Complete Sync Cycle 
print(f"\n{SEP}")
print("  6.  Complete Sync Cycle (End-to-End)")
print(SEP)

def full_pipeline():
    m   = Chem.MolFromSmiles(TEST_SMILES)
    m3d = optimize_conformer_3d(Chem.AddHs(Chem.MolFromSmiles(TEST_SMILES)))
    nodes  = get_one_hot_nodes(m3d).to(_device)
    conf   = m3d.GetConformer()
    coords = torch.tensor(
        [[conf.GetAtomPosition(i).x,
          conf.GetAtomPosition(i).y,
          conf.GetAtomPosition(i).z]
         for i in range(m3d.GetNumAtoms())],
        dtype=torch.float32
    ).to(_device)
    with torch.no_grad():
        predictor(coords, nodes)
    calculate_adme_descriptors(m)
    find_repurposing_targets(TEST_SMILES)

measure("Full pipeline (all modules)", fn=full_pipeline)

#  Summary 
print()
print("=" * 58)
print("  Benchmark complete.")
print("=" * 58)
print()
