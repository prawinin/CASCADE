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
├── pdb_repurposing.py   # Live Class: RCSB PDB Target Mappings & Tanimoto Similarities
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
git clone https://github.com/prawin/KineticSketch.git
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

## 📄 Personal Academic Use License

This software is protected under a strict **Personal Academic Use License** (detailed in the [`LICENSE`](file:///home/prawin/Documents/GitHub/KineticSketch/LICENSE) file).

*   **Ownership:** The entire software suite, all integrated modules, and associated documentation are owned **exclusively by Prawin**.
*   **Usage:** Authorized solely for personal, non-commercial, and academic research purposes.
*   **Citation Requirement:** Any academic publication, paper, presentation, patent, or course using this software must formally credit **Prawin** as the creator and provide a citation to the repository.

---

## 🤝 Acknowledgments

Special thanks to the Live Session instruction guidance that inspired the integration of the RCSB PDB Drug Repurposing similarity search mechanics into the heart of this workspace pipeline.
