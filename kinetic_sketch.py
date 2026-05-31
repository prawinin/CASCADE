#!/usr/bin/env python3
"""
KineticSketch AI - Molecular Dynamics Workspace
Main Entrypoint & GUI Orchestration Server
Clean Modular Multi-File Architecture
"""

import os
import sys
import json
import logging
from datetime import datetime
from typing import Any

# Configure native logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("KineticSketch.Main")

# Import custom modular services
try:
    from checkpoint import CheckpointManager
    from models import MDRepoPredictor, get_one_hot_nodes
    from cheminformatics import optimize_conformer_3d, write_all_conformers
    from visualizer import query_ollama_for_pymol, execute_pymol_commands, get_pymol_process
    from pdb_repurposing import find_repurposing_targets
except ImportError as e:
    logger.critical(f"Failed to import local modules! Ensure they exist. Error: {e}")
    sys.exit(1)

# Import chemical and GUI frameworks
try:
    from rdkit import Chem
    from rdkit.Chem import rdDepictor
except ImportError:
    logger.error("RDKit not found globally or in venv site-packages!")
    Chem = None
    rdDepictor = None

try:
    import torch
except ImportError:
    logger.error("PyTorch not found globally or in venv!")
    torch = None

try:
    from taipy.gui import Gui, Html, State
except ImportError:
    logger.error("Taipy GUI framework not available!")
    Gui = None
    Html = None
    State = None

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None


# Initialize central checkpoint service manager
checkpoint_manager = CheckpointManager()


# =====================================================================
# TAIPY GUI REACTIVE VARIABLE BINDINGS
# =====================================================================
canvas_payload = "{}"
smiles_input = ""
chat_prompt = ""
chat_log_html = ""
predictions_html = "<div style='color: var(--text-muted); font-size: 0.95rem; font-style: italic;'>Draw a molecule or enter a SMILES to trigger optimization and predictions.</div>"
repurposing_html = "<div style='color: var(--text-muted); font-size: 0.95rem; font-style: italic;'>Sketched drug target repurposing matches will populate here.</div>"
checkpoint_logs_html = "<div class='checkpoint-log-line'><span class='checkpoint-time'>[INIT]</span> Checkpoint engine initialized.</div>"


def log_checkpoint_to_ui(state: State, message: str, level: str = "success"):
    """
    Appends a formatted log boundary line to the checkpoint GUI viewport.
    """
    time_str = datetime.now().strftime("%H:%M:%S")
    color_class = "checkpoint-success"
    if level == "warning":
        color_class = "checkpoint-warning"
    elif level == "error":
        color_class = "checkpoint-error"
    elif level == "info":
        color_class = "checkpoint-time"
        
    line_html = f"<div class='checkpoint-log-line'><span class='checkpoint-time'>[{time_str}]</span> <span class='{color_class}'>{message}</span></div>"
    state.checkpoint_logs_html += line_html


