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
from types import SimpleNamespace
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
    from flask import Flask, jsonify, request
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
smiles_submit_token = ""
last_smiles_submission_key = ""
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


def process_smiles_submission(state: State, smiles: str, submission_key: Optional[str] = None) -> bool:
    """Validate a SMILES string, render it to 2D, and run the analysis pipeline."""
    global last_smiles_submission_key
    smiles = (smiles or "").strip()
    if not smiles:
        return False

    if submission_key and submission_key == last_smiles_submission_key:
        return False

    try:
        # Validate SMILES length (max 2000 chars)
        if len(smiles) > 2000:
            log_checkpoint_to_ui(state, "Error: SMILES string too long (max 2000 chars)", "error")
            return False

        # Strict sanitization with RDKit
        mol = Chem.MolFromSmiles(smiles, sanitize=True)
        if mol is None:
            log_checkpoint_to_ui(state, f"Invalid SMILES string: '{smiles[:50]}'", "error")
            return False

        # Validate molecule size
        if mol.GetNumAtoms() > 200:
            log_checkpoint_to_ui(state, "Error: Molecule too large (max 200 atoms)", "error")
            return False

        # Calculate 2D coordinates layout
        rdDepictor.Compute2DCoords(mol)
        conf = mol.GetConformer()

        # Format canvas rendering coordinate payload — send raw RDKit coords (Angstroms).
        # The JS loadCanvasData handles all fitting/scaling to the canvas viewport.
        canvas_atoms = []
        for i in range(mol.GetNumAtoms()):
            atom = mol.GetAtomWithIdx(i)
            pos = conf.GetAtomPosition(i)
            canvas_atoms.append({
                "id": i + 1,
                "x": round(pos.x, 4),
                "y": round(pos.y, 4),
                "element": atom.GetSymbol()
            })

        canvas_bonds = []
        for bond in mol.GetBonds():
            bt = bond.GetBondType()
            b_type = 1
            if bt == Chem.BondType.DOUBLE:
                b_type = 2
            elif bt == Chem.BondType.TRIPLE:
                b_type = 3

            canvas_bonds.append({
                "source": bond.GetBeginAtomIdx() + 1,
                "target": bond.GetEndAtomIdx() + 1,
                "type": b_type
            })

        # Set canvas payload to render on frontend
        payload = json.dumps({"atoms": canvas_atoms, "bonds": canvas_bonds})
        state.canvas_payload = payload

        # Execute computational dynamics pipeline
        if submission_key:
            last_smiles_submission_key = submission_key
        run_molecular_pipeline(state, mol)
        return True
    except Exception as e:
        logger.error(f"SMILES submission error: {e}")
        log_checkpoint_to_ui(state, f"Error processing SMILES: {e}", "error")
        return False


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
        # Keep the submitted SMILES in state; the explicit submit token triggers processing.
        pass

    elif var_name == "smiles_submit_token":
        process_smiles_submission(state, state.smiles_input, str(var_value))


def build_smiles_response(state: Any, smiles: str) -> Dict[str, Any]:
    """Run the SMILES pipeline on a lightweight state object and return serializable output."""
    response_state = state
    if response_state is None:
        response_state = SimpleNamespace(
            smiles_input="",
            canvas_payload="{}",
            predictions_html=predictions_html,
            repurposing_html=repurposing_html,
            checkpoint_logs_html=checkpoint_logs_html,
        )

    success = process_smiles_submission(
        response_state,
        smiles,
        f"api:{smiles}:{datetime.utcnow().isoformat()}",
    )
    canvas_payload_obj = {}
    try:
        canvas_payload_obj = json.loads(getattr(response_state, "canvas_payload", "{}") or "{}")
    except Exception:
        canvas_payload_obj = {}

    return {
        "ok": success,
        "smiles": smiles,
        "canvas_payload": canvas_payload_obj,
        "predictions_html": getattr(response_state, "predictions_html", predictions_html),
        "repurposing_html": getattr(response_state, "repurposing_html", repurposing_html),
        "checkpoint_logs_html": getattr(response_state, "checkpoint_logs_html", checkpoint_logs_html),
    }

# =====================================================================
# SERVER RUN ENTRYPOINT
# =====================================================================
# Pure Flask app — serves our index.html directly without Taipy's React shell
from flask import Flask, jsonify, request, send_from_directory
flask_app = Flask(__name__, static_folder=os.path.join(current_dir, "static"))

gui_dir = os.path.join(current_dir, "gui")

# Serve index.html at root
@flask_app.get("/")
def index():
    return send_from_directory(gui_dir, "index.html")

# Serve any file from gui/ directory (CSS, fonts, etc.)
@flask_app.get("/gui/<path:filename>")
def gui_file(filename):
    return send_from_directory(gui_dir, filename)

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

