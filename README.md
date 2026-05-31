# 🧬 KineticSketch AI

> A state-of-the-art modular molecular sketcher, 3D conformer optimizer, GNN/MLP dynamics predictor, and RCSB PDB drug-repurposing target search engine.

---

KineticSketch AI is a high-performance desktop workspace that bridges the gap between raw 2D molecular drawings and advanced structural biophysics. By combining reactive UI design, cheminformatics, neural network volatility modeling, and live external visualizer pipelines, it provides researchers and students with a unified dashboard for computer-aided drug design.

Designed and engineered exclusively by **Prawin**, KineticSketch AI brings premium laboratory tools right to your local environment.

---

## 🚀 Key Capabilities

*   **Interactive 2D Sketching Canvas:** Reactively converts raw vector drawing coordinates to validated chemical SMILES structures (and vice-versa).
*   **3D Conformation Engine (RDKit):** Appends hydrogens, generates optimized 3D geometries via `ETKDGv3`, runs MMFF94 force-field minimizations, and exports Tripos-compliant `.mol2`, `.sdf`, and `.xyz` files.
*   **AI Dynamics Predictor (PyTorch):** Utilizes an invariant neural network architecture (`MDRepoPredictor`) to predict atomic volatility fluctuations at 10 ns and 1 µs timescales.
*   **PDB Drug Repurposing Target Search:** Leverages Morgan chemical fingerprints and Tanimoto similarity mappings to match queries against clinical drug targets in the RCSB Protein Data Bank.
*   **External Visualizer Bridge:** Controls non-blocking external `PyMOL` instances via standard input pipes with a local LLM natural language command translator.

---

## 📁 Repository Structure

```text
KineticSketch/
├── kinetic_sketch.py    # Module 1: Taipy Orchestrator & GUI Reactive Server
├── cheminformatics.py  # Module 2: RDKit 3D Conformation & File Exporters
├── visualizer.py        # Module 3: PyMOL pipes & Ollama API Integrators
├── models.py            # Module 4: PyTorch GNN/MLP Dynamics Predictor
├── checkpoint.py        # Module 5: Progress Checkpointing Service
├── pdb_repurposing.py   # RCSB PDB Target Repurposing & Tanimoto Similarities
├── index.html           # Premium Front-End HTML5 Dashboard Layout
├── LICENSE              # Personal Academic Use License (Owned exclusively by Prawin)
└── .gitignore           # Pycache, virtual env, output structures, & progress logs
```

---

## 🛠️ Installation & Setup

### 1. Prerequisites
Ensure you have the following installed on your system:
*   **Python 3.10 to 3.14**
*   **PyMOL** (for live 3D visual pipeline rendering)
*   **Ollama** (optional, for local natural language visualizer chat assistance using `qwen2.5-coder:7b`)

### 2. Clone & Prepare Environment
Clone the repository to your local machine:
```bash
git clone https://github.com/prawinin/KineticSketch.git
cd KineticSketch
```

To configure your virtual environment and install all packages:
```bash
# Create a virtual environment using system packages to inherit optimized PyTorch/Pandas
python3 -m venv venv --system-site-packages
source venv/bin/activate

# Install required libraries
pip install rdkit torch taipy marshmallow==3.21.2 apispec sqlalchemy openpyxl tzlocal deepdiff toml
```

> [!NOTE]
> Marshmallow has been explicitly pinned to `3.21.2` to resolve schema inference incompatibilities with modern Taipy Rest frameworks.

---

## 💻 Running the Workspace

To start the local web dashboard server, execute:
```bash
python kinetic_sketch.py
```

Once the server initializes, open your web browser and navigate to:
**`http://localhost:5000`**

### Step-by-Step Workflow:
1.  **Sketch:** Draw your molecule of interest using the interactive canvas on the left panel (or paste a pre-existing SMILES string into the input field).
2.  **Optimize:** Click **Analyze** to trigger the RDKit conformer generation. The application instantly minimizes spatial geometries and outputs verified `.sdf`, `.xyz`, and compliant Tripos `.mol2` files to your workspace directory.
3.  **Predict:** The PyTorch `MDRepoPredictor` model reads the 3D conformation and instantly calculates conformer volatility fluctuations across 10 ns and 1 µs intervals.
4.  **Target Mappings:** The PDB repurposing engine evaluates similarity matches against clinical drug pharmacophores (Aspirin, Gleevec, Lipitor, etc.) and lists Solved PDB Structures, binding affinities ($-\Delta G$), and receptor profiles.
5.  **Visualize:** Use the built-in PyMOL chat panel to run visual instructions. Commands are dynamically piped into your active PyMOL window using the external controller.