def run_molecular_pipeline(state: State, mol: Chem.Mol):
    """
    Coordinates conformational optimization and deep learning predictions.
    Calls cheminformatics, PyTorch models, and checkpointing services.
    """
    global checkpoint_manager
    if mol is None:
        return

    smiles = Chem.MolToSmiles(mol)
    logger.info(f"Initiating modular dynamics pipeline for SMILES: {smiles}")

    state.predictions_html = "<div style='color: var(--secondary); font-size: 0.95rem;'>Running structural dynamics optimization pipeline...</div>"

    # Reset progress checkpoint to INITIALIZED
    checkpoint_manager.save_checkpoint("INIT", {"smiles": smiles})
    log_checkpoint_to_ui(state, f"Starting compilation pipeline for SMILES: {smiles}", "info")

    try:
        # Step progress bar sequence for terminal view
        steps = ["Add Hydrogens & Embed", "MMFF94 Optimize", "Write Conformers", "Run Inference"]
        iterator = tqdm(steps, desc="Assembling Conformers") if tqdm is not None else steps
        
        mol_h = None
        
        for idx, step in enumerate(iterator):
            if idx == 0:
                # 1. 3D Coordinates Conformation Embedding
                mol_h = optimize_conformer_3d(mol)
                checkpoint_manager.save_checkpoint("EMBED_3D")
                log_checkpoint_to_ui(state, "Generated 3D coordinate conformation via ETKDGv3 and appended hydrogens.", "success")
            
            elif idx == 1:
                # 2. Conformer minimization (MMFF94) is already handled inside optimize_conformer_3d
                checkpoint_manager.save_checkpoint("MINIMIZE_3D")
                log_checkpoint_to_ui(state, "Minimized conformer geometry using MMFF94 force field calculations.", "success")

            elif idx == 2:
                # 3. Stream coordinate structures to SDF, XYZ, and Tripos MOL2 formats
                sdf_path = "molecule.sdf"
                xyz_path = "molecule.xyz"
                mol2_path = "molecule.mol2"
                
                write_all_conformers(mol_h, sdf_path, xyz_path, mol2_path)

                checkpoint_manager.save_checkpoint("WRITE_FILES", {
                    "sdf_path": sdf_path,
                    "xyz_path": xyz_path,
                    "mol2_path": mol2_path
                })
                log_checkpoint_to_ui(state, "Wrote optimized structural coordinate conformers to .sdf, .xyz, and .mol2 formats.", "success")

            elif idx == 3:
                # 4. PyTorch Tensor extraction and predictive inference
                conf = mol_h.GetConformer()
                positions = []
                for i in range(mol_h.GetNumAtoms()):
                    pos = conf.GetAtomPosition(i)
                    positions.append([pos.x, pos.y, pos.z])

                pos_tensor = torch.tensor(positions, dtype=torch.float32)
                node_features = get_one_hot_nodes(mol_h)

                checkpoint_manager.save_checkpoint("EXTRACT_TENSORS")
                log_checkpoint_to_ui(
                    state,
                    f"Generated PyTorch tensors: Position shape={list(pos_tensor.shape)}, node features={list(node_features.shape)}",
                    "success"
                )

                # MDRepo fast predictive inference
                predictor = MDRepoPredictor()
                predictor.eval()
                
                with torch.no_grad():
                    predictions = predictor(pos_tensor, node_features)  # Shape (N, 2)

                checkpoint_manager.save_checkpoint("RUN_INFERENCE", {
                    "predictions": predictions.tolist()
                })
                log_checkpoint_to_ui(state, "MDRepo dynamic atomic fluctuation predictions computed successfully.", "success")

                # Render dynamic predictions table
                render_predictions_table(state, mol_h, predictions)
                
                # Render dynamic PDB drug repurposing table
                render_repurposing_table(state, smiles)

    except Exception as e:
        logger.error(f"Error in dynamics integration pipeline: {e}", exc_info=True)
        log_checkpoint_to_ui(state, f"Interruption detected: {str(e)}", "error")
        state.predictions_html = f"<div style='color: var(--accent); font-size: 0.95rem;'>Pipeline Failure: {str(e)}</div>"


def render_predictions_table(state: State, mol: Chem.Mol, predictions: torch.Tensor):
    """
    Formats neural network variance coordinates into a dynamic premium HTML table.
    """
    lines = []
    lines.append("<table class='predictions-table'>")
    lines.append("<thead><tr><th>Atom</th><th>Element</th><th>X, Y, Z Coords</th><th>10 ns Fluctuation (Å²)</th><th>1 µs Fluctuation (Å²)</th></tr></thead>")
    lines.append("<tbody>")

    conf = mol.GetConformer()
    for i in range(mol.GetNumAtoms()):
        atom = mol.GetAtomWithIdx(i)
        symbol = atom.GetSymbol()
        pos = conf.GetAtomPosition(i)
        var_10ns = predictions[i, 0].item()
        var_1us = predictions[i, 1].item()

        # Styles based on volatility thresholds
        color_class = "element-" + symbol
        color_10ns = "var(--success)" if var_10ns < 0.25 else "var(--warning)" if var_10ns < 0.55 else "var(--accent)"
        color_1us = "var(--success)" if var_1us < 0.45 else "var(--warning)" if var_1us < 0.85 else "var(--accent)"

        lines.append("<tr>")
        lines.append(f"<td>#{i+1}</td>")
        lines.append(f"<td><span class='element-dot {color_class}'></span><span class='{color_class}'>{symbol}</span></td>")
        lines.append(f"<td style='color: var(--text-muted)'>{pos.x:.2f}, {pos.y:.2f}, {pos.z:.2f}</td>")
        lines.append(f"<td style='color: {color_10ns}'><span class='variance-indicator' style='background: {color_10ns}'></span>{var_10ns:.4f}</td>")
        lines.append(f"<td style='color: {color_1us}'><span class='variance-indicator' style='background: {color_1us}'></span>{var_1us:.4f}</td>")
        lines.append("</tr>")

    lines.append("</tbody></table>")
    state.predictions_html = "\n".join(lines)


