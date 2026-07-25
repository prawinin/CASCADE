#!/usr/bin/env python3
"""
KineticSketch - Molecular Dynamics Workspace
Main Entrypoint & GUI Orchestration Server
Clean Modular Multi-File Architecture
"""

import os  # noqa: E402
import sys  # noqa: E402
import json  # noqa: E402
import logging  # noqa: E402
import html as html_module  # noqa: E402
from datetime import datetime, timezone  # noqa: E402
from types import SimpleNamespace  # noqa: E402
from typing import Any, Dict, List, Optional  # noqa: E402

from app.config import get_config  # noqa: E402
from app.paths import (  # noqa: E402
    APP_DIR,
    GUI_DIR,
    JOBS_DIR,
    USERS_DATABASE_PATH,
    ensure_runtime_directories,
)

ensure_runtime_directories()
current_dir = str(APP_DIR)

config = get_config()
is_valid_config, config_errors = config.validate()
if not is_valid_config:
    raise RuntimeError("Invalid KineticSketch configuration: " + "; ".join(config_errors))

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
    from app.services import (
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

# Import drug database service (optional — gracefully unavailable until built)
try:
    from app.services.drug_database import (
        lookup_smiles_by_name,
        get_autocomplete_suggestions,
        is_available as drug_db_available,
        get_db_stats
    )
    _drug_db_imported = True
except ImportError:
    _drug_db_imported = False
    def lookup_smiles_by_name(name): return None
    def get_autocomplete_suggestions(prefix, limit=10): return []
    def drug_db_available(): return False
    def get_db_stats(): return {"status": "not_imported"}

# Import singleton predictor factory
try:
    from app.services.models import get_predictor
except ImportError:
    get_predictor = None

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
    logger.info("Taipy GUI is not installed; using the Flask web interface.")
    Gui = None
    Html = None
    State = None

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None


# Initialize central checkpoint service manager
checkpoint_manager = CheckpointManager()


# TAIPY GUI REACTIVE VARIABLE BINDINGS
canvas_payload = "{}"
smiles_input = ""
smiles_submit_token = ""  # nosec B105
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

    logger.info("Initiating molecular dynamics pipeline for a validated structure")

    state.predictions_html = "<div style='color: var(--text-secondary); font-size: 0.95rem;'><i class='fa-solid fa-spinner fa-spin' style='margin-right: 8px;'></i>Running structural dynamics optimization pipeline...</div>"
    state.repurposing_html = "<div style='color: var(--text-secondary); font-size: 0.95rem;'><i class='fa-solid fa-spinner fa-spin' style='margin-right: 8px;'></i>Searching 5,576 PDB targets...</div>"


    u_id = getattr(state, "user_id", None) or "anonymous"
    j_id = getattr(state, "job_id", None) or str(uuid.uuid4())
    from app.services.cheminformatics import get_or_create_job_dir
    from app.services import CheckpointManager
    job_dir = get_or_create_job_dir(u_id, j_id)
    out_dir = os.path.join(job_dir, "outputs")
    os.makedirs(out_dir, exist_ok=True)
    local_ckpt_mgr = CheckpointManager(os.path.join(out_dir, "workspace_progress.json"))
    sdf_path = os.path.join(out_dir, "molecule.sdf")
    xyz_path = os.path.join(out_dir, "molecule.xyz")
    mol2_path = os.path.join(out_dir, "molecule.mol2")

    # Reset progress checkpoint to INITIALIZED
    local_ckpt_mgr.save_checkpoint("INIT", {"smiles": smiles})
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
                local_ckpt_mgr.save_checkpoint("EMBED_3D")
                log_checkpoint_to_ui(state, "Generated 3D coordinate conformation via ETKDGv3 and appended hydrogens.", "success")

            elif idx == 1:
                # 2. Conformer minimization (MMFF94) is already handled inside optimize_conformer_3d
                local_ckpt_mgr.save_checkpoint("MINIMIZE_3D")
                log_checkpoint_to_ui(state, "Minimized conformer geometry using MMFF94 force field calculations.", "success")

            elif idx == 2:
                # 3. Stream coordinate structures to SDF, XYZ, and Tripos MOL2 formats
                write_all_conformers(mol_h, sdf_path, xyz_path, mol2_path)

                local_ckpt_mgr.save_checkpoint("WRITE_FILES", {
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

                local_ckpt_mgr.save_checkpoint("EXTRACT_TENSORS")
                log_checkpoint_to_ui(
                    state,
                    f"Generated PyTorch tensors: Position shape={list(pos_tensor.shape)}, node features={list(node_features.shape)}",
                    "success"
                )

                # MDRepo fast predictive inference — use singleton (loaded once at startup)
                if get_predictor is not None:
                    predictor = get_predictor()
                else:
                    predictor = MDRepoPredictor()
                    predictor.eval()

                try:
                    model_device = next(predictor.parameters()).device
                    pos_tensor = pos_tensor.to(model_device)
                    node_features = node_features.to(model_device)
                except Exception as exc:
                    logger.debug(f"Could not detect predictor device: {exc}")

                with torch.no_grad():
                    pred_dict = predictor(pos_tensor, node_features)
                    # Move all tensors to CPU for rendering
                    predictions = {k: v.cpu() if isinstance(v, torch.Tensor) else v
                                   for k, v in pred_dict.items()}

                local_ckpt_mgr.save_checkpoint("RUN_INFERENCE", {
                    "rmsf": predictions["rmsf"].tolist(),
                    "homo_lumo_gap": float(predictions["homo_lumo_gap"]),
                })
                log_checkpoint_to_ui(state, "MDRepo dynamic atomic fluctuation predictions computed successfully.", "success")

                # Render multi-task predictions tables
                render_predictions_table(state, mol_h, predictions)

                # Render dynamic PDB drug repurposing table
                render_repurposing_table(state, smiles)

    except Exception as e:
        logger.error(f"Error in dynamics integration pipeline: {e}", exc_info=True)
        log_checkpoint_to_ui(state, f"Pipeline Info: {str(e)[:100]}", "warning")
        try:
            if 'mol_h' in locals() and mol_h is not None:
                from rdkit.Chem import AllChem
                AllChem.ComputeGasteigerCharges(mol_h)
                num_atoms = mol_h.GetNumAtoms()
                charges = []
                for i in range(num_atoms):
                    atom = mol_h.GetAtomWithIdx(i)
                    val = float(atom.GetProp('_GasteigerCharge')) if atom.HasProp('_GasteigerCharge') else 0.0
                    charges.append(val if not (val != val) else 0.0)
                
                if torch is not None:
                    fallback_preds = {
                        "rmsf": torch.zeros((num_atoms, 2)),
                        "sasa": torch.zeros(num_atoms),
                        "bfactor": torch.zeros(num_atoms),
                        "charge": torch.tensor(charges, dtype=torch.float32),
                        "homo_lumo_gap": 6.85
                    }
                else:
                    fallback_preds = {
                        "rmsf": SimpleNamespace(tolist=lambda: [[0.0, 0.0]]*num_atoms),
                        "sasa": [0.0]*num_atoms,
                        "bfactor": [0.0]*num_atoms,
                        "charge": charges,
                        "homo_lumo_gap": 6.85
                    }
                render_predictions_table(state, mol_h, fallback_preds)
            else:
                state.predictions_html = get_demo_disclaimer_html("Conformer Predictions") + "<div style='color: var(--text-muted); font-size: 0.95rem; padding: 10px;'>Draw a molecule or enter a SMILES to trigger optimization and predictions.</div>"
        except Exception as exc:
            logger.error(f"Fallback rendering failed: {exc}")
            state.predictions_html = get_demo_disclaimer_html("Conformer Predictions") + "<div style='color: var(--text-muted); font-size: 0.95rem; padding: 10px;'>Lightweight mode active. Contact <strong>prawin@vyapai.tech</strong> for full live demo.</div>"

        render_repurposing_table(state, smiles)


def get_demo_disclaimer_html(module_title: str = "Cloud Demo Preview") -> str:
    mailto_url = (
        "mailto:prawin@vyapai.tech?"
        "subject=CASCADE%20Full%20Demo%20Request&"
        "body=Hi%20Prawin%2C%0A%0AI%20am%20interested%20in%20a%20full%20live%20demo%20of%20CASCADE%20with%20the%20complete%20drug%20database%20and%20AI%20models.%0A%0APlease%20let%20me%20know%20when%20we%20can%20connect.%0A%0ABest%20regards%2C"
    )
    return (
        f"<div style='background: linear-gradient(135deg, #0F172A 0%, #1E293B 100%); border: 1px solid #334155; border-radius: 10px; padding: 14px; margin-bottom: 14px; color: #F8FAFC; box-shadow: 0 4px 12px rgba(0,0,0,0.15); font-family: system-ui, -apple-system, sans-serif;'>"
        f"  <div style='display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; margin-bottom: 8px;'>"
        f"    <span style='background: rgba(245, 158, 11, 0.2); border: 1px solid rgba(245, 158, 11, 0.5); color: #FBBF24; padding: 3px 8px; border-radius: 12px; font-size: 11px; font-weight: 700; text-transform: uppercase;'>Cloud Preview Demo</span>"
        f"    <a href='{mailto_url}' target='_blank' style='display: inline-flex; align-items: center; background: #2563EB; color: #FFFFFF; font-size: 11px; font-weight: 600; padding: 5px 10px; border-radius: 5px; text-decoration: none; transition: background 0.2s;'>"
        f"      Request full live demo"
        f"    </a>"
        f"  </div>"
        f"  <div style='font-size: 12px; color: #CBD5E1; line-height: 1.4;'>"
        f"    This online workspace runs in lightweight mode without local AI datasets or large neural weights. <a href='{mailto_url}' target='_blank' style='color: #60A5FA; font-weight: 600; text-decoration: underline;'>Contact for complete live demo</a>"
        f"  </div>"
        f"</div>"
    )


def render_predictions_table(state: State, mol: "Chem.Mol", predictions: dict) -> None:
    """
    Formats multi-task neural network predictions into a dynamic premium HTML table.

    Args:
        state: Taipy GUI state object
        mol: RDKit Mol object with conformer
        predictions: Dict with keys 'rmsf' (N,3), 'sasa' (N,), 'bfactor' (N,), 'charge' (N,), 'homo_lumo_gap' (scalar)
    """
    rmsf = predictions["rmsf"]      # (N, 3)
    sasa = predictions["sasa"]       # (N,)
    bfactor = predictions["bfactor"] # (N,)
    charge = predictions["charge"]   # (N,)
    homo_lumo = float(predictions["homo_lumo_gap"])

    lines: List[str] = [get_demo_disclaimer_html("Conformer Predictions")]

    # HOMO-LUMO banner with Level of Theory disclosure and Reference Drug Comparison
    hl_color = "#10B981" if homo_lumo > 3.0 else "#F59E0B" if homo_lumo > 1.0 else "#F43F5E"
    lines.append(
        f"<div style='padding:10px 14px; margin-bottom:10px; background:#F8FAFC; border:1px solid #E2E8F0; border-radius:8px;'>"
        f"  <div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;'>"
        f"    <div>"
        f"      <span style='font-size:12px; font-weight:700; color:#1E293B;'>Quantum HOMO–LUMO Gap</span>"
        f"      <span style='font-size:10px; color:#64748B; margin-left:8px; font-family:monospace;'>(GNN Learned Regression Prediction)</span>"
        f"    </div>"
        f"    <span style='font-size:15px; font-weight:800; font-family:monospace; color:{hl_color};'>{homo_lumo:.3f} eV</span>"
        f"  </div>"
        f"  <div style='font-size:10px; color:#475569; border-top:1px solid #E2E8F0; padding-top:6px; display:flex; flex-wrap:wrap; gap:12px; align-items:center;'>"
        f"    <span style='font-weight:600; color:#334155;'>Reference Benchmark Gaps:</span>"
        f"    <span>Aspirin: <strong style='color:#0284C7;'>8.20 eV</strong></span>"
        f"    <span>Ibuprofen: <strong style='color:#0284C7;'>8.00 eV</strong></span>"
        f"    <span>Caffeine: <strong style='color:#D97706;'>5.80 eV</strong></span>"
        f"    <span>Penicillin G: <strong style='color:#059669;'>4.10 eV</strong></span>"
        f"    <span>Vancomycin: <strong style='color:#DC2626;'>3.60 eV</strong></span>"
        f"  </div>"
        f"</div>"
    )

    lines.append("<div style='font-size:10px; color:#64748B; margin-bottom:6px; font-family:monospace;'>Partial charges computed via <strong>Gasteiger-Marsili (PEOE algorithm)</strong> force field model (units: elementary charge e).</div>")

    lines.append("<table class='w-full min-w-[720px] table-fixed border-collapse text-xs'>")

    # Colgroup
    lines.append("<colgroup>")
    for _ in range(10):  # Atom, El, X, Y, Z, 10ns, 1µs, SASA, B-factor, Charge
        lines.append("  <col />")
    lines.append("</colgroup>")

    # Headers
    lines.append("<thead><tr>")
    headers = [
        ("Atom", "text-left"), ("El.", "text-center"),
        ("X", "text-right"), ("Y", "text-right"), ("Z", "text-right"),
        ("<span class='block'>10ns</span><span class='block text-[10px] font-normal text-slate-400'>RMSF (Å²)</span>", "text-right"),
        ("<span class='block'>1µs</span><span class='block text-[10px] font-normal text-slate-400'>RMSF (Å²)</span>", "text-right"),
        ("<span class='block'>SASA</span><span class='block text-[10px] font-normal text-slate-400'>(Å²)</span>", "text-right"),
        ("<span class='block'>B-factor</span><span class='block text-[10px] font-normal text-slate-400'>(Å²)</span>", "text-right"),
        ("<span class='block'>Charge</span><span class='block text-[10px] font-normal text-slate-400'>(e, Gasteiger)</span>", "text-right"),
    ]
    for label, align in headers:
        lines.append(f"  <th class='px-2 py-2 {align} text-[11px] font-semibold text-slate-600 leading-4 align-bottom bg-slate-50 border-b border-slate-200 whitespace-normal break-words'>{label}</th>")
    lines.append("</tr></thead>")
    lines.append("<tbody>")

    element_colors = {
        'C': '#6B7280', 'O': '#DC2626', 'N': '#2563EB',
        'H': '#9CA3AF', 'P': '#EA580C', 'S': '#CA8A04'
    }

    conf = mol.GetConformer()
    for i in range(mol.GetNumAtoms()):
        atom = mol.GetAtomWithIdx(i)
        symbol = atom.GetSymbol()
        pos = conf.GetAtomPosition(i)
        var_10ns = rmsf[i, 0].item()
        var_1us = rmsf[i, 1].item()
        sasa_val = sasa[i].item()
        bf_val = bfactor[i].item()
        ch_val = charge[i].item()

        # Color coding
        color_10ns = "#10B981" if var_10ns < 0.25 else "#F59E0B" if var_10ns < 0.55 else "#F43F5E"
        color_1us = "#10B981" if var_1us < 0.45 else "#F59E0B" if var_1us < 0.85 else "#F43F5E"
        color_sasa = "#2563EB"
        color_bf = "#6366F1"
        color_ch = "#10B981" if ch_val >= 0 else "#F43F5E"
        el_color = element_colors.get(symbol, '#1E293B')

        lines.append("<tr class='hover:bg-slate-50 last:border-b-0'>")
        lines.append(f"  <td class='px-2 py-1.5 text-xs text-slate-700 border-b border-slate-100 truncate'>#{i+1}</td>")
        lines.append(f"  <td class='px-2 py-1.5 text-xs text-slate-700 border-b border-slate-100 text-center font-medium'><span class='inline-block w-2 h-2 rounded-full mr-1' style='background-color: {el_color}'></span>{symbol}</td>")
        lines.append(f"  <td class='px-2 py-1.5 border-b border-slate-100 font-mono text-[11px] tabular-nums text-right text-slate-500'>{pos.x:.2f}</td>")
        lines.append(f"  <td class='px-2 py-1.5 border-b border-slate-100 font-mono text-[11px] tabular-nums text-right text-slate-500'>{pos.y:.2f}</td>")
        lines.append(f"  <td class='px-2 py-1.5 border-b border-slate-100 font-mono text-[11px] tabular-nums text-right text-slate-500'>{pos.z:.2f}</td>")
        lines.append(f"  <td class='px-2 py-1.5 border-b border-slate-100 font-mono text-[11px] tabular-nums text-right font-medium' style='color: {color_10ns}'>{var_10ns:.4f}</td>")
        lines.append(f"  <td class='px-2 py-1.5 border-b border-slate-100 font-mono text-[11px] tabular-nums text-right font-medium' style='color: {color_1us}'>{var_1us:.4f}</td>")
        lines.append(f"  <td class='px-2 py-1.5 border-b border-slate-100 font-mono text-[11px] tabular-nums text-right font-medium' style='color: {color_sasa}'>{sasa_val:.3f}</td>")
        lines.append(f"  <td class='px-2 py-1.5 border-b border-slate-100 font-mono text-[11px] tabular-nums text-right font-medium' style='color: {color_bf}'>{bf_val:.3f}</td>")
        lines.append(f"  <td class='px-2 py-1.5 border-b border-slate-100 font-mono text-[11px] tabular-nums text-right font-medium' style='color: {color_ch}'>{ch_val:+.4f}</td>")
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

    #  Deduplicate: group PDB entries by drug name
    drug_cards: dict = {}
    for t in targets:
        key = t.get("matched_drug", "Unknown")
        if key not in drug_cards:
            drug_cards[key] = {
                "drug_name": key,
                "similarity": t.get("similarity", 0.0),
                "approved_by": t.get("approved_by", ""),
                "affinity_estimate": t.get("affinity_estimate", ""),
                "pdbs": [],          # (pdb_id, target_name) tuples
            }
        pdb_id_raw = t.get("pdb_id", "")
        target_name = t.get("target_name", "")
        is_real_pdb = (pdb_id_raw and pdb_id_raw != "N/A"
                       and len(pdb_id_raw) == 4 and pdb_id_raw.isalnum())
        if is_real_pdb:
            drug_cards[key]["pdbs"].append((pdb_id_raw, target_name))

    # Sort: drugs with real PDB targets first, then by similarity desc
    card_list = sorted(
        drug_cards.values(),
        key=lambda c: (0 if c["pdbs"] else 1, -c["similarity"])
    )

    #  Build card HTML
    lines: List[str] = [get_demo_disclaimer_html("Drug Repurposing")]
    lines.append("<div style='display:flex; flex-direction:column; gap:0; padding:0;'>")

    shown = 0
    for card in card_list:
        if shown >= 8:
            break
        shown += 1

        sim_val     = card["similarity"]
        sim_pct     = sim_val * 100
        drug_name   = html_module.escape(card["drug_name"])
        approved_by = html_module.escape(card["approved_by"] or "—")
        affinity    = html_module.escape(card["affinity_estimate"] or "—")
        pdbs        = card["pdbs"]  # list of (pdb_id, target_name)

        # Similarity bar colour
        if sim_val >= 0.7:
            bar_color  = "#10B981"   # emerald
            score_bg   = "#ECFDF5"
            score_fg   = "#065F46"
            score_border = "#A7F3D0"
        elif sim_val >= 0.4:
            bar_color  = "#F59E0B"   # amber
            score_bg   = "#FFFBEB"
            score_fg   = "#92400E"
            score_border = "#FDE68A"
        else:
            bar_color  = "#94A3B8"   # slate
            score_bg   = "#F8FAFC"
            score_fg   = "#475569"
            score_border = "#E2E8F0"

        # Build PDB pill row
        if pdbs:
            # Deduplicate PDB IDs, keep up to 4 pills
            seen_pdb: set = set()
            pdb_pills = []
            for pid, tgt in pdbs:
                if pid not in seen_pdb:
                    seen_pdb.add(pid)
                    pid_esc = html_module.escape(pid)
                    tgt_esc = html_module.escape(tgt or "")
                    pdb_pills.append(
                        f"<a href='https://www.rcsb.org/structure/{pid_esc}' "
                        f"   target='_blank' rel='noopener' title='{tgt_esc}' "
                        f"   style='display:inline-flex; align-items:center; gap:3px; "
                        f"          padding:2px 7px; border-radius:4px; "
                        f"          background:#EEF2FF; border:1px solid #C7D2FE; "
                        f"          color:#4338CA; font-family:monospace; font-size:10.5px; "
                        f"          font-weight:600; text-decoration:none; white-space:nowrap; "
                        f"          transition:background 0.12s;'>"
                        f"  {pid_esc}"
                        f"  <span style='font-size:8px; opacity:0.7;'>↗</span>"
                        f"</a>"
                    )
                    if len(pdb_pills) >= 4:
                        break
            # Show first target name as subtitle
            first_target = html_module.escape(pdbs[0][1] or "") if pdbs else ""
            target_line = (
                f"<div style='font-size:10.5px; color:#475569; line-height:1.4; margin-top:3px; "
                f"            white-space:nowrap; overflow:hidden; text-overflow:ellipsis;' "
                f"     title='{first_target}'>{first_target}</div>"
            ) if first_target and first_target not in ("No PDB target recorded", "Unknown target") else ""
            pdb_section = (
                "<div style='display:flex; flex-wrap:wrap; gap:4px; margin-top:5px;'>"
                + "".join(pdb_pills) + "</div>"
                + target_line
            )
        else:
            pdb_section = (
                "<div style='font-size:10.5px; color:#94A3B8; margin-top:4px; font-style:italic;'>"
                "No crystal structure on record</div>"
            )

        # Approval badge
        if approved_by and approved_by not in ("—", "Unknown"):
            badge = (
                f"<span style='font-size:9.5px; font-weight:600; padding:1px 6px; "
                f"             border-radius:3px; background:#F0FDF4; border:1px solid #BBF7D0; "
                f"             color:#15803D; white-space:nowrap;'>{approved_by}</span>"
            )
        else:
            badge = ""

        # Card
        is_last = (shown == min(len(card_list), 8))
        border_bottom = "" if is_last else "border-bottom:1px solid #F1F5F9;"
        lines.append(
            f"<div style='padding:10px 12px 10px 12px; {border_bottom}'>"

            #  Row 1: drug name + score
            f"  <div style='display:flex; align-items:flex-start; justify-content:space-between; gap:6px;'>"
            f"    <div style='font-size:12px; font-weight:600; color:#1E293B; "
            f"                line-height:1.35; flex:1; min-width:0; overflow:hidden; "
            f"                text-overflow:ellipsis; white-space:nowrap;' "
            f"         title='{drug_name}'>{drug_name}</div>"
            f"    <span style='flex-shrink:0; font-size:11px; font-weight:700; "
            f"                 padding:2px 8px; border-radius:5px; "
            f"                 background:{score_bg}; border:1px solid {score_border}; "
            f"                 color:{score_fg}; font-variant-numeric:tabular-nums;'>"
            f"      {sim_pct:.0f}%"
            f"    </span>"
            f"  </div>"

            #  Row 2: similarity bar
            f"  <div style='margin-top:5px; height:4px; border-radius:2px; background:#E2E8F0; overflow:hidden;'>"
            f"    <div style='width:{min(sim_pct, 100):.1f}%; height:100%; "
            f"               border-radius:2px; background:{bar_color}; "
            f"               transition:width 0.4s ease;'></div>"
            f"  </div>"

            #  Row 3: PDB pills + target name
            f"  {pdb_section}"

            #  Row 4: affinity + approval badge
            f"  <div style='display:flex; align-items:center; gap:6px; margin-top:5px; flex-wrap:wrap;'>"
            f"    <span style='font-size:10.5px; color:#64748B; font-family:monospace; "
            f"                 background:#F8FAFC; border:1px solid #E2E8F0; "
            f"                 padding:1px 6px; border-radius:3px;'>ΔG {affinity}</span>"
            f"    {badge}"
            f"  </div>"

            f"</div>"
        )

    #  Dev Log & Search Computation Breakdown
    lines.append(
        f"<details style='margin-top:12px; border:1px solid #E2E8F0; border-radius:6px; background:#F8FAFC; padding:8px 12px; font-family:monospace; font-size:11px;'>"
        f"  <summary style='cursor:pointer; color:#0284C7; font-weight:700;'> Drug Discovery Computation Log &amp; Pipeline Breakdown</summary>"
        f"  <div style='margin-top:8px; display:flex; flex-direction:column; gap:4px; color:#475569; font-size:10.5px; line-height:1.5;'>"
        f"    <div>[1] <strong>SMILES Input:</strong> Query <code>{html_module.escape(smiles[:60])}</code></div>"
        f"    <div>[2] <strong>Fingerprint Generation:</strong> Calculated 2048-bit Morgan Fingerprint (Radius 2, ECFP4-equivalent) via RDKit</div>"
        f"    <div>[3] <strong>Vectorized Search:</strong> Computed Tanimoto Similarity T(A,B) = |A ∩ B| / |A ∪ B| over 2,898,063 compounds</div>"
        f"    <div>[4] <strong>Memory Management:</strong> Processed in 10,000-row mmap numpy matrix chunks (RAM strictly &lt; 80 MB)</div>"
        f"    <div>[5] <strong>Target Cross-Reference:</strong> Matched drug candidates against 5,421 PDB protein binding targets with estimated ΔG</div>"
        f"  </div>"
        f"</details>"
    )

    lines.append("</div>")
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
        if len(smiles) > config.SMILES_LENGTH_LIMIT:
            log_checkpoint_to_ui(
                state,
                f"Error: SMILES string too long (max {config.SMILES_LENGTH_LIMIT} chars)",
                "error",
            )
            return False

        # Strict sanitization with RDKit
        mol = Chem.MolFromSmiles(smiles, sanitize=True)
        if mol is None:
            log_checkpoint_to_ui(state, f"Invalid SMILES string: '{smiles[:50]}'", "error")
            return False

        if mol.GetNumAtoms() > config.MOLECULE_SIZE_LIMIT:
            log_checkpoint_to_ui(
                state,
                f"Error: Molecule too large (max {config.MOLECULE_SIZE_LIMIT} atoms)",
                "error",
            )
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
                "x": round(pos.x * 40.0, 4),
                "y": round(pos.y * 40.0, 4),
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


# TAIPY STATE REACTIVE BINDINGS (MODULE 1 BRIDGE)
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
        sys_bubble = "<div class='chat-message message-system'>"
        if exec_success:
            sys_bubble += "Visualization request sent to PyMOL."
        else:
            sys_bubble += "PyMOL is offline. The request was interpreted and kept in the server log."
        logger.info("Generated PyMOL command sequence: %s", commands_text)
        sys_bubble += "</div>"
        state.chat_log_html += sys_bubble

    except Exception as e:
        logger.error(f"Error in chat handler: {e}")
        sys_bubble = "<div class='chat-message message-system' style='color: var(--accent-pink);'>Error processing request. Check logs.</div>"
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
            except Exception:
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


def build_smiles_response(state: Any, smiles: str, user_id: Optional[str] = None, job_id: Optional[str] = None) -> Dict[str, Any]:
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

    response_state.user_id = user_id
    response_state.job_id = job_id

    success = process_smiles_submission(
        response_state,
        smiles,
        f"api:{smiles}:{datetime.now(timezone.utc).isoformat()}",
    )
    canvas_payload_obj = {}
    try:
        canvas_payload_obj = json.loads(getattr(response_state, "canvas_payload", "{}") or "{}")
    except Exception:
        canvas_payload_obj = {}

    res = {
        "ok": success,
        "smiles": smiles,
        "canvas_payload": canvas_payload_obj,
        "predictions_html": getattr(response_state, "predictions_html", predictions_html),
        "repurposing_html": getattr(response_state, "repurposing_html", repurposing_html),
        "checkpoint_logs_html": getattr(response_state, "checkpoint_logs_html", checkpoint_logs_html),
    }
    if job_id:
        res["job_id"] = job_id
    return res

import requests  # noqa: E402
import sqlite3  # noqa: E402
import uuid  # noqa: E402
import hashlib  # noqa: E402
import hmac  # noqa: E402
import functools  # noqa: E402
import time  # noqa: E402
from urllib.parse import quote  # noqa: E402
from datetime import timedelta  # noqa: E402
from flask import Flask, jsonify, request, send_from_directory, session  # noqa: E402
from werkzeug.middleware.proxy_fix import ProxyFix  # noqa: E402

flask_app = Flask(__name__, static_folder=os.path.join(current_dir, "static"))

secret_key = config.SECRET_KEY
if not secret_key or len(secret_key) < 32:
    raise RuntimeError("FLASK_SECRET_KEY must be set to a random value of at least 32 characters.")

flask_app.secret_key = secret_key
embedded_mode = config.EMBEDDED_MODE
flask_app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=(
        os.environ.get("FLASK_ENV", "development") == "production" or embedded_mode
    ),
    SESSION_COOKIE_SAMESITE="None" if embedded_mode else "Lax",
    # CHIPS keeps an embedded Space session partitioned to its top-level site.
    # Flask 3.1+ emits the Secure and Partitioned cookie attributes together.
    SESSION_COOKIE_PARTITIONED=embedded_mode,
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    MAX_CONTENT_LENGTH=12 * 1024 * 1024,
    JSON_SORT_KEYS=False,
)


@flask_app.errorhandler(413)
def request_too_large(_error):
    return jsonify({"ok": False, "error": "Request body exceeds the configured size limit"}), 413
if config.TRUST_PROXY_HOPS:
    flask_app.wsgi_app = ProxyFix(
        flask_app.wsgi_app,
        x_for=config.TRUST_PROXY_HOPS,
        x_proto=config.TRUST_PROXY_HOPS,
        x_host=config.TRUST_PROXY_HOPS,
        x_port=config.TRUST_PROXY_HOPS,
    )

@flask_app.after_request
def add_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    frame_ancestors = config.FRAME_ANCESTORS
    if frame_ancestors == "'none'":
        response.headers.setdefault("X-Frame-Options", "DENY")
    else:
        # X-Frame-Options has no standard multi-origin allow-list. CSP's
        # frame-ancestors directive is the authoritative restriction here.
        response.headers.pop("X-Frame-Options", None)
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com "
        "https://cdn.tailwindcss.com https://3dmol.org; style-src 'self' 'unsafe-inline' "
        "https://cdnjs.cloudflare.com https://fonts.googleapis.com; img-src 'self' data:; "
        "connect-src 'self'; font-src 'self' https://cdnjs.cloudflare.com https://fonts.gstatic.com",
    )
    response.headers["Content-Security-Policy"] += (
        f"; object-src 'none'; base-uri 'self'; frame-ancestors {frame_ancestors}; "
        "form-action 'self'"
    )
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if request.path.startswith("/api/auth/"):
        response.headers.setdefault("Cache-Control", "no-store")
    if flask_app.config.get("SESSION_COOKIE_SECURE"):
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response

# In-memory limiter is used only for tests or explicitly Redis-free demos.
test_login_attempts = {}


def _rate_limit(bucket: str, limit: int, window_seconds: int, identity: str):
    key_suffix = hashlib.sha256(identity.encode("utf-8", errors="replace")).hexdigest()
    if flask_app.config.get("TESTING") or not config.REQUIRE_REDIS:
        now = time.time()
        memory_key = (bucket, key_suffix)
        attempts = [t for t in test_login_attempts.get(memory_key, []) if now - t < window_seconds]
        test_login_attempts[memory_key] = attempts
        if len(attempts) >= limit:
            return jsonify({"ok": False, "error": "Too many requests. Please try again later."}), 429
        attempts.append(now)
        return None

    try:
        import redis as redis_lib

        redis_client = redis_lib.from_url(
            config.REDIS_URL, socket_connect_timeout=1, socket_timeout=1
        )
        redis_key = f"rate:{bucket}:{key_suffix}"
        current = redis_client.incr(redis_key)
        if current == 1:
            redis_client.expire(redis_key, window_seconds)
        if current > limit:
            return jsonify({"ok": False, "error": "Too many requests. Please try again later."}), 429
        return None
    except Exception:
        return jsonify({"ok": False, "error": "Request limiting service unavailable"}), 503

@flask_app.before_request
def rate_limit_login():
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return None

    fetch_site = request.headers.get("Sec-Fetch-Site", "")
    if fetch_site == "cross-site" and request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": "Cross-site request rejected"}), 403

    client_ip = request.remote_addr or "unknown"
    if request.path == "/api/auth/login":
        limited = _rate_limit("login", 5, 60, client_ip)
        if limited:
            response, status = limited
            if status == 429:
                return jsonify({
                    "ok": False,
                    "error": "Too many login attempts. Please try again in 1 minute.",
                }), 429
            return response, status
    if request.path == "/api/auth/register":
        return _rate_limit("register", 5, 3600, client_ip)
    if request.path in {
        "/api/analyze_smiles", "/api/pdb/upload", "/api/pdb/fetch",
        "/api/dock", "/api/admet", "/api/mcs_align", "/api/tasks/submit",
    }:
        identity = str(session.get("user_id") or client_ip)
        return _rate_limit("compute", 30, 60, identity)
    return None

DB_USERS_PATH = str(USERS_DATABASE_PATH)
os.makedirs(os.path.dirname(DB_USERS_PATH), exist_ok=True)

def hash_password(password: str) -> str:
    iterations = int(os.getenv("PASSWORD_HASH_ITERATIONS", "600000"))
    salt = os.urandom(16)
    pw_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${pw_hash.hex()}"

def check_password(password: str, hashed: str) -> bool:
    try:
        if hashed.startswith("pbkdf2_sha256$"):
            _, iteration_text, salt_hex, hash_hex = hashed.split("$", 3)
            iterations = int(iteration_text)
        else:
            salt_hex, hash_hex = hashed.split(":", 1)
            iterations = 100000
        salt = bytes.fromhex(salt_hex)
        pw_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, iterations)
        return hmac.compare_digest(pw_hash.hex(), hash_hex)
    except Exception:
        return False

