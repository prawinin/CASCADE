---
title: CASCADE
emoji: 🧬
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
fullWidth: true
pinned: false
short_description: Molecular sketching, cheminformatics, and research analysis workspace
---

# CASCADE
<sub>Computational Architecture for Sketching, Conformation, ADMET, and Docking Evaluation</sub>

CASCADE is a comprehensive molecular sketching and analysis platform designed to unify several computational chemistry pipelines into a single browser-based workspace. Molecules can be drawn natively on the custom canvas, entered directly as SMILES strings, or resolved dynamically via a text-based drug name search. The resulting structure acts as a unified molecular object that can be visualized in 3D, evaluated against common drug-likeness rules, processed through a message-passing graph neural network (MPNN), compared against a local pharmacological database, and profiled for non-covalent interactions against PDB protein structures.

The application features a deterministic SMILES workflow. When a structure is drawn, the frontend canvas graph is serialized and converted into a validated RDKit molecule and canonical SMILES. Text-based drug name queries are resolved instantaneously through an optimized local SQLite FTS5 database, with the PubChem API available as a reliable fallback. The normalized SMILES string subsequently drives the downstream pipeline, acting as the foundation for 2D cleanup, 3D conformer generation, descriptor calculation, model inference, and target-interaction analysis.

CASCADE was developed by Prawin under the supervision of Dr. Rajiv K. Kar (Assistant Professor, Jyoti and Bhupat Mehta School of Health Sciences & Technology, IIT Guwahati).

> CASCADE is an advanced computational chemistry tool. The model predictions, docking poses, ADMET profiles, heuristic design scores, similarity-based binding estimates, and non-covalent interaction maps are computational approximations and do not substitute for in vitro or clinical validation.

## Main features

- Custom 2D molecular sketcher with draw, move, erase, zoom, pan, undo/redo, bond orders, and 23 ring/scaffold templates.
- Canvas-to-SMILES conversion, direct SMILES input, and automatic drug-name-to-SMILES resolution through local autocomplete with PubChem fallback.
- RDKit 2D cleanup and ETKDGv3 3D conformer generation.
- MMFF94, MMFF94s, and UFF force field minimization paths. (OPLS-AA is explicitly disabled/unsupported in the active release).
- Interactive 3Dmol.js viewer and SDF, XYZ, and MOL2 downloads.
- PyTorch message-passing neural network for per-atom and molecule-level estimates.
- Lipinski and Veber checks, live molecular descriptors, and a heuristic design score.
- ADMET-AI integration with a clearly labelled RDKit heuristic fallback.
- Local SQLite/FTS5 drug search and Morgan-fingerprint Tanimoto comparison.
- PDB fetch/upload, ligand selection, and geometry-based interaction profiling.
- Optional GNINA docking.
- Ollama-assisted natural-language commands for the 3D viewer.
- Celery/Redis task submission and activity log.

A comprehensive engineering and security audit detailing the implementation, dependencies, and verification findings is available in [AUDIT_REPORT.md](AUDIT_REPORT.md).

## How the pipeline works

1. The canvas graph or SMILES is converted into an RDKit molecule.
2. RDKit checks the structure and generates clean 2D coordinates.
3. Explicit hydrogens are added and ETKDGv3 generates a starting 3D conformer.
4. A force-field path relaxes the geometry.
5. The structure is written to SDF, XYZ, and MOL2.
6. Molecular descriptors and drug-likeness rules are calculated.
7. The GNN uses atom types and pairwise 3D distances to produce learned estimates.
8. The molecule is compared with local drug fingerprints for possible reference matches.
9. A selected PDB structure can be inspected for geometric protein-ligand contacts.

## Important scientific distinctions

