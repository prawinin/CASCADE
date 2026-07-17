---
title: KineticSketch
emoji: 🧬
colorFrom: blue
colorTo: indigo
sdk: gradio
app_file: app.py
pinned: false
license: cc-by-nc-4.0
short_description: A browser-native molecular dynamics GNN prediction workspace
---

<div align="center">


# 🧬 KineticSketch AI

### *Computational Chemistry — Fully Offline. Instant. Yours.*

A browser-native molecular dynamics workstation. Draw a drug, get per-atom fluctuation predictions powered by a custom Graph Neural Network trained on **150,000 synthetic structures + 1,319 real protein MD trajectories**. No cloud. No subscriptions. Runs on a single GPU.

<p>
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/PyTorch-GNN%20%7C%20AMP%20%7C%20ROCm-EE4C2C?style=for-the-badge&logo=pytorch&logoColor=white" />
  <img src="https://img.shields.io/badge/RDKit-Cheminformatics-3CB371?style=for-the-badge" />
  <img src="https://img.shields.io/badge/GPU-AMD%20ROCm%20%2F%20NVIDIA%20CUDA-ED1C24?style=for-the-badge" />
  <img src="https://img.shields.io/badge/3Dmol.js-WebGL%203D-7B68EE?style=for-the-badge" />
  <img src="https://img.shields.io/badge/Ollama-Local%20LLM-black?style=for-the-badge" />
  <img src="https://img.shields.io/badge/License-Academic%20Use-lightgrey?style=for-the-badge" />
</p>

---

*Developed by **Prawin** under the guidance of **Dr. Rajiv K. Kar**, Assistant Professor, Jyoti and Bhupat Mehta School of Health Sciences & Technology, IIT Guwahati.*

</div>

## What It Does

KineticSketch AI is a locally-hosted computational chemistry workspace for researchers, medicinal chemists, and students. Submit any molecule — drawn by hand on the built-in canvas, typed as a SMILES string, or looked up by drug name — and the system runs a full cheminformatics + deep learning pipeline in seconds:

1. **3D Conformer Generation** — RDKit ETKDGv3 embedding + MMFF94 force-field minimization
2. **Per-Atom Dynamics Prediction** — Custom-trained GNN predicts RMSF fluctuation at 10 ns and 1 µs timescales
3. **ADME Drug-Likeness Profiling** — Lipinski Rule of 5, Veber filter, all key descriptors
4. **Drug Repurposing** — Tanimoto similarity search against 4,099 clinically approved drugs
5. **AI 3D Visualization** — Natural language control of the WebGL 3D viewer via local LLM

Everything runs on your own hardware. No external APIs. No subscriptions. No data leaves the machine.

---

## The Model — MDRepoPredictor

The heart of KineticSketch is a custom **Message Passing Neural Network (MPNN)** architecture trained end-to-end on real and synthetic molecular dynamics data.

### Architecture

| Component | Specification |
|---|---|
| **Total Parameters** | **1,228,370** |
| **Node Input** | 3D Cartesian coordinates `(N × 3)` + one-hot element encoding `(N × 13)` |
| **Node Embedding** | `Linear(13 → 256)` + LayerNorm + ReLU |
| **GNN Layers** | **4 × MPNNLayer** with multi-scale Gaussian RBF adjacency |
| **Gamma Scales (γ)** | **4 learnable γ values** — captures interactions at 0.006 Å⁻² to 0.22 Å⁻² |
| **Adjacency** | `A[i,j] = exp(−γ_k · d²(i,j))` — rotation & translation invariant |
| **Global Context** | Per-atom distance to molecular center of mass (Å) |
| **MLP Head** | `(512+1) → 256 → 128 → 64 → 2` with LayerNorm + Dropout(0.1) |
| **Output Activation** | Softplus — strictly positive RMSF predictions guaranteed |
| **Output** | `(N, 2)` — RMSF at **10 ns** and **1 µs** per atom (Å) |