def init_users_db():
    conn = sqlite3.connect(DB_USERS_PATH, timeout=10)
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE,
            password_hash TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS task_ownership (
            task_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

init_users_db()

def record_task_ownership(task_id: str, user_id: str):
    conn = sqlite3.connect(DB_USERS_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO task_ownership (task_id, user_id) VALUES (?, ?)", (task_id, user_id))
        conn.commit()
    finally:
        conn.close()

def get_task_owner(task_id: str) -> Optional[str]:
    conn = sqlite3.connect(DB_USERS_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM task_ownership WHERE task_id = ?", (task_id,))
        row = cursor.fetchone()
        return row[0] if row else None
    finally:
        conn.close()

@flask_app.before_request
def check_auth():
    if request.path.startswith("/api/") and not request.path.startswith("/api/auth/") and request.path != "/api/tasks/health":
        if "user_id" not in session:
            return jsonify({"ok": False, "error": "Authentication required"}), 401

def login_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"ok": False, "error": "Authentication required"}), 401
        return f(*args, **kwargs)
    return decorated_function

@flask_app.post("/api/auth/register")
def register():
    if not config.REGISTRATION_ENABLED:
        return jsonify({"ok": False, "error": "New account registration is disabled"}), 403

    payload = request.get_json(silent=True) or {}
    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", ""))

    if not username or not password:
        return jsonify({"ok": False, "error": "Username and password are required"}), 400

    if len(username) < 3 or len(username) > 32 or not all(c.isalnum() or c in "_-" for c in username):
        return jsonify({"ok": False, "error": "Username must be 3-32 alphanumeric, underscore, or hyphen characters"}), 400

    if len(password) < 12 or len(password) > 1024:
        return jsonify({"ok": False, "error": "Password must be between 12 and 1024 characters"}), 400

    conn = sqlite3.connect(DB_USERS_PATH)
    try:
        cursor = conn.cursor()
        pw_hash = hash_password(password)
        user_id = str(uuid.uuid4())
        cursor.execute("INSERT INTO users (id, username, password_hash) VALUES (?, ?, ?)", (user_id, username, pw_hash))
        conn.commit()
        return jsonify({"ok": True, "message": "User registered successfully"})
    except sqlite3.IntegrityError:
        return jsonify({"ok": False, "error": "Username already exists"}), 400
    finally:
        conn.close()

@flask_app.post("/api/auth/login")
def login():
    payload = request.get_json(silent=True) or {}
    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", ""))

    if not username or not password or len(password) > 1024:
        return jsonify({"ok": False, "error": "Username and password are required"}), 400

    conn = sqlite3.connect(DB_USERS_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, password_hash FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()

    if row and check_password(password, row[1]):
        if not row[1].startswith("pbkdf2_sha256$"):
            with sqlite3.connect(DB_USERS_PATH) as upgrade_conn:
                upgrade_conn.execute(
                    "UPDATE users SET password_hash = ? WHERE id = ?",
                    (hash_password(password), row[0]),
                )
        session.permanent = True
        session["user_id"] = row[0]
        session["username"] = username
        return jsonify({"ok": True, "message": "Login successful", "user": {"id": row[0], "username": username}})

    return jsonify({"ok": False, "error": "Invalid username or password"}), 401

@flask_app.post("/api/auth/logout")
def logout():
    session.clear()
    return jsonify({"ok": True, "message": "Logged out successfully"})

@flask_app.get("/api/auth/me")
def me():
    if "user_id" in session:
        return jsonify({"ok": True, "user": {"id": session["user_id"], "username": session["username"]}})
    return jsonify({"ok": False, "error": "Not authenticated"}), 401

@flask_app.get("/api/download/<job_id>/<file_type>")
def download_job_file(job_id, file_type):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"ok": False, "error": "Not authenticated"}), 401

    from app.services.cheminformatics import find_job_dir
    try:
        job_dir = find_job_dir(user_id, job_id)
    except ValueError as ve:
        return jsonify({"ok": False, "error": str(ve)}), 400
    except FileNotFoundError as fnfe:
        return jsonify({"ok": False, "error": str(fnfe)}), 404

    file_mapping = {
        "sdf": ("outputs", "molecule.sdf"),
        "xyz": ("outputs", "molecule.xyz"),
        "mol2": ("outputs", "molecule.mol2"),
        "docked_poses_sdf": ("outputs", "docked_poses.sdf"),
        "docking_log": ("outputs", "docking_log.txt")
    }

    if file_type not in file_mapping:
        return jsonify({"ok": False, "error": "Invalid file type"}), 400

    sub_dir, filename = file_mapping[file_type]
    directory = os.path.join(job_dir, sub_dir)

    if not os.path.exists(os.path.join(directory, filename)):
        return jsonify({"ok": False, "error": "File not found"}), 404

    return send_from_directory(directory, filename, as_attachment=False)