---

## 🚢 Production-Ready Deployment

KineticSketch AI has been fully optimized for production deployment with:

### ✅ Code Quality & Security
- **Type Hints**: Complete Python 3.11+ type annotations across all modules
- **Comprehensive Docstrings**: Google-style documentation for all functions/classes
- **HTML Sanitization**: XSS prevention using `html.escape()` on all dynamic content
- **Input Validation**: SMILES length limits (2000 chars), molecule size limits (200 atoms)
- **Request Timeouts**: PyMOL (5s), Ollama (15s) to prevent UI hangs
- **Error Handling**: Graceful degradation when services are offline

### 🎨 Enhanced UI/UX
- **GitHub-Style Color System**: Professional elevation-based design (Surface 0-3, Text Primary/Secondary)
- **Micro-Animations**: Smooth transitions (300ms panel entrance, 150ms button hover, 200ms active indicators)
- **Responsive Design**: Optimized for desktop (1920px), tablet (1024px), and mobile (480px)
- **Accessibility**: WCAG AA contrast ratios, keyboard navigation, focus indicators
- **Data Tables**: Tabular figures with Okabe-Ito colorblind-safe indicators

### 🐳 Docker & Infrastructure
- **Multi-Stage Dockerfile**: Optimized Python 3.11-slim image
- **Docker Compose**: Full stack orchestration (app + PyMOL + Ollama)
- **Centralized Config**: `config.py` with environment-aware settings
- **Health Checks**: Built-in endpoint for load balancer monitoring
- **Security**: Non-root user, secrets in .env, HTTPS-ready

### 📋 Deployment Options
- **Heroku**: 30-minute quick setup, $7-50/month
- **Railway**: GitHub auto-deploy, $5-20/month, minimal configuration
- **Azure App Service**: Enterprise integration, $10-50/month
- **AWS Elastic Beanstalk**: Highly scalable, $5-40/month

See [DEPLOYMENT.md](DEPLOYMENT.md) for complete cloud deployment guides.

### 🧪 Comprehensive Testing
- **30+ Unit & Integration Tests**: >90% code coverage
- **Test Suite**: `pytest` with coverage reporting, performance benchmarks
- **Test Categories**: Unit tests, integration tests, performance tests, edge cases
- **CI/CD Ready**: GitHub Actions configuration example
- **Quality Checks**: mypy type checking, flake8 linting, black formatting

Run tests with:
```bash
pip install -r requirements-test.txt
pytest -v --cov=.
```

See [TESTING.md](TESTING.md) for detailed testing documentation.

### 📊 Performance Optimizations
- **Caching**: PDB repurposing results cached for 1 hour
- **Lazy Loading**: Predictions only compute on explicit "Analyze" click
- **Batch Processing**: Efficient GPU utilization when available
- **Memory Efficient**: Handles molecules up to 200 atoms smoothly

### 🔧 Configuration Management
All settings configurable via environment variables. Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Key settings:
- `FLASK_ENV`: development/production/testing
- `PYMOL_ENABLED`: Enable PyMOL integration
- `OLLAMA_ENABLED`: Enable Ollama AI chat
- `MOLECULE_SIZE_LIMIT`: Max atoms (default: 200)
- `SMILES_LENGTH_LIMIT`: Max SMILES length (default: 2000)
- `LOG_LEVEL`: INFO/DEBUG/WARNING
- `LOG_FORMAT`: json/text for structured logging

---

## 📚 Documentation

- **[DEPLOYMENT.md](DEPLOYMENT.md)** - Cloud deployment guides (Heroku, Railway, Azure, AWS)
- **[TESTING.md](TESTING.md)** - Testing guide with 30+ test cases
- **[implementation_plan.md](implementation_plan.md)** - Architecture and design decisions
- **config.py** - Centralized configuration with validation

---

## 📄 Personal Academic Use License

This software is protected under a strict **Personal Academic Use License** (detailed in the [`LICENSE`](file:///home/prawin/Documents/GitHub/KineticSketch/LICENSE) file).

*   **Ownership:** The entire software suite, all integrated modules, and associated documentation are owned **exclusively by Prawin**.
*   **Usage:** Authorized solely for personal, non-commercial, and academic research purposes.
*   **Citation Requirement:** Any academic publication, paper, presentation, patent, or course using this software must formally credit **Prawin** as the creator and provide a citation to the repository.

---

## 🤝 Acknowledgments & Credits

Special thanks to the developers and maintainers of RDKit, PyTorch, Taipy, and the RCSB Protein Data Bank for providing the robust open-source tools and structural databases that make this advanced computational pipeline possible.