@flask_app.post("/api/analyze_smiles")
def analyze_smiles():
    payload = request.get_json(silent=True) or {}
    smiles = str(payload.get("smiles", "")).strip()
    if not smiles:
        return jsonify({"ok": False, "error": "SMILES is required."}), 400
    response = build_smiles_response(None, smiles)
    status_code = 200 if response.get("ok") else 422
    return jsonify(response), status_code

@flask_app.post("/api/chat")
def chat():
    payload = request.get_json(silent=True) or {}
    prompt = str(payload.get("prompt", "")).strip()
    if not prompt:
        return jsonify({"ok": False, "error": "Prompt is required."}), 400
    try:
        cmd, source = query_ollama_for_pymol(prompt)
        result = execute_pymol_commands([cmd]) if cmd else "No command generated."
        return jsonify({"ok": True, "command": cmd, "result": result, "source": source})
    except Exception as e:
        logger.error(f"Chat API error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

@flask_app.post("/api/optimize_2d")
def optimize_2d():
    from app.services import canvas_json_to_2d_optimized
    payload = request.get_json(silent=True) or {}
    try:
        res = canvas_json_to_2d_optimized(payload)
        return jsonify({"ok": True, "canvas_payload": res})
    except Exception as e:
        logger.error(f"Optimize 2D error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 422

@flask_app.post("/api/canvas_to_smiles")
def canvas_to_smiles():
    from app.services import canvas_json_to_smiles
    payload = request.get_json(silent=True) or {}
    try:
        smiles = canvas_json_to_smiles(payload)
        if not smiles:
            return jsonify({"ok": False, "error": "Invalid structure"}), 400
        return jsonify({"ok": True, "smiles": smiles})
    except Exception as e:
        logger.error(f"Canvas to SMILES error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 422

@flask_app.post("/api/descriptors")
def descriptors():
    from app.services import smiles_to_rdkit_mol, calculate_adme_descriptors
    payload = request.get_json(silent=True) or {}
    smiles = str(payload.get("smiles", "")).strip()
    if not smiles:
        return jsonify({"ok": False, "error": "SMILES is required"}), 400
    try:
        mol = smiles_to_rdkit_mol(smiles)
        if mol is None:
            return jsonify({"ok": False, "error": f"Invalid SMILES: {smiles}"}), 400
        desc = calculate_adme_descriptors(mol)
        return jsonify(desc)
    except Exception as e:
        logger.error(f"Descriptors error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

@flask_app.post("/api/pdb/upload")
def pdb_upload():
    from app.services import parse_pdb_structure, get_ligands_in_structure
    import tempfile
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "No file uploaded"}), 400
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"ok": False, "error": "No file selected"}), 400
        
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdb", delete=False) as tmp:
            file.save(tmp.name)
            tmp_path = tmp.name
            
        struct = parse_pdb_structure(tmp_path)
        ligands = get_ligands_in_structure(struct)
        os.remove(tmp_path)
        
        return jsonify({
            "ok": True,
            "filename": file.filename,
            "ligands": [{"resname": name, "chain": chain, "seq": seq} for name, chain, seq in ligands]
        })
    except Exception as e:
        logger.error(f"PDB upload error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

@flask_app.get("/api/pdb/fetch")
def pdb_fetch():
    from app.services import fetch_pdb_file, parse_pdb_structure, get_ligands_in_structure
    pdb_id = request.args.get("pdb_id", "").strip().upper()
    if not pdb_id or len(pdb_id) != 4 or not pdb_id.isalnum():
        return jsonify({"ok": False, "error": "Valid 4-character PDB ID is required."}), 400
        
    try:
        filepath = fetch_pdb_file(pdb_id)
        struct = parse_pdb_structure(filepath)
        ligands = get_ligands_in_structure(struct)
        return jsonify({
            "ok": True,
            "pdb_id": pdb_id,
            "ligands": [{"resname": name, "chain": chain, "seq": seq} for name, chain, seq in ligands]
        })
    except Exception as e:
        logger.error(f"PDB fetch error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

@flask_app.post("/api/interactions")
def interactions():
    from app.services import (
        fetch_pdb_file, 
        parse_pdb_structure, 
        extract_pocket_residues, 
        detect_interactions,
        smiles_to_rdkit_mol,
        generate_2d_coords
    )
    payload = request.get_json(silent=True) or {}
    smiles = str(payload.get("smiles", "")).strip()
    pdb_id = str(payload.get("pdb_id", "")).strip().upper()
    ligand_resname = str(payload.get("ligand_resname", "")).strip().upper()
    ligand_chain = payload.get("ligand_chain")
    ligand_seq = payload.get("ligand_seq")
    if ligand_seq is not None:
        try:
            ligand_seq = int(ligand_seq)
        except ValueError:
            ligand_seq = None
            
    if not smiles or not pdb_id or not ligand_resname:
        return jsonify({"ok": False, "error": "SMILES, pdb_id, and ligand_resname are required."}), 400
        
    try:
        filepath = fetch_pdb_file(pdb_id)
        struct = parse_pdb_structure(filepath)
        
        # Extract pocket around ligand
        ligand_atoms, pocket_residues = extract_pocket_residues(
            struct, ligand_resname, ligand_chain, ligand_seq
        )
        
        # Detect interactions
        profile = detect_interactions(ligand_atoms, pocket_residues)
        
        # Generate 2D coordinates for the ligand smiles to layout the diagram
        mol = smiles_to_rdkit_mol(smiles)
        if mol:
            mol = generate_2d_coords(mol)
            conf = mol.GetConformer(0)
            coords = []
            for i, atom in enumerate(mol.GetAtoms()):
                pos = conf.GetAtomPosition(i)
                coords.append({
                    "id": i + 1,
                    "x": round(pos.x, 4),
                    "y": round(pos.y, 4),
                    "element": atom.GetSymbol()
                })
            bonds = []
            for bond in mol.GetBonds():
                bt = bond.GetBondType()
                b_type = 1
                if bt == Chem.BondType.DOUBLE: b_type = 2
                elif bt == Chem.BondType.TRIPLE: b_type = 3
                bonds.append({
                    "source": bond.GetBeginAtomIdx() + 1,
                    "target": bond.GetEndAtomIdx() + 1,
                    "type": b_type
                })
                
            # Format interactions for front-end diagram
            serializable_profile = []
            for item in profile:
                serializable_profile.append({
                    "type": item["type"],
                    "ligand_atom": {
                        "name": item["ligand_atom"]["name"],
                        "element": item["ligand_atom"]["element"],
                        "coord": item["ligand_atom"]["coord"]
                    },
                    "residue": item["residue"],
                    "protein_atom": {
                        "name": item["protein_atom"]["name"],
                        "element": item["protein_atom"]["element"],
                        "coord": item["protein_atom"]["coord"]
                    },
                    "distance_angstrom": item["distance_angstrom"],
                    "angle_deg": item.get("angle_deg")
                })
            
            ligand_2d = {"atoms": coords, "bonds": bonds}
        else:
            ligand_2d = None
            serializable_profile = []
            
        return jsonify({
            "ok": True,
            "interactions": serializable_profile,
            "ligand_2d_coords": ligand_2d
        })
    except Exception as e:
        logger.error(f"Interactions profiling error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

@flask_app.post("/api/mcs_align")
def mcs_align():
    from rdkit.Chem import rdFMCS
    from app.services import smiles_to_rdkit_mol
    payload = request.get_json(silent=True) or {}
    smiles_list = payload.get("smiles_list", [])
    if not smiles_list or len(smiles_list) < 2:
        return jsonify({"ok": False, "error": "At least 2 SMILES are required for alignment."}), 400
        
    try:
        mols = []
        for s in smiles_list:
            mol = smiles_to_rdkit_mol(s)
            if mol is None:
                return jsonify({"ok": False, "error": f"Invalid SMILES in list: {s}"}), 400
            mols.append(mol)
            
        from rdkit.Chem import rdDepictor
        for mol in mols:
            rdDepictor.Compute2DCoords(mol)
            
        res = rdFMCS.FindMCS(mols)
        if res.numAtoms == 0:
            aligned_coords = []
            for mol in mols:
                conf = mol.GetConformer(0)
                atoms = [{"id": i+1, "x": conf.GetAtomPosition(i).x, "y": conf.GetAtomPosition(i).y, "element": mol.GetAtomWithIdx(i).GetSymbol()} for i in range(mol.GetNumAtoms())]
                bonds = [{"source": b.GetBeginAtomIdx()+1, "target": b.GetEndAtomIdx()+1, "type": 1 if b.GetBondType() == Chem.BondType.SINGLE else 2} for b in mol.GetBonds()]
                aligned_coords.append({"atoms": atoms, "bonds": bonds})
            return jsonify({"ok": True, "aligned": aligned_coords})
            
        mcs_query = Chem.MolFromSmarts(res.smartsString)
        ref_mol = mols[0]
        ref_match = ref_mol.GetSubstructMatch(mcs_query)
        
        aligned_coords = []
        for i, mol in enumerate(mols):
            conf = mol.GetConformer(0)
            if i > 0:
                match = mol.GetSubstructMatch(mcs_query)
                if match and ref_match:
                    try:
                        rdDepictor.GenerateDepictionMatching2DStructure(mol, ref_mol, acceptFailure=True)
                        conf = mol.GetConformer(0)
                    except Exception as align_err:
                        logger.warning(f"Matching 2D alignment failed: {align_err}")
                        
            atoms = [{"id": j+1, "x": conf.GetAtomPosition(j).x, "y": conf.GetAtomPosition(j).y, "element": mol.GetAtomWithIdx(j).GetSymbol()} for j in range(mol.GetNumAtoms())]
            bonds = []
            for b in mol.GetBonds():
                bt = b.GetBondType()
                b_type = 1
                if bt == Chem.BondType.DOUBLE: b_type = 2
                elif bt == Chem.BondType.TRIPLE: b_type = 3
                bonds.append({
                    "source": b.GetBeginAtomIdx() + 1,
                    "target": b.GetEndAtomIdx() + 1,
                    "type": b_type
                })
            aligned_coords.append({"atoms": atoms, "bonds": bonds})
            
        return jsonify({"ok": True, "aligned": aligned_coords})
    except Exception as e:
        logger.error(f"MCS align error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

@flask_app.post("/api/tasks/submit")
def tasks_submit():
    from app.tasks.task_schemas import TaskSubmitSchema
    from marshmallow import ValidationError
    
    payload = request.get_json(silent=True) or {}
    schema = TaskSubmitSchema()
    try:
        validated_data = schema.load(payload)
        schema.validate_params(validated_data)
    except ValidationError as err:
        return jsonify({"ok": False, "error": err.messages}), 400
        
    task_type = validated_data["task_type"]
    params = validated_data["params"]
    
    task_id = None
    estimated_time = "~30s"
    
    try:
        if task_type == "optimize_3d":
            from app.tasks import run_3d_optimization_task
            result = run_3d_optimization_task.delay(
                smiles=params["smiles"]
            )
            task_id = result.id
            estimated_time = "~10s"
            
        elif task_type == "interaction_profile":
            from app.tasks import run_interaction_profiling_task
            result = run_interaction_profiling_task.delay(
                smiles=params["smiles"],
                pdb_id=params["pdb_id"],
                ligand_resname=params["ligand_resname"],
                ligand_chain=params.get("ligand_chain"),
                ligand_seq=params.get("ligand_seq")
            )
            task_id = result.id
            estimated_time = "~15s"
            
        elif task_type == "md_simulation":
            from app.tasks import run_openmm_md_task
            structure_path = params.get("sdf_path")
            if not structure_path and params.get("smiles"):
                structure_path = "molecule.sdf"
            elif not structure_path:
                structure_path = "molecule.sdf"
                
            result = run_openmm_md_task.delay(
                structure_path=structure_path,
                n_steps=params["n_steps"]
            )
            task_id = result.id
            estimated_time = "~1m"
            
        return jsonify({
            "ok": True,
            "task_id": task_id,
            "estimated_time": estimated_time
        })
    except Exception as e:
        logger.error(f"Task submission error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

@flask_app.get("/api/tasks/status/<task_id>")
def tasks_status(task_id):
    from celery.result import AsyncResult
    from app.tasks import celery_app
    
    try:
        res = AsyncResult(task_id, app=celery_app)
        state = res.state
        
        response_data = {
            "task_id": task_id,
            "status": state,
            "result": None,
            "error": None
        }
        
        if state == "SUCCESS":
            response_data["result"] = res.result
        elif state == "FAILURE":
            response_data["error"] = str(res.result)
        elif state == "PROGRESS":
            meta = res.info or {}
            response_data["percent"] = meta.get("percent", 0)
            response_data["message"] = meta.get("message", "Processing...")
            
        return jsonify(response_data)
    except Exception as e:
        logger.error(f"Task status retrieval error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

@flask_app.delete("/api/tasks/cancel/<task_id>")
def tasks_cancel(task_id):
    from celery.result import AsyncResult
    from app.tasks import celery_app
    
    try:
        res = AsyncResult(task_id, app=celery_app)
        res.revoke(terminate=True)
        return jsonify({"ok": True, "message": f"Task {task_id} successfully revoked."})
    except Exception as e:
        logger.error(f"Task cancel error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

if __name__ == "__main__":
    logger.info("Starting modular KineticSketch Workspace Server...")
    is_valid, config_errors = config.validate()
    if not is_valid:
        for error in config_errors:
            logger.warning("Configuration warning: %s", error)
    
    if config.PYMOL_ENABLED:
        get_pymol_process()
        
    logger.info(f" * Server starting on http://{config.HOST}:{config.PORT}")

    flask_app.run(
        host=config.HOST,
        port=config.PORT,
        debug=config.DEBUG,
        use_reloader=False,
    )

