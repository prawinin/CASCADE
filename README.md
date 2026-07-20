# KineticSketch

KineticSketch is a molecular sketching and analysis project that I built to bring several computational chemistry steps into one browser workspace. A molecule can be drawn on the custom canvas, entered as SMILES, or searched by drug name. The same structure can then be viewed in 3D, checked for common drug-likeness rules, passed through a graph neural network, compared with a local drug database, and studied against a PDB protein structure.

This project was developed by Prawin under the guidance of Dr. Rajiv K. Kar, Assistant Professor, Jyoti and Bhupat Mehta School of Health Sciences & Technology, IIT Guwahati.

> KineticSketch is a research and learning prototype. The model outputs, docking results, ADMET values, design score, similarity-based estimates, and interaction maps are computational estimates. They are not experimental or clinical results.

## Main features

- Custom 2D molecular sketcher with draw, move, erase, zoom, pan, undo/redo, bond orders, and 23 ring/scaffold templates.
- Input by SMILES or drug name, with local autocomplete and PubChem fallback.
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

The detailed explanation of every UI feature, force field, formula, charge method, model layer, and current limitation is in [Project_KineticSketch.md](Project_KineticSketch.md).

The reusable internet-hosting, security, storage-lifecycle, testing, monitoring, and release checklist is in [PRODUCTION_READINESS_CHECKLIST.md](PRODUCTION_READINESS_CHECKLIST.md).

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
├── Project_KineticSketch.md        # Full explanation and live-demo guide
├── requirements.txt
├── run.py
└── wsgi.py
```

## Setup

The current reference environment is Fedora Linux with Python 3.13. A virtual environment is recommended.

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
PORT=5000
REDIS_URL=redis://localhost:6379/0
OLLAMA_ENABLED=1
OLLAMA_API_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5-coder:7b
PYMOL_ENABLED=0
```

The actual defaults are defined in `app/config.py`. Do not store real secrets in the repository.

## Running the application

```bash
source .venv/bin/activate
python run.py
```

Then open:

```text
http://127.0.0.1:5000
```

For queued Compute-page operations, Redis and a Celery worker are also required. The exact Celery app is `app.tasks.celery_app:celery_app`.

```bash
redis-server
celery -A app.tasks.celery_app:celery_app worker --loglevel=info
```

Without Redis, normal molecule rendering still works and 3D optimization has a local threaded fallback. Queued interaction and MD tasks require Redis/Celery.

## Optional components

### Ollama

Ollama is used to convert plain-English visualization requests into a limited command set. If it is unavailable, a keyword-based fallback is used.

```bash
ollama pull qwen2.5-coder:7b
```

### GNINA

Place an executable named `gnina` in the project root or set `GNINA_PATH`. Docking is unavailable without it.

### Local data and checkpoint

The current working repository contains:

- `data/drug_database.sqlite` with 2,898,063 drug rows and 5,576 drug-target rows;
- `data/drug_fingerprints.npz`; and
- `app/models/mdrepo_predictor.pt`.

These are large/generated research assets, so availability may differ between distributions of the repository. Their source and redistribution permissions should be checked before publishing them.

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