- The main Conformers charge column is a learned GNN output. The background optimization task separately calculates RDKit Gasteiger–Marsili PEOE charges.
- The learned HOMO–LUMO value is not a new quantum-chemistry calculation.
- Tanimoto similarity is structural similarity, not a calibrated binding probability.
- The displayed similarity-based ΔG is a project heuristic, not measured free energy.
- The current local OpenMM-labelled backend demonstrates task orchestration and returns an example curve; it does not yet run physical MD.
- The OPLS-AA force field option is explicitly disabled in the engine. Users must select MMFF94, MMFF94s, or UFF.

## Technology used

- Python and Flask
- RDKit
- PyTorch
- BioPython
- HTML5 Canvas and vanilla JavaScript
- 3Dmol.js
- SQLite with FTS5
- Celery and Redis
- ADMET-AI when available
- Ollama when available
- GNINA when installed separately

## Repository structure

```text
CASCADE/
├── app/
│   ├── gui/index.html              # Complete browser interface
│   ├── static/sketch.js            # Sketcher and page interactions
│   ├── static/interaction_viewer.js
│   ├── services/                   # Chemistry, model, PDB, docking, ADMET services
│   ├── tasks/                      # Celery task definitions
│   ├── models/                     # GNN checkpoint and training history
│   ├── config.py
│   └── main.py                     # Flask application and API routes
├── data/                           # Local database, fingerprints, action logs
├── scripts/
│   ├── build_drug_db.py
│   └── train_mdrepo.py
├── AUDIT_REPORT.md                 # Verified engineering findings
├── requirements.txt
├── run.py
└── wsgi.py
```

## Quick Start

### Requirements

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows / macOS / Linux)
- Python 3.11+ (for `compose_up.py`; not needed if you use `docker compose` directly)
- ~900 MB free disk space for the data and model files

### 1. Clone the repo

```bash
git clone https://github.com/prawinin/CASCADE.git
cd CASCADE
```

### 2. Download data files

The drug database, fingerprints, and model weights are hosted as a GitHub Release
(too large for the repository itself). Run the setup script for your OS:

**Linux / macOS:**
```bash
bash setup.sh
```

**Windows (PowerShell):**
```powershell
.\setup.ps1
```

This downloads three files into the correct locations:
- `data/drug_database.sqlite` — 2.89 M compounds
- `data/drug_fingerprints.npz` — memory-mapped fingerprint index
- `app/models/mdrepo_predictor.pt` — trained GNN weights

If any file already exists it is skipped automatically.

### 3. Start the application

```bash
python compose_up.py
```

That's it. The script will:
1. Create a `.env` file from `.env.example` if one does not exist
2. Auto-generate a secure `FLASK_SECRET_KEY` and save it to `.env`
3. Pick a free port (default 7860) and launch all services
4. Open the app in your browser

Or launch without Python if you prefer:

```bash
docker compose up
```

(You must set `FLASK_SECRET_KEY` in `.env` manually if using this path directly.)

### 4. Register your account

On first run, registration is open. Go to `http://localhost:7860`, create your
account, then optionally close registration in `.env`:

```env
REGISTRATION_ENABLED=0
```

Run `docker compose restart app` to apply.

### Stopping

```bash
docker compose down
```

---

## Optional components

### Ollama (local LLM assistant)

CASCADE can use a locally running Ollama instance to interpret plain-English
commands for the 3D viewer. To enable it:

