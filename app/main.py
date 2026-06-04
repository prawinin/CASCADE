#!/usr/bin/env python3
"""
KineticSketch - Molecular Dynamics Workspace
Main Entrypoint & GUI Orchestration Server
Clean Modular Multi-File Architecture
"""

import os
import sys
import json
import logging
import html as html_module
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# Setup relative paths so the project can be run from anywhere
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)
services_dir = os.path.join(current_dir, "services")
if services_dir not in sys.path:
    sys.path.insert(0, services_dir)

from config import get_config

config = get_config()

# Configure native logging
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("KineticSketch.Main")

# Import custom modular services from services package
try:
    from services import (
        CheckpointManager,
        optimize_conformer_3d,
        write_all_conformers,
        query_ollama_for_pymol,
        execute_pymol_commands,
        get_pymol_process,
        find_repurposing_targets,
        MDRepoPredictor,
        get_one_hot_nodes
    )
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
    from flask import Flask, jsonify
except ImportError:
    logger.error("Taipy GUI framework not available!")
    Gui = None
    Html = None
    State = None
    Flask = None
    jsonify = None

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
checkpoint_logs_html = "<div class='checkpoint-log-line'><span class='checkpoint-time'>[READY]</span> Workspace ready for analysis.</div>"


def log_checkpoint_to_ui(state: State, message: str, level: str = "success") -> None:
    """
    Appends a formatted log boundary line to the checkpoint GUI viewport.
    
    Args:
        state: Taipy GUI state object
        message: Log message to display
        level: Log level - 'success', 'warning', 'error', or 'info'
    """
    time_str = datetime.now().strftime("%H:%M:%S")
    color_class = "checkpoint-success"
    if level == "warning":
        color_class = "checkpoint-warning"
    elif level == "error":
        color_class = "checkpoint-error"
    elif level == "info":
        color_class = "checkpoint-time"
    
    # Sanitize message to prevent HTML injection
    safe_message = html_module.escape(message)
    line_html = f"<div class='checkpoint-log-line'><span class='checkpoint-time'>[{time_str}]</span> <span class='{color_class}'>{safe_message}</span></div>"
    state.checkpoint_logs_html += line_html


def run_molecular_pipeline(state: State, mol: "Chem.Mol") -> None:
    """
    Coordinates conformational optimization and deep learning predictions.
    
    Orchestrates the full pipeline: 3D embedding → MMFF94 minimization →
    file export → PyTorch inference → table rendering.
    
    Args:
        state: Taipy GUI state object
        mol: RDKit Mol object to process
    
    Returns:
        None (updates state variables instead)
    """
    global checkpoint_manager
    if mol is None:
        return

    try:
        smiles = Chem.MolToSmiles(mol)
    except Exception as e:
        logger.error(f"Failed to generate SMILES: {e}")
        log_checkpoint_to_ui(state, "Error: Invalid molecular structure", "error")
        return
    
    logger.info(f"Initiating modular dynamics pipeline for SMILES: {smiles}")

    state.predictions_html = "<div style='color: var(--text-secondary); font-size: 0.95rem;'>Running structural dynamics optimization pipeline...</div>"

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
                if mol_h is None or mol_h.GetNumAtoms() == 0:
                    log_checkpoint_to_ui(state, "Error: Invalid molecule for prediction", "error")
                    return
                
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
        log_checkpoint_to_ui(state, f"Pipeline Error: {str(e)[:100]}", "error")
        state.predictions_html = f"<div style='color: var(--accent-pink); font-size: 0.95rem;'>Pipeline failed. Check logs.</div>"


def render_predictions_table(state: State, mol: "Chem.Mol", predictions: "torch.Tensor") -> None:
    """
    Formats neural network variance coordinates into a dynamic premium HTML table.
    
    Args:
        state: Taipy GUI state object
        mol: RDKit Mol object with conformer
        predictions: PyTorch tensor of shape (N, 2) with variance predictions
    """
    lines: List[str] = []
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
        color_10ns = "var(--success)" if var_10ns < 0.25 else "var(--warning)" if var_10ns < 0.55 else "var(--accent-pink)"
        color_1us = "var(--success)" if var_1us < 0.45 else "var(--warning)" if var_1us < 0.85 else "var(--accent-pink)"

        lines.append("<tr>")
        lines.append(f"<td>#{i+1}</td>")
        lines.append(f"<td><span class='element-dot {color_class}'></span><span class='{color_class}'>{symbol}</span></td>")
        lines.append(f"<td style='color: var(--text-secondary)'>{pos.x:.2f}, {pos.y:.2f}, {pos.z:.2f}</td>")
        lines.append(f"<td style='color: {color_10ns}'><span class='variance-indicator' style='background: {color_10ns}'></span>{var_10ns:.4f}</td>")
        lines.append(f"<td style='color: {color_1us}'><span class='variance-indicator' style='background: {color_1us}'></span>{var_1us:.4f}</td>")
        lines.append("</tr>")

    lines.append("</tbody></table>")
    state.predictions_html = "\n".join(lines)