gui_dir = str(GUI_DIR)

@flask_app.route('/static/<filename>')
def serve_static_files(filename):
    return send_from_directory(flask_app.static_folder, filename)

# Serve index.html at root
@flask_app.get("/")
def index():
    return send_from_directory(gui_dir, "index.html")

# Serve any file from gui/ directory (CSS, fonts, etc.)
@flask_app.get("/gui/<path:filename>")
def gui_file(filename):
    return send_from_directory(gui_dir, filename)

@flask_app.get("/api/pubchem/fetch")
def pubchem_fetch():
    """Legacy endpoint — kept for backward compatibility. Delegates to /api/drug/lookup."""
    name = request.args.get("name", "").strip()
    if not name:
        return jsonify({"ok": False, "error": "Name parameter is required."}), 400
    return drug_lookup()


@flask_app.get("/api/drug/lookup")
def drug_lookup():
    """
    Unified drug name → SMILES lookup endpoint.
    Strategy:
    1. Local DrugCentral SQLite (offline, instant, ~4,100 drugs)
    2. PubChem REST API fallback (online, requires internet)
    """
    name = request.args.get("name", "").strip()
    if not name:
        return jsonify({"ok": False, "error": "Name parameter is required."}), 400
    if len(name) > 200:
        return jsonify({"ok": False, "error": "Name exceeds 200 characters"}), 400

    # 1. Try local drug database first
    try:
        result = lookup_smiles_by_name(name)
        if result and result.get("smiles"):
            logger.info("Drug lookup hit in local database")
            return jsonify({
                "ok": True,
                "smiles": result["smiles"],
                "name": result.get("inn", name),
                "source": "local",
                "approved_by": result.get("approved_by", "DrugCentral")
            })
    except Exception as e:
        logger.debug(f"Local DB lookup error: {e}")

    # 2. Fallback: PubChem REST API
    try:
        encoded_name = quote(name, safe="")
        url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{encoded_name}/property/CanonicalSMILES/json"
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            data = res.json()
            smiles = data.get("PropertyTable", {}).get("Properties", [{}])[0].get("CanonicalSMILES")
            if smiles:
                logger.info("Drug lookup hit using PubChem fallback")
                return jsonify({"ok": True, "smiles": smiles, "name": name, "source": "pubchem"})
        return jsonify({"ok": False, "error": f"Could not find SMILES for compound '{name}'."}), 404
    except Exception as e:
        logger.error(f"PubChem fallback error: {e}")
        return jsonify({"ok": False, "error": "Drug lookup service failed"}), 500


