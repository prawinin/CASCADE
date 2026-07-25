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
KineticSketch/
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

## Setup

### 1. Docker Installation (Recommended)
The easiest and most reliable way to run the application across any operating system (Windows, Mac, Linux) is using Docker. This avoids manual dependency management and guarantees computational reproducibility.

If you do not have Docker installed, please download and install [Docker Desktop](https://www.docker.com/products/docker-desktop/).

Once Docker is running on your machine, simply execute:

```bash
git clone https://github.com/prawinin/KineticSketch.git
cd KineticSketch
python compose_up.py
```
The script will automatically allocate a free port, spin up all required databases and Python dependencies isolated in a container, and launch the application in your default web browser.

### 2. Traditional Local Installation
Alternatively, if you prefer running it directly on your host machine, the portable runtime targets Python 3.11 or newer and CPU inference. A virtual environment is highly recommended.

```bash
git clone https://github.com/prawinin/KineticSketch.git
cd KineticSketch

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

The AMD/ROCm dependency notes are in `requirements_amd_rocm63_rdna2.txt`.

Copy the example environment file if configuration is needed:

```bash
cp .env.example .env
```

Useful settings include:

```env
HOST=127.0.0.1
# Leave PORT unset locally to select the first free port from 7860.
REDIS_URL=redis://localhost:6379/0
OLLAMA_ENABLED=0
OLLAMA_API_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5-coder:7b
PYMOL_ENABLED=0
GNINA_ENABLED=0
```

The actual defaults are defined in `app/config.py`. Do not store real secrets in the repository.

## Running the application

```bash
source .venv/bin/activate
python run.py
```

The launcher prints the selected URL. If `PORT` is not set, it chooses the first
available port starting at 7860. Hosting-provider ports are honored exactly.

For queued Compute-page operations, Redis and a Celery worker are also required. The exact Celery app is `app.tasks.celery_app:celery_app`.

```bash
redis-server
celery -A app.tasks.celery_app:celery_app worker --loglevel=info
```

Without Redis, normal molecule rendering still works, but every Compute-page task returns HTTP 503. This fail-closed behavior avoids inconsistent task state across multiple web workers.

## Optional components

### Ollama

Ollama is used to convert plain-English visualization requests into a limited command set. If it is unavailable, a keyword-based fallback is used.

```bash
ollama pull qwen2.5-coder:7b
```

### GNINA

GNINA is not required. Deployed builds disable it by default and hide docking
controls. For an optional local installation, place an executable named `gnina`
in the project root or set `GNINA_PATH` and `GNINA_ENABLED=1`.

### Local data and checkpoint

The current working repository contains:

- `data/drug_database.sqlite` with 2,898,063 drug rows and 5,576 drug-target rows;
- `data/drug_fingerprints.npz`; and
- `app/models/mdrepo_predictor.pt`.

These are large/generated research assets, so availability may differ between distributions of the repository. Their source and redistribution permissions should be checked before publishing them.

Copy these assets to the listed project-relative paths before building. Runtime
locations are resolved from the installed project root, not the shell's working
directory, and every storage path has an environment override.



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