1. Install Ollama from [ollama.com](https://ollama.com) and pull a model:
   ```bash
   ollama pull qwen2.5-coder:7b
   ```
2. Edit `.env`:
   ```env
   OLLAMA_ENABLED=1
   OLLAMA_API_URL=http://host.docker.internal:11434
   OLLAMA_MODEL=qwen2.5-coder:7b
   ```
3. Restart: `docker compose restart app celery_worker`

`host.docker.internal` is the special Docker hostname that routes to your host
machine where Ollama is running. On Linux, replace it with your host IP if needed.

### GNINA docking

To enable real CNN-based molecular docking, place the `gnina` binary in the
project root and add to `.env`:

```env
GNINA_ENABLED=1
GNINA_PATH=./gnina
```

### GPU inference

Change `MODEL_DEVICE` in `.env`:

```env
MODEL_DEVICE=cuda    # NVIDIA
MODEL_DEVICE=cpu     # default
```

---

## Traditional local installation (no Docker)

The portable runtime targets Python 3.11+ and CPU inference. A virtual environment is recommended.

```bash
git clone https://github.com/prawinin/CASCADE.git
cd CASCADE
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Copy and configure the environment file:

```bash
cp .env.example .env
# Edit .env — at minimum set a real FLASK_SECRET_KEY
```

Download the data files (same as the Docker path):

```bash
bash setup.sh   # Linux/macOS
# or .\setup.ps1 on Windows
```

Start the full stack manually:

```bash
redis-server &
celery -A app.tasks.celery_app:celery_app worker --loglevel=info &
python run.py
```

Without Redis, molecule rendering still works but every Compute-page task returns HTTP 503.

## Main API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/` | Main interface |
| GET | `/health` | Service and database health |
| POST | `/api/analyze_smiles` | Run the main molecular pipeline |
| POST | `/api/canvas_to_smiles` | Convert canvas graph to SMILES |
| POST | `/api/optimize_2d` | Clean 2D coordinates |
| POST | `/api/descriptors` | Calculate molecular descriptors |
| GET | `/api/drug/lookup` | Resolve a drug name |
| GET | `/api/drug/autocomplete` | Local name suggestions |
| GET | `/api/pdb/fetch` | Fetch a PDB and list ligands |
| POST | `/api/pdb/upload` | Securely upload a local PDB/ENT/PDB.GZ file |
| POST | `/api/interactions` | Generate an interaction profile |
| POST | `/api/dock` | Run GNINA docking |
| POST | `/api/admet` | Run ADMET model/fallback |
| POST | `/api/mcs_align` | Generate MCS-aligned coordinates |
| POST | `/api/tasks/submit` | Submit a compute task |
| GET | `/api/tasks/status/<id>` | Read task status/result (enforces task ownership) |
| DELETE | `/api/tasks/cancel/<id>` | Revoke a queued task (enforces task ownership) |
| GET | `/api/download/<job_id>/<file_type>` | Download job artifacts securely |

## Security and Production Architecture

- **Isolated Job Workspaces:** Per-user and per-job directory isolation (`jobs/<user-id>/<job-id>/`) with strict UUID path canonicalization to prevent traversal attacks.
- **Fail-Closed GNN Loading:** SHA-256 weight hash validation with automatic abort on checkpoint mismatch or corruption.
- **Authentication & Ownership:** Session security flags, rate-limited login, and SQLite task ownership mapping.
- **Container Hardening:** Isolated internal service ports (Redis, PyMOL, Ollama) and shared persistent volumes.
- **Explicit Inference Device:** `MODEL_DEVICE=cpu` is the safe default; GPU execution must be selected explicitly.
- **Health Probes:** `/health/live` reports liveness and `/health/ready` verifies Redis, SQLite, writable job storage, and the model checkpoint.

## Training

The model architecture is in `app/services/models.py`, and the training program is in `scripts/train_mdrepo.py`.

```bash
python scripts/train_mdrepo.py --help
```

The model loader fails closed if trained weights are corrupt or missing, ensuring only verified model weights are used for inference.

## Known limitations

- Research prototype; not validated for clinical use.
- The OpenMM-labelled local backend is currently a demonstration and does not yet run physical MD simulations.
- OPLS-AA is explicitly disabled and unavailable.
- MCS coordinates are generated, but the overlay is not drawn yet.
- External dependencies (PubChem, RCSB, GNINA) require network access or local binaries.

## License

See [LICENSE](LICENSE). External libraries, datasets, PDB structures, model assets, and drug-database content may have their own licenses and attribution requirements.