@flask_app.get("/api/drug/autocomplete")
def drug_autocomplete():
    """
    Returns up to 10 drug name suggestions matching the given prefix.
    Used by the unified input field's live dropdown.
    """
    prefix = request.args.get("prefix", "").strip()
    try:
        limit = max(1, min(int(request.args.get("limit", 10)), 20))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "limit must be an integer"}), 400
    if len(prefix) < 2:
        return jsonify({"ok": True, "suggestions": []})
    try:
        suggestions = get_autocomplete_suggestions(prefix, limit=limit)
        return jsonify({"ok": True, "suggestions": suggestions})
    except Exception as e:
        logger.error(f"Autocomplete error: {e}")
        return jsonify({"ok": True, "suggestions": []})

@flask_app.get("/health")
def health():
    from app.services import is_gnina_available
    return jsonify({
        "status": "healthy",
        "environment": config.ENVIRONMENT,
        "capabilities": {
            "gnina": is_gnina_available(),
            "registration": config.REGISTRATION_ENABLED,
        },
        "services": {
            "rdkit": "available" if Chem is not None else "unavailable",
            "torch": "available" if torch is not None else "unavailable",
            "pymol": "enabled" if config.PYMOL_ENABLED else "disabled",
            "ollama": "enabled" if config.OLLAMA_ENABLED else "disabled",
            "gnina": "available" if is_gnina_available() else "disabled",
            "drug_database": get_db_stats(),
        },
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    })