def render_repurposing_table(state: State, smiles: str) -> None:
    """
    Queries PDB repurposing targets using Morgan-Tanimoto similarity
    and formats them as a premium HTML table inside the GUI.
    
    Args:
        state: Taipy GUI state object
        smiles: SMILES string of the molecule to match
    """
    try:
        targets = find_repurposing_targets(smiles)
    except Exception as e:
        logger.error(f"Error querying PDB repurposing targets: {e}")
        state.repurposing_html = "<div style='color: var(--text-secondary); font-size: 0.95rem; font-style: italic; text-align: center; padding: 1rem;'>Unable to query PDB targets. Check logs.</div>"
        return
    
    if not targets:
        state.repurposing_html = "<div style='color: var(--text-secondary); font-size: 0.95rem; font-style: italic; text-align: center; padding: 1rem;'>No high-similarity PDB drug targets identified. Sketched molecule represents a novel chemical fragment!</div>"
        return

    lines: List[str] = []
    lines.append("<table class='repurposing-table'>")
    lines.append("<thead><tr><th>Drug Match</th><th>PDB ID</th><th>Protein Target Receptor</th><th>Morgan Sim</th></tr></thead>")
    lines.append("<tbody>")

    # Show top 5 matches
    for t in targets[:5]:
        sim_val = t.get("similarity", 0.0)
        sim_percent = sim_val * 100
        
        # Color threshold for similarity
        sim_color = "var(--success)" if sim_val > 0.6 else "var(--text-secondary)" if sim_val > 0.3 else "var(--text-secondary)"
        
        # Progress gauge HTML structure
        bar_gauge = (
            f"<div style='display: flex; align-items: center; gap: 8px; justify-content: flex-end;'>"
            f"<div style='background: rgba(255,255,255,0.06); border-radius: 4px; height: 6px; width: 60px; overflow: hidden;'>"
            f"<div style='background: {sim_color}; height: 100%; width: {sim_percent:.0f}%;'></div>"
            f"</div>"
            f"<span style='color: {sim_color}; font-weight: 600; font-size: 0.8rem; min-width: 38px; text-align: right;'>{sim_percent:.0f}%</span>"
            f"</div>"
        )

        # Sanitize text fields
        drug_name = html_module.escape(t.get("matched_drug", "Unknown"))
        pdb_id = html_module.escape(t.get("pdb_id", "N/A"))
        target_name = html_module.escape(t.get("target_name", "Unknown"))

        lines.append("<tr>")
        lines.append(f"<td style='color: var(--text-primary); font-weight: 600;'>{drug_name}</td>")
        lines.append(f"<td><span class='badge' style='background: rgba(188,140,255,0.15); border: 1px solid rgba(188,140,255,0.3); color: #fff; padding: 2px 6px; font-size: 0.72rem; border-radius: 4px;'>{pdb_id}</span></td>")
        lines.append(f"<td style='color: var(--text-secondary); font-size: 0.8rem;' title='{target_name}'>{target_name}</td>")
        lines.append(f"<td>{bar_gauge}</td>")
        lines.append("</tr>")

    lines.append("</tbody></table>")
    state.repurposing_html = "\n".join(lines)


# =====================================================================
# TAIPY STATE REACTIVE BINDINGS (MODULE 1 BRIDGE)
# =====================================================================
def on_chat_send(state: State) -> None:
    """
    Processes chat prompt through visualizer service connection APIs.
    
    Translates user visualization requests to PyMOL commands via Ollama
    (with fallback to local mapper) and pipes to running PyMOL process.
    
    Args:
        state: Taipy GUI state object
    """
    prompt = state.chat_prompt
    if not prompt or not prompt.strip():
        return

    # Sanitize and cap prompt length
    prompt = prompt.strip()[:2000]
    
    # Append user bubble (sanitized)
    safe_prompt = html_module.escape(prompt)
    user_bubble = f"<div class='chat-message message-user'>{safe_prompt}</div>"
    state.chat_log_html += user_bubble

    try:
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

        # Format system bubble response (sanitized)
        sys_bubble = f"<div class='chat-message message-system'>"
        if exec_success:
            sys_bubble += "Visualization request sent to PyMOL."
        else:
            sys_bubble += "PyMOL is offline. The request was interpreted and kept in the server log."
        logger.info("Generated PyMOL command sequence: %s", commands_text)
        sys_bubble += "</div>"
        state.chat_log_html += sys_bubble
    
    except Exception as e:
        logger.error(f"Error in chat handler: {e}")
        sys_bubble = f"<div class='chat-message message-system' style='color: var(--accent-pink);'>Error processing request. Check logs.</div>"
        state.chat_log_html += sys_bubble

    # Clear prompt input
    state.chat_prompt = ""