def render_repurposing_table(state: State, smiles: str):
    """
    Queries PDB repurposing targets using Morgan-Tanimoto similarity
    and formats them as a premium HTML table inside the GUI.
    """
    targets = find_repurposing_targets(smiles)
    if not targets:
        state.repurposing_html = "<div style='color: var(--text-muted); font-size: 0.95rem; font-style: italic; text-align: center; padding: 1rem;'>No high-similarity PDB drug targets identified. Sketched molecule represents a novel chemical fragment!</div>"
        return

    lines = []
    lines.append("<table class='repurposing-table'>")
    lines.append("<thead><tr><th>Drug Match</th><th>PDB ID</th><th>Protein Target Receptor</th><th>Morgan Sim</th></tr></thead>")
    lines.append("<tbody>")

    # Show top 5 matches
    for t in targets[:5]:
        sim_val = t["similarity"]
        sim_percent = sim_val * 100
        
        # Color threshold for similarity
        sim_color = "var(--success)" if sim_val > 0.6 else "var(--secondary)" if sim_val > 0.3 else "var(--text-muted)"
        
        # Progress gauge HTML structure
        bar_gauge = (
            f"<div style='display: flex; align-items: center; gap: 8px; justify-content: flex-end;'>"
            f"<div style='background: rgba(255,255,255,0.06); border-radius: 4px; height: 6px; width: 60px; overflow: hidden;'>"
            f"<div style='background: {sim_color}; height: 100%; width: {sim_percent}%;'></div>"
            f"</div>"
            f"<span style='color: {sim_color}; font-weight: 600; font-size: 0.8rem; min-width: 38px; text-align: right;'>{t['binding_probability']}</span>"
            f"</div>"
        )

        lines.append("<tr>")
        lines.append(f"<td style='color: var(--text-main); font-weight: 600;'>{t['matched_drug']}</td>")
        lines.append(f"<td><span class='badge' style='background: rgba(138,43,226,0.15); border-color: var(--primary); color: #fff; padding: 1px 6px; font-size: 0.72rem; font-family: inherit;'>{t['pdb_id']}</span></td>")
        lines.append(f"<td style='color: var(--text-muted); font-size: 0.8rem;' title='{t['function']}'>{t['target_name']}</td>")
        lines.append(f"<td>{bar_gauge}</td>")
        lines.append("</tr>")

    lines.append("</tbody></table>")
    state.repurposing_html = "\n".join(lines)


# =====================================================================
# TAIPY STATE REACTIVE BINDINGS (MODULE 1 BRIDGE)
# =====================================================================
def on_chat_send(state: State):
    """
    Processes chat prompt through visualizer service connection APIs.
    """
    prompt = state.chat_prompt
    if not prompt or not prompt.strip():
        return

    # Append user bubble
    user_bubble = f"<div class='chat-message message-user'>{prompt}</div>"
    state.chat_log_html += user_bubble

    # Query Ollama service (returns raw script commands)
    pymol_commands = query_ollama_for_pymol(prompt)

    # Clean script command bounds
    cleaned_lines = []
    for line in pymol_commands.split("\n"):
        line = line.strip()
        if not line or line.startswith("```"):
            continue
        cleaned_lines.append(line)
    commands_text = "\n".join(cleaned_lines)

    # Pipe commands to local visualizer subprocess
    exec_success = execute_pymol_commands(commands_text)

    # Format system bubble response
    sys_bubble = f"<div class='chat-message message-system'>"
    if exec_success:
        sys_bubble += "Intercepted request and piped commands directly to running PyMOL visualizer:"
    else:
        sys_bubble += "Ollama intercepted request (PyMOL offline - showing generated script):"
    
    sys_bubble += f"<pre class='pymol-code-block'>{commands_text}</pre></div>"
    state.chat_log_html += sys_bubble

    # Clear prompt input
    state.chat_prompt = ""