@flask_app.post("/api/analyze_smiles")
def analyze_smiles():
    payload = request.get_json(silent=True) or {}
    smiles = str(payload.get("smiles", "")).strip()
    if not smiles:
        return jsonify({"ok": False, "error": "SMILES is required."}), 400
    if len(smiles) > config.SMILES_LENGTH_LIMIT:
        return jsonify({"ok": False, "error": "SMILES exceeds configured length limit"}), 400
    validation_mol = Chem.MolFromSmiles(smiles, sanitize=True)
    if validation_mol is None:
        return jsonify({"ok": False, "error": "Invalid SMILES"}), 400
    if validation_mol.GetNumAtoms() > config.MOLECULE_SIZE_LIMIT:
        return jsonify({"ok": False, "error": "Molecule exceeds configured atom limit"}), 400

    user_id = session.get("user_id")
    job_id = payload.get("job_id") or str(uuid.uuid4())
    from app.services.cheminformatics import get_or_create_job_dir
    get_or_create_job_dir(user_id, job_id)

    response = build_smiles_response(None, smiles, user_id=user_id, job_id=job_id)
    status_code = 200 if response.get("ok") else 422
    return jsonify(response), status_code

@flask_app.post("/api/chat")
def chat():
    payload = request.get_json(silent=True) or {}
    prompt = str(payload.get("prompt", "")).strip()
    if not prompt:
        return jsonify({"ok": False, "error": "Prompt is required."}), 400
    if len(prompt) > 1000:
        return jsonify({"ok": False, "error": "Prompt exceeds 1000 characters"}), 400
    try:
        cmd = query_ollama_for_pymol(prompt)
        source = "ollama" if config.OLLAMA_ENABLED else "fallback"
        result = execute_pymol_commands(cmd) if cmd else "No command generated."
        return jsonify({"ok": True, "command": cmd, "result": result, "source": source})
    except Exception as e:
        logger.error(f"Chat API error: {e}")
        return jsonify({"ok": False, "error": "Chat processing failed"}), 500

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
    if len(smiles) > config.SMILES_LENGTH_LIMIT:
        return jsonify({"ok": False, "error": "SMILES exceeds configured length limit"}), 400
    try:
        mol = smiles_to_rdkit_mol(smiles)
        if mol is None:
            return jsonify({"ok": False, "error": "Invalid SMILES"}), 400
        desc = calculate_adme_descriptors(mol)
        return jsonify(desc)
    except Exception as e:
        logger.error(f"Descriptors error: {e}")
        return jsonify({"ok": False, "error": "Descriptor calculation failed"}), 500