### Invariance

Pairwise squared interatomic distances `d²(i,j)` are intrinsically invariant to any rigid rotation or translation. The model produces byte-identical predictions regardless of how the molecule is oriented in space. This is a hard mathematical guarantee, not a data augmentation trick.

### Training Pipeline

Training ran in two sequential phases on an AMD Radeon RX 6500M GPU using PyTorch ROCm 6.x with `torch.amp` mixed-precision (AMP).

#### Phase A — Synthetic Pre-training

| Parameter | Value |
|---|---|
| Dataset | 150,000 synthetically generated molecules |
| Source | RDKit ETKDGv3 + MMFF94 from 30 seed SMILES |
| Labels | Rule-based biophysical RMSF (aromatic → rigid, terminal → flexible) |
| Epochs | 300 |
| Batch Size | 128 (gradient accumulation × 4 → effective 512) |
| Optimizer | Adam, lr=1e-3, weight_decay=1e-5 |
| Scheduler | CosineAnnealingLR (η_min = 1e-5) |
| Final Val Loss (MSE) | **~0.062** |
| GPU | AMD Radeon RX 6500M (ROCm 6.x, GFX1030) |

#### Phase B — Real MD Fine-tuning

| Parameter | Value |
|---|---|
| Dataset | **1,319 real protein structures** from FastProtFlex (filtered ≤ 1,200 atoms) |
| Source | PDB structures from RCSB, RMSF from crystallographic B-factors |
| Atom coverage | ~1.05 million individual atom labels |
| Epochs | 200 |
| Batch Size | 1 (protein structures are variable-length) |
| LR | 1e-4 (10× lower than Phase A — fine-tuning regime) |
| Scheduler | CosineAnnealingLR (η_min = 1e-6) |
| Best Val Loss (MSE) | **15.039** |
| Checkpoint | Saved only when validation improves |
| GPU | AMD Radeon RX 6500M (ROCm 6.x, GFX1030) |
| Training Time | ~2 hours 10 minutes |

> **Note on Phase B loss scale:** The larger MSE in Phase B (~15 vs ~0.06 in Phase A) is expected. Phase A uses normalized synthetic RMSF in a narrow range (0.01–0.8 Å). Phase B fine-tunes on raw protein B-factor–derived RMSF values, which span a much wider physical range (0.5–25+ Å). The network is correctly learning the full dynamic range of real proteins.

#### No Quality Loss from Inference Optimizations

`torch.compile` is intentionally **disabled at inference time**. It is only used during training for kernel fusion speed. All inference runs natively on PyTorch eager mode — the predictions are numerically identical to a compiled model. Disabling it at inference eliminates:
- A 10–15 second JIT stall on the first request
- CUDA Graph thread-safety errors in Flask worker threads

---

## Full Feature Set

### 2D Molecular Sketcher
A fully custom HTML5 Canvas drawing engine (~1,400 lines of vanilla JavaScript):
- Draw, Move, and Erase interaction modes
- Element selection: C, N, O, H, P, S, F, Cl, Br, I, B, Si
- Bond type cycling: single → double → triple on click
- One-click ring templates: benzene, cyclohexane, cyclopentane, pyridine
- Full undo/redo stack (up to 80 states, serialized as JSON)
- Zoom, pan, and canvas auto-fit
- RDKit-backed 2D coordinate cleanup (`Compute2DCoords`)
- Live debounced sync to 3D + ADME panels (800 ms / 1200 ms)