def on_change(state: State, var_name: str, var_value: Any) -> None:
    """
    Central reactive event listener bridging sketch vectors and pasted SMILES inputs.
    
    Handles two primary reactions:
    1. canvas_payload: RDKit mol reconstruction → pipeline execution
    2. smiles_input: SMILES parsing → 2D layout → pipeline execution
    
    Args:
        state: Taipy GUI state object
        var_name: Name of the variable that changed
        var_value: New value of the variable
    """
    if var_name == "canvas_payload":
        try:
            payload = json.loads(var_value)
            atoms = payload.get("atoms", [])
            bonds = payload.get("bonds", [])
            
            # Validate molecule size (max 200 atoms for performance)
            if len(atoms) > 200:
                log_checkpoint_to_ui(state, "Error: Molecule too large (max 200 atoms)", "error")
                return
            
            if not atoms:
                state.smiles_input = ""
                state.predictions_html = "<div style='color: var(--text-secondary); font-size: 0.95rem; font-style: italic;'>Draw a molecule or enter a SMILES to trigger optimization and predictions.</div>"
                state.repurposing_html = "<div style='color: var(--text-secondary); font-size: 0.95rem; font-style: italic;'>Sketched drug target repurposing matches will populate here.</div>"
                return

            # Reconstruct RDKit RWmol from canvas coordinates and bonds
            rw_mol = Chem.RWMol()
            atom_map = {}
            
            for atom_data in atoms:
                el = atom_data.get("element", "C")
                try:
                    rd_atom = Chem.Atom(el)
                    rd_idx = rw_mol.AddAtom(rd_atom)
                    atom_map[atom_data["id"]] = rd_idx
                except Exception as e:
                    logger.warning(f"Invalid element {el}: {e}")
                    continue

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
                    try:
                        rw_mol.AddBond(
                            atom_map[src], 
                            atom_map[tgt], 
                            bond_types.get(b_type, Chem.BondType.SINGLE)
                        )
                    except Exception as e:
                        logger.warning(f"Invalid bond {src}-{tgt}: {e}")
                        continue

            # Sanitize structure
            mol = rw_mol.GetMol()
            try:
                Chem.SanitizeMol(mol)
            except Exception as e:
                log_checkpoint_to_ui(state, "Error: Invalid molecule structure", "error")
                return
            
            smiles = Chem.MolToSmiles(mol)
            state.smiles_input = smiles
            
            # Execute computational dynamics pipeline
            run_molecular_pipeline(state, mol)
            
        except json.JSONDecodeError as e:
            logger.debug(f"Canvas payload JSON parse error: {e}")
        except Exception as e:
            logger.error(f"Canvas payload processing error: {e}")

    elif var_name == "smiles_input":
        # Handle live edits if any, though explicit action is preferred
        pass

def on_smiles_action(state: State) -> None:
    """Explicitly handles SMILES submission from the Render button."""
    try:
        smiles = state.smiles_input.strip()
        if not smiles:
            return

        # Validate SMILES length (max 2000 chars)
        if len(smiles) > 2000:
            log_checkpoint_to_ui(state, "Error: SMILES string too long (max 2000 chars)", "error")
            return

        # Strict sanitization with RDKit
        mol = Chem.MolFromSmiles(smiles, sanitize=True)
        if mol is None:
            log_checkpoint_to_ui(state, f"Invalid SMILES string: '{smiles[:50]}'", "error")
            return

        # Validate molecule size
        if mol.GetNumAtoms() > 200:
            log_checkpoint_to_ui(state, "Error: Molecule too large (max 200 atoms)", "error")
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

        # Set canvas payload to render on frontend
        payload = json.dumps({"atoms": canvas_atoms, "bonds": canvas_bonds})
        state.canvas_payload = payload

        # Execute computational dynamics pipeline
        run_molecular_pipeline(state, mol)
        
    except Exception as e:
        logger.error(f"SMILES action error: {e}")
        log_checkpoint_to_ui(state, f"Error processing SMILES: {e}", "error")

# =====================================================================
# SERVER RUN ENTRYPOINT
# =====================================================================
if __name__ == "__main__":
    logger.info("Starting modular KineticSketch Workspace Server...")
    is_valid, config_errors = config.validate()
    if not is_valid:
        for error in config_errors:
            logger.warning("Configuration warning: %s", error)
    
    if config.PYMOL_ENABLED:
        # Pre-spawn PyMOL pipeline dynamically when configured.
        get_pymol_process()
    
    # Load frontend index template relatively using dynamic path resolution
    html_path = os.path.join(current_dir, "gui", "index.html")
    html_page = Html(html_path)

    flask_app = Flask(__name__) if Flask is not None else None

    if flask_app is not None:
        @flask_app.get("/health")
        def health():
            return jsonify({
                "status": "healthy",
                "environment": config.ENVIRONMENT,
                "services": {
                    "rdkit": "available" if Chem is not None else "unavailable",
                    "torch": "available" if torch is not None else "unavailable",
                    "pymol": "enabled" if config.PYMOL_ENABLED else "disabled",
                    "ollama": "enabled" if config.OLLAMA_ENABLED else "disabled",
                },
                "timestamp": datetime.utcnow().isoformat() + "Z",
            })
    
    # Run Taipy GUI web server
    gui = Gui(page=html_page, flask=flask_app)
    gui.run(
        title="KineticSketch - Molecular Dynamics Workspace",
        use_reloader=False,
        host=config.HOST,
        port=config.PORT,
        debug=config.DEBUG,
        dark_mode=False
    )