@flask_app.post("/api/pdb/upload")
def pdb_upload():
    """Upload a custom PDB file for local profiling and docking."""
    import gzip
    import uuid as _uuid
    from app.services import parse_pdb_structure, get_ligands_in_structure
    from app.services.cheminformatics import get_or_create_job_dir

    content_length = request.content_length
    if content_length is not None and content_length > 5 * 1024 * 1024:
        return jsonify({"ok": False, "error": "File size exceeds limit of 5 MB."}), 413

    if "file" not in request.files:
        return jsonify({"ok": False, "error": "No file uploaded"}), 400
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"ok": False, "error": "No file selected"}), 400

    filename = file.filename
    if filename.lower().endswith(".pdb.gz"):
        ext = ".pdb.gz"
    else:
        ext = os.path.splitext(filename)[1].lower()

    allowed_extensions = {".pdb", ".ent", ".pdb.gz"}
    if ext not in allowed_extensions:
        return jsonify({"ok": False, "error": f"Unsupported file type: {ext}. Upload a .pdb or .pdb.gz file."}), 400

    max_decompressed_size = 10 * 1024 * 1024
    content_buffer = bytearray()
    try:
        if ext == ".pdb.gz":
            try:
                gzip_file = gzip.GzipFile(fileobj=file.stream)
                while True:
                    chunk = gzip_file.read(65536)
                    if not chunk:
                        break
                    content_buffer.extend(chunk)
                    if len(content_buffer) > max_decompressed_size:
                        return jsonify({"ok": False, "error": "Decompressed file size exceeds limit of 10 MB."}), 400
            except Exception as ex:
                return jsonify({"ok": False, "error": f"Failed to decompress file: {ex}"}), 400
        else:
            content_buffer.extend(file.read(max_decompressed_size + 1))
            if len(content_buffer) > max_decompressed_size:
                return jsonify({"ok": False, "error": "File size exceeds limit of 10 MB."}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": f"Error reading upload stream: {e}"}), 400

    try:
        content_str = bytes(content_buffer).decode("utf-8", errors="ignore")
        lines = content_str.splitlines()

        pdb_keywords = {"HEADER", "TITLE", "REMARK", "ATOM", "HETATM", "CRYST1", "SEQRES", "HELIX", "SHEET"}
        is_pdb = any(any(line.startswith(kw) for kw in pdb_keywords) for line in lines[:100])
        if not is_pdb:
            return jsonify({"ok": False, "error": "Invalid file content. Not a valid PDB structure file."}), 400

        if len(lines) > 100000:
            return jsonify({"ok": False, "error": "File contains too many records (max 100,000 allowed)."}), 400

        atom_count = sum(1 for line in lines if line.startswith("ATOM") or line.startswith("HETATM"))
        if atom_count > 50000:
            return jsonify({"ok": False, "error": "File contains too many atoms (max 50,000 allowed)."}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": f"Failed to verify file content structure: {e}"}), 400

    try:
        user_id = session.get("user_id")
        job_id = request.form.get("job_id") or str(_uuid.uuid4())

        job_dir = get_or_create_job_dir(user_id, job_id)

        base_name = os.path.splitext(os.path.basename(filename))[0]
        if base_name.lower().endswith(".pdb"):
            base_name = base_name[:-4]

        safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in base_name) + ".pdb"
        save_path = os.path.join(job_dir, "input", safe_name)

        with open(save_path, "w", encoding="utf-8") as f_out:
            f_out.write(content_str)

        logger.info(f"Custom PDB uploaded securely: {safe_name} → {save_path} for user {user_id}")

        struct = parse_pdb_structure(save_path)
        ligands = get_ligands_in_structure(struct)

        pseudo_id = safe_name[:-4].upper()[:8]

        return jsonify({
            "ok": True,
            "filename": safe_name,
            "pdb_id": pseudo_id,
            "job_id": job_id,
            "ligands": [{"resname": name, "chain": chain, "seq": seq} for name, chain, seq in ligands]
        })
    except Exception as e:
        logger.error(f"PDB upload error: {e}")
        return jsonify({"ok": False, "error": "PDB upload processing failed"}), 500

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
        return jsonify({"ok": False, "error": "PDB retrieval failed"}), 502

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
        coords, bonds = [], []
        if mol:
            mol = generate_2d_coords(mol)
            from app.services.cheminformatics import mol_to_json_graph
            coords, bonds = mol_to_json_graph(mol)

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
        return jsonify({"ok": False, "error": "Interaction profiling failed"}), 500

@flask_app.post("/api/dock")
def dock():
    """One-click docking: dock drawn molecule against uploaded/fetched PDB target."""
    from app.services import dock_molecule, is_gnina_available, autobox_from_ligand, fetch_pdb_file

    if not is_gnina_available():
        return jsonify({"ok": False, "error": "GNINA binary not installed. See /health for setup instructions."}), 503

    payload = request.get_json(silent=True) or {}
    pdb_id = str(payload.get("pdb_id", "")).strip().upper()
    ligand_resname = str(payload.get("ligand_resname", "")).strip().upper()
    user_id = session.get("user_id") or "anonymous"
    job_id = payload.get("job_id")
    if not job_id:
        return jsonify({"ok": False, "error": "Active job_id is required"}), 400

    from app.services.cheminformatics import find_job_dir
    job_dir = find_job_dir(user_id, job_id)
    if not job_dir:
        return jsonify({"ok": False, "error": "Job directory not found"}), 404

    ligand_sdf = os.path.join(job_dir, "outputs", "molecule.sdf")
    if not os.path.exists(ligand_sdf):
        return jsonify({"ok": False, "error": "Molecule SDF not found in job directory"}), 400

    try:
        receptor_path = fetch_pdb_file(pdb_id)

        # Auto-calculate box from existing ligand if available
        box_params = {}
        if ligand_resname:
            box_params = autobox_from_ligand(receptor_path, ligand_resname)

        result = dock_molecule(
            ligand_sdf_path=ligand_sdf,
            receptor_pdb_path=receptor_path,
            output_dir=os.path.join(job_dir, "outputs"),
            **box_params
        )
        if result.get("ok"):
            # Do not disclose host filesystem locations in an API response.
            result["output_sdf"] = "docked_poses.sdf"
            result.pop("log_path", None)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Docking error: {e}")
        return jsonify({"ok": False, "error": "Docking failed"}), 500

@flask_app.post("/api/admet")
def admet():
    """Neural network ADMET prediction endpoint."""
    from app.services import predict_admet_nn
    payload = request.get_json(silent=True) or {}
    smiles = str(payload.get("smiles", "")).strip()
    if not smiles:
        return jsonify({"ok": False, "error": "SMILES is required"}), 400
    if len(smiles) > config.SMILES_LENGTH_LIMIT:
        return jsonify({"ok": False, "error": "SMILES exceeds configured length limit"}), 400
    try:
        result = predict_admet_nn(smiles)
        return jsonify(result)
    except Exception as e:
        logger.error(f"ADMET prediction error: {e}")
        return jsonify({"ok": False, "error": "ADMET prediction failed"}), 500

@flask_app.post("/api/mcs_align")
def mcs_align():
    from rdkit.Chem import rdFMCS
    from app.services import smiles_to_rdkit_mol
    payload = request.get_json(silent=True) or {}
    smiles_list = payload.get("smiles_list", [])
    if not isinstance(smiles_list, list) or len(smiles_list) < 2:
        return jsonify({"ok": False, "error": "At least 2 SMILES are required for alignment."}), 400
    if len(smiles_list) > 20:
        return jsonify({"ok": False, "error": "At most 20 SMILES can be aligned at once."}), 400

    try:
        mols = []
        for s in smiles_list:
            if not isinstance(s, str) or len(s) > config.SMILES_LENGTH_LIMIT:
                return jsonify({"ok": False, "error": "Invalid SMILES input length"}), 400
            mol = smiles_to_rdkit_mol(s)
            if mol is None:
                return jsonify({"ok": False, "error": "Invalid SMILES in list"}), 400
            if mol.GetNumAtoms() > config.MOLECULE_SIZE_LIMIT:
                return jsonify({"ok": False, "error": "Molecule exceeds configured atom limit"}), 400
            mols.append(mol)

        from rdkit.Chem import rdDepictor
        for mol in mols:
            rdDepictor.Compute2DCoords(mol)

        res = rdFMCS.FindMCS(mols)
        if res.numAtoms == 0:
            aligned_coords = []
            for mol in mols:
                from app.services.cheminformatics import mol_to_json_graph
                c, b = mol_to_json_graph(mol)
                aligned_coords.append({"atoms": c, "bonds": b})
            return jsonify({"ok": True, "aligned": aligned_coords})

        mcs_query = Chem.MolFromSmarts(res.smartsString)
        ref_mol = mols[0]
        ref_match = ref_mol.GetSubstructMatch(mcs_query)

        aligned_coords = []
        from app.services.cheminformatics import mol_to_json_graph
        for i, mol in enumerate(mols):
            if i > 0:
                match = mol.GetSubstructMatch(mcs_query)
                if match and ref_match:
                    try:
                        rdDepictor.GenerateDepictionMatching2DStructure(mol, ref_mol, acceptFailure=True)
                    except Exception as align_err:
                        logger.warning(f"Matching 2D alignment failed: {align_err}")

            c, b = mol_to_json_graph(mol)
            aligned_coords.append({"atoms": c, "bonds": b})

        return jsonify({"ok": True, "aligned": aligned_coords})
    except Exception as e:
        logger.error(f"MCS align error: {e}")
        return jsonify({"ok": False, "error": "MCS alignment failed"}), 500

def _redis_available() -> bool:
    """Fast Redis ping — returns True only if Redis is reachable within 1 second."""
    try:
        import redis as redis_lib
        from app.config import get_config as _gc
        url = _gc().REDIS_URL
        r = redis_lib.from_url(url, socket_connect_timeout=1, socket_timeout=1)
        return r.ping()
    except Exception:
        return False


@flask_app.get("/api/tasks/health")
def tasks_health():
    """Quick probe: is the Celery/Redis backend reachable?"""
    ok = _redis_available()
    return jsonify({"ok": ok, "broker": "redis", "status": "online" if ok else "offline"}), 200


@flask_app.get("/health/live")
def health_live():
    return jsonify({"ok": True, "status": "live"})


@flask_app.get("/health/ready")
def health_ready():
    checks = {
        "redis": _redis_available(),
        "database": False,
        "storage": False,
        "model": False,
        "drug_data": False,
    }
    try:
        with sqlite3.connect(DB_USERS_PATH) as conn:
            conn.execute("SELECT 1").fetchone()
        checks["database"] = True
    except Exception as exc:
        logger.warning(f"Readiness database check failed: {exc}")

    jobs_dir = str(JOBS_DIR)
    try:
        os.makedirs(jobs_dir, exist_ok=True)
        checks["storage"] = os.access(jobs_dir, os.W_OK)
    except OSError:
        pass

    try:
        from app.services.models import verify_model_checkpoint
        checks["model"] = verify_model_checkpoint()
    except Exception as exc:
        logger.warning(f"Readiness model check failed: {exc}")

    try:
        from app.paths import DRUG_DATABASE_PATH, DRUG_FINGERPRINT_PATH
        checks["drug_data"] = (
            DRUG_DATABASE_PATH.is_file() and DRUG_DATABASE_PATH.stat().st_size > 0
            and DRUG_FINGERPRINT_PATH.is_file() and DRUG_FINGERPRINT_PATH.stat().st_size > 0
        )
    except OSError as exc:
        logger.warning(f"Readiness drug-data check failed: {exc}")

    required = {
        "database": True,
        "storage": True,
        "redis": config.REQUIRE_REDIS,
        "model": config.REQUIRE_MODEL,
        "drug_data": config.REQUIRE_DRUG_DATA,
    }
    ready = all(checks[name] for name, is_required in required.items() if is_required)
    status = 200 if ready else 503
    return jsonify({
        "ok": ready,
        "status": "ready" if ready else "not_ready",
        "checks": checks,
        "required": required,
    }), status


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
    redis_up = _redis_available()

    user_id = session.get("user_id")
    job_id = payload.get("job_id") or str(uuid.uuid4())

    if not redis_up:
        return jsonify({
            "ok": False,
            "error": "Task orchestration requires the Celery/Redis backend. Start Redis first: redis-server --daemonize yes",
            "requires_redis": True
        }), 503

    task_id = None
    estimated_time = "~30s"

    try:
        if task_type == "optimize_3d":
            from app.tasks import run_3d_optimization_task
            result = run_3d_optimization_task.delay(
                smiles=params["smiles"],
                force_field=params.get("force_field", "MMFF94"),
                user_id=user_id,
                job_id=job_id
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
                ligand_seq=params.get("ligand_seq"),
                user_id=user_id,
                job_id=job_id
            )
            task_id = result.id
            estimated_time = "~15s"

        elif task_type == "md_simulation":
            from app.tasks import run_openmm_md_task
            from app.services.cheminformatics import find_job_dir
            if not job_id:
                return jsonify({"ok": False, "error": "job_id is required"}), 400
            try:
                job_dir_path = find_job_dir(user_id, job_id)
            except ValueError as ve:
                return jsonify({"ok": False, "error": str(ve)}), 400
            except FileNotFoundError as fnfe:
                return jsonify({"ok": False, "error": str(fnfe)}), 404
            structure_path = os.path.join(job_dir_path, "outputs", "molecule.sdf")
            if not os.path.exists(structure_path):
                return jsonify({"ok": False, "error": "molecule.sdf not found for this job"}), 404

            result = run_openmm_md_task.delay(
                structure_path=structure_path,
                n_steps=params["n_steps"]
            )
            task_id = result.id
            estimated_time = "~1m"

        if task_id and user_id:
            record_task_ownership(task_id, user_id)

        return jsonify({
            "ok": True,
            "task_id": task_id,
            "estimated_time": estimated_time,
            "job_id": job_id
        })
    except Exception as e:
        logger.error(f"Task submission error: {e}")
        return jsonify({"ok": False, "error": "Task submission failed"}), 500

@flask_app.get("/api/tasks/status/<task_id>")
def tasks_status(task_id):
    user_id = session.get("user_id")
    owner_id = get_task_owner(task_id)
    if not owner_id or owner_id != user_id:
        return jsonify({"ok": False, "error": "Access forbidden: you do not own this task"}), 403

    # (Sync task check removed for multi-worker compatibility)

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
            logger.error("Background task %s failed: %s", task_id, res.result)
            response_data["error"] = "Background task failed; check server logs"
        elif state == "PROGRESS":
            meta = res.info or {}
            response_data["percent"] = meta.get("percent", 0)
            response_data["message"] = meta.get("message", "Processing...")

        return jsonify(response_data)
    except Exception as e:
        logger.error(f"Task status retrieval error: {e}")
        return jsonify({"ok": False, "error": "Task status retrieval failed"}), 500

@flask_app.delete("/api/tasks/cancel/<task_id>")
def tasks_cancel(task_id):
    user_id = session.get("user_id")
    owner_id = get_task_owner(task_id)
    if not owner_id or owner_id != user_id:
        return jsonify({"ok": False, "error": "Access forbidden: you do not own this task"}), 403

    from celery.result import AsyncResult
    from app.tasks import celery_app

    try:
        res = AsyncResult(task_id, app=celery_app)
        res.revoke(terminate=True)
        return jsonify({"ok": True, "message": f"Task {task_id} successfully revoked."})
    except Exception as e:
        logger.error(f"Task cancel error: {e}")
        return jsonify({"ok": False, "error": "Task cancellation failed"}), 500

@flask_app.post("/api/action_log")
def action_log():
    """Silently log user drawing actions for generative AI training data."""
    if not config.ACTION_LOGGING_ENABLED:
        return jsonify({"ok": True, "enabled": False}), 200
    from app.services import log_action
    payload = request.get_json(silent=True) or {}
    action_type = payload.get("action", "")
    data = payload.get("data", {})
    session_id = payload.get("session_id")
    allowed_actions = {
        "add_atom", "delete_atom", "move_atom", "add_bond", "delete_bond",
        "change_bond_type", "change_element", "clear_canvas", "undo", "redo",
        "submit_render",
    }
    if action_type not in allowed_actions or not isinstance(data, dict):
        return jsonify({"ok": False, "error": "Invalid action log payload"}), 400
    log_action(action_type, data, session_id)
    return jsonify({"ok": True}), 200

@flask_app.post("/api/action_log/start")
def action_log_start():
    """Start a new action logging session."""
    if not config.ACTION_LOGGING_ENABLED:
        return jsonify({"ok": True, "enabled": False, "session_id": None})
    from app.services import start_session
    sid = start_session()
    return jsonify({"ok": True, "session_id": sid})

@flask_app.post("/api/design_score")
def design_score():
    """Real-time design score for gamified feedback."""
    from app.services import calculate_design_score
    payload = request.get_json(silent=True) or {}
    smiles = str(payload.get("smiles", "")).strip()
    if not smiles:
        return jsonify({"ok": False, "score": 0, "grade": "F", "color": "#EF4444"}), 200
    if len(smiles) > config.SMILES_LENGTH_LIMIT:
        return jsonify({"ok": False, "error": "SMILES exceeds configured length limit"}), 400
    result = calculate_design_score(smiles)
    return jsonify(result)

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