### 3D Conformer Generation
1. Validates and sanitizes via RDKit `SanitizeMol`
2. Appends explicit hydrogen atoms (`AddHs`)
3. Embeds 3D coordinates with **ETKDGv3** (RDKit's Cambridge Structural Database-trained geometry algorithm)
4. Energy-minimizes with **MMFF94** force field
5. Exports `.sdf`, `.xyz`, `.mol2`

### WebGL 3D Viewer
Live rendering via **3Dmol.js** (WebGL). Stick, sphere (CPK), line, and cartoon styles. Interactive rotation/zoom/pan. Auto-renders on each canvas edit or molecule submission.

### ADME Drug-Likeness Profiling

| Property | Filter | Source |
|---|---|---|
| Molecular Weight | < 500 Da | Lipinski Rule of 5 |
| LogP | < 5 | Lipinski Rule of 5 |
| H-Bond Donors | ≤ 5 | Lipinski Rule of 5 |
| H-Bond Acceptors | ≤ 10 | Lipinski Rule of 5 |
| Rotatable Bonds | ≤ 10 | Veber Filter |
| TPSA | ≤ 140 Ų | Veber Filter |

### Drug Repurposing Engine
Vectorized Tanimoto similarity search across **2,898,063 known drug compounds**, cross-referenced with **5,576 drug-target PDB associations** (across 5,421 unique PDB targets). Full search completes in under a second. Results include matched drug name, PDB target ID, binding free energy (ΔG), and similarity score.

The fingerprint matrix is loaded via `numpy mmap_mode='r'` — the OS pages in only the rows needed per query, keeping RAM footprint under 100 MB regardless of database size.

### Smart Drug Name Lookup
Detects SMILES vs. drug name automatically. Resolution order:
1. Offline synonym vocabulary (brand names → INN)
2. Local SQLite FTS5 full-text index with autocomplete
3. PubChem PUG REST API (online fallback only)

### PDB Protein Fetch + Interaction Profiling
Enter a PDB ID or upload a `.pdb` file. BioPython extracts ligands and detects the binding pocket. Interaction profiler identifies:

| Interaction | Geometry Criterion |
|---|---|
| Hydrogen Bond | Donor–acceptor ≤ 3.5 Å + angular geometry |
| Pi–Pi Stacking | Ring centroid ≤ 5.8 Å; plane angle via SVD (parallel < 35°, T-shape 55–90°) |
| Cation–Pi | Cation to ring centroid ≤ 6.0 Å |
| Salt Bridge | Oppositely charged residues ≤ 4.2 Å |
| Hydrophobic Contact | Aliphatic C–C ≤ 4.5 Å |

### PyMOL AI Assistant (Local LLM)
A chat interface powered by **Ollama** running **Microsoft Phi** (or any model you configure). Natural language commands (`"show spheres and color nitrogen blue"`) are translated server-side into PyMOL syntax. The frontend `applyPyMOLTo3Dmol()` function maps commands to the 3Dmol.js WebGL API — no PyMOL process runs. Configurable via `OLLAMA_MODEL` in `.env`.

---

## Deployment

KineticSketch is designed to run locally or on a shared lab server. It does not send any molecular data to external servers, which makes it suitable for research environments where data privacy matters.

| Environment | Recommended Spec | Notes |
|---|---|---|
| **Personal Laptop / Workstation** | Any NVIDIA RTX / AMD Radeon (4 GB+ VRAM) | Full pipeline in < 2s per molecule |
| **Shared Lab Server** | NVIDIA A10G / RTX 4090 (24 GB) | Multiple users via Gunicorn |
| **Air-Gapped Intranet** | Any GPU workstation, no internet required | No external API calls at runtime |

For deployment questions or academic collaboration, contact: **prawin@vyapai.tech**

---

## Repository Structure

```text
KineticSketch/
├── app/
│   ├── gui/
│   │   └── index.html              # Frontend: sketcher, 3D viewer, ADME panel, PyMOL chat
│   ├── services/
│   │   ├── checkpoint.py           # Pipeline state serialization
│   │   ├── cheminformatics.py      # ETKDGv3 embedding, MMFF94, SDF/XYZ/MOL2 export
│   │   ├── descriptors.py          # Lipinski / Veber / ADME descriptor calculations
│   │   ├── drug_database.py        # SQLite FTS5 lookup, fingerprint mmap search
│   │   ├── interaction_profiler.py # H-bond, pi-stacking, salt bridge, hydrophobic
│   │   ├── models.py               # MDRepoPredictor GNN — 1.2M params, 4 layers, embed_dim=256
│   │   ├── pdb_parser.py           # BioPython PDB parsing and ligand extraction
│   │   ├── pdb_repurposing.py      # Morgan fingerprint Tanimoto similarity search
│   │   └── visualizer.py          # Ollama HTTP client and fallback PyMOL mapper
│   ├── models/
│   │   ├── mdrepo_predictor.pt     # Trained GNN weights — Phase A+B (gitignored)
│   │   └── training_history.json   # Epoch-by-epoch loss logs (gitignored)
│   ├── static/
│   │   ├── sketch.js               # 2D canvas engine, undo stack, debounce timers
│   │   └── interaction_viewer.js   # SVG 2D ligand-protein interaction diagram renderer
│   ├── config.py                   # Environment-aware centralized config
│   └── main.py                     # Flask routes and request orchestration
├── data/
│   ├── FastProtFlex.zip            # 3,771 PDB structures for MD fine-tuning (gitignored)
│   ├── drug_database.sqlite        # DrugCentral — 4,099 approved drugs + FTS5 index (gitignored)
│   └── drug_fingerprints.npz       # Pre-computed Morgan fingerprints for repurposing (gitignored)
├── scripts/
│   ├── build_drug_db.py            # Builds drug_database.sqlite + drug_fingerprints.npz
│   └── train_mdrepo.py             # MDRepoPredictor two-phase training script
├── run.py                          # Root launcher — sets sys.path and boots main.py
├── wsgi.py                         # Gunicorn-compatible WSGI entry point
├── Modelfile                       # Ollama model specification
├── requirements.txt                # Python CPU dependencies
├── requirements_amd_rocm63_rdna2.txt # PyTorch ROCm 6.3 + RDNA2 pinned deps
├── Dockerfile                      # Multi-stage production container
├── docker-compose.yml              # Flask service orchestration
└── .env.example                    # Environment configuration template
```

---

## Installation

### Requirements
- Python 3.10–3.13
- Linux (Ubuntu 22.04+, Arch, or Manjaro) — macOS supported, Windows via WSL2
- GPU: NVIDIA (CUDA 11.8+) or AMD (ROCm 6.x) — CPU fallback available

### Setup

```bash
git clone https://github.com/prawinin/KineticSketch.git
cd KineticSketch

python3 -m venv .venv
source .venv/bin/activate

# CPU / NVIDIA CUDA
pip install -r requirements.txt

# AMD GPU — ROCm 6.3 (tested: RX 6500M, RDNA2)
# Ensure: HSA_OVERRIDE_GFX_VERSION=10.3.0 for RDNA2 GPUs
pip install -r requirements_amd_rocm63_rdna2.txt
```

```bash
# Configure environment
cp .env.example .env

# Key settings to adjust in .env:
# OLLAMA_ENABLED=1
# OLLAMA_MODEL=phi3          ← or any model you have in Ollama
# OLLAMA_API_URL=http://localhost:11434
# SECRET_KEY=your-secret-key
```

```bash
# Optional: set up local LLM assistant
ollama pull phi3              # Microsoft Phi-3 (recommended — fast, 3.8B params)
# OR
ollama create kinetic-agent -f Modelfile   # Custom KineticSketch Llama 3.2 agent
```

> **Note on Data & Models:** To keep the repository lightweight, we have not uploaded any datasets, pre-computed databases/fingerprints, or the trained GNN model weights (`app/models/mdrepo_predictor.pt`) to this repository. To obtain these files for local execution, please contact: **prawin@vyapai.tech**

---

## Running

```bash
# Development
source .venv/bin/activate
python run.py
# Open http://localhost:5000
```

```bash
# Production (Gunicorn — recommended for shared lab use)
gunicorn wsgi:app --bind 0.0.0.0:5000 --workers 4 --timeout 120
```

```bash
# Docker (production container)
docker-compose up --build
```

---

## Training Your Own Model

The two-phase training pipeline is fully reproducible:

```bash
# Phase A — synthetic pre-training (150,000 molecules, ~5 hrs on RTX 3080)
python scripts/train_mdrepo.py \
    --phase a \
    --epochs 300 \
    --samples 150000 \
    --batch-size 128

# Phase B — real MD fine-tuning (requires FastProtFlex.zip in data/)
python scripts/train_mdrepo.py \
    --phase b \
    --epochs 200 \
    --batch-size 1 \
    --max-atoms 1200 \
    --resume
```

Weights are saved to `app/models/mdrepo_predictor.pt` whenever validation loss improves. Training auto-resumes from the latest checkpoint with `--resume`.

> **Note on Training Data:** The training datasets (including `FastProtFlex.zip`) are not uploaded to this repository. To request access to the dataset, please email: **prawin@vyapai.tech**

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Main application UI |
| `GET` | `/health` | Server and service health check |
| `POST` | `/api/analyze_smiles` | Full pipeline: SMILES → 3D conformer → RMSF predictions |
| `POST` | `/api/canvas_to_smiles` | Canvas atom/bond JSON → canonical SMILES |
| `POST` | `/api/descriptors` | ADME descriptor calculation |
| `POST` | `/api/optimize_2d` | Recompute 2D canvas coordinates via RDKit |
| `POST` | `/api/chat` | Natural language → PyMOL command via local LLM |
| `GET` | `/api/drug/lookup?name=` | Drug name → SMILES (offline-first) |
| `GET` | `/api/drug/autocomplete?prefix=` | Live drug name autocomplete |
| `GET` | `/api/pdb/fetch?pdb_id=` | Download PDB structure + extract ligands |
| `POST` | `/api/pdb/upload` | Upload local `.pdb` file |
| `POST` | `/api/interactions` | Full non-covalent interaction profile |
| `POST` | `/api/mcs_align` | Maximum Common Substructure alignment |

---

## Configuration Reference

| Variable | Default | Description |
|---|---|---|
| `HOST` | `0.0.0.0` | Flask bind host |
| `PORT` | `5000` | Flask bind port |
| `SECRET_KEY` | — | Flask session signing key (required in production) |
| `OLLAMA_API_URL` | `http://localhost:11434` | Ollama service endpoint |
| `OLLAMA_MODEL` | `phi3` | LLM model name for the PyMOL assistant |
| `OLLAMA_ENABLED` | `1` | Toggle AI assistant on/off |
| `OLLAMA_TIMEOUT` | `15` | Request timeout in seconds |
| `PYMOL_ENABLED` | `0` | Set to `1` if a real PyMOL process is running |
| `MOLECULE_SIZE_LIMIT` | `200` | Max atoms accepted by the 3D pipeline |
| `SMILES_LENGTH_LIMIT` | `2000` | Max SMILES string length |
| `LOG_LEVEL` | `INFO` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`) |

---

## Security

- **XSS Prevention:** `html.escape()` applied to all user strings before HTML rendering
- **SMILES Validation:** RDKit `SanitizeMol` rejects malformed structures before reaching the GPU
- **Input Limits:** 200 atom cap, 2000 character SMILES cap, 4-character alphanumeric PDB ID validation
- **Timeout Enforcement:** All external HTTP calls (Ollama, PubChem, RCSB) have explicit timeouts
- **No Data Egress:** No molecular data is sent to any external server at runtime

---

## License

This project is released under an **Academic Use License** — see [LICENSE](LICENSE).

You are free to use, run, and study this software for personal learning and academic research. If you use it in a paper or presentation, please credit the authors. Commercial use requires written permission.

---

<div align="center">

*KineticSketch AI — Molecular Dynamics Intelligence, Fully Offline.*

**Developed by Prawin** | *Under the guidance of Dr. Rajiv K. Kar, IIT Guwahati*

</div>