def on_change(state: State, var_name: str, var_value: Any):
    """
    Central reactive event listener bridging sketch vectors and pasted SMILES inputs.
    """
    if var_name == "canvas_payload":
        try:
            payload = json.loads(var_value)
            atoms = payload.get("atoms", [])
            bonds = payload.get("bonds", [])
            
            if not atoms:
                state.smiles_input = ""
                state.predictions_html = "<div style='color: var(--text-muted); font-size: 0.95rem; font-style: italic;'>Draw a molecule or enter a SMILES to trigger optimization and predictions.</div>"
                state.repurposing_html = "<div style='color: var(--text-muted); font-size: 0.95rem; font-style: italic;'>Sketched drug target repurposing matches will populate here.</div>"
                return

            # Reconstruct RDKit RWmol from canvas coordinates and bonds
            rw_mol = Chem.RWMol()
            atom_map = {}
            
            for atom_data in atoms:
                el = atom_data.get("element", "C")
                rd_atom = Chem.Atom(el)
                rd_idx = rw_mol.AddAtom(rd_atom)
                atom_map[atom_data["id"]] = rd_idx

            bond_types = {
                1: Chem.BondType.SINGLE,
                2: Chem.BondType.DOUBLE,
                3: Chem.BondType.TRIPLE
            }
            
            for bond_data in bonds:
                src = bond_data.get("source")
                tgt = bond_data.get("target")
                b_type = bond_data.get("type", 1)
                
                if src in atom_map and tgt in atom_map:
                    rw_mol.AddBond(
                        atom_map[src], 
                        atom_map[tgt], 
                        bond_types.get(b_type, Chem.BondType.SINGLE)
                    )

            # Sanitize structure
            mol = rw_mol.GetMol()
            Chem.SanitizeMol(mol)
            
            smiles = Chem.MolToSmiles(mol)
            state.smiles_input = smiles
            
            # Execute computational dynamics pipeline
            run_molecular_pipeline(state, mol)
            
        except Exception as e:
            logger.debug(f"Parsing partial drawn state canvas payload: {e}")

    elif var_name == "smiles_input":
        smiles = var_value.strip()
        if not smiles:
            return

        try:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                log_checkpoint_to_ui(state, f"Invalid SMILES string entered: '{smiles}'", "error")
                return

            # Calculate 2D coordinates layout
            rdDepictor.Compute2DCoords(mol)
            conf = mol.GetConformer()

            # Format canvas rendering coordinate payload
            canvas_atoms = []
            for i in range(mol.GetNumAtoms()):
                atom = mol.GetAtomWithIdx(i)
                pos = conf.GetAtomPosition(i)
                canvas_atoms.append({
                    "id": i + 1,
                    "x": pos.x * 50.0,
                    "y": pos.y * 50.0,
                    "element": atom.GetSymbol()
                })

            canvas_bonds = []
            for bond in mol.GetBonds():
                bt = bond.GetBondType()
                b_type = 1
                if bt == Chem.BondType.DOUBLE: b_type = 2
                elif bt == Chem.BondType.TRIPLE: b_type = 3
                
                canvas_bonds.append({
                    "source": bond.GetBeginAtomIdx() + 1,
                    "target": bond.GetEndAtomIdx() + 1,
                    "type": b_type
                })

            payload = {
                "atoms": canvas_atoms,
                "bonds": canvas_bonds
            }
            
            # Update canvas payload (Observer redraws canvas in browser!)
            state.canvas_payload = json.dumps(payload)
            
            # Run computational pipeline
            run_molecular_pipeline(state, mol)

        except Exception as e:
            logger.error(f"Failed to process pasted SMILES representation: {e}")
            log_checkpoint_to_ui(state, f"SMILES Error: {str(e)}", "error")


# =====================================================================
# SERVER RUN ENTRYPOINT
# =====================================================================
if __name__ == "__main__":
    logger.info("Starting modular KineticSketch AI Workspace Server...")
    
    # Pre-spawn PyMOL pipeline dynamically
    get_pymol_process()
    
    # Load frontend index template
    html_page = Html("index.html")
    
    # Run Taipy GUI web server
    gui = Gui(page=html_page)
    gui.run(
        title="KineticSketch AI - Molecular Dynamics Workspace",
        use_reloader=False,
        port=5000,
        dark_mode=True
    )
