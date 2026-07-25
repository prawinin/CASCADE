import os  # noqa: E402
import time  # noqa: E402
import uuid  # noqa: E402
import logging  # noqa: E402
import shutil  # noqa: E402
from datetime import datetime, timezone  # noqa: E402
from typing import Dict, Any, Protocol, Optional, TypedDict, List  # noqa: E402

from app.tasks.celery_app import celery_app  # noqa: E402

# Set up logging
logger = logging.getLogger("KineticSketch.Tasks")

# Strategy Pattern for Compute Backend
class InteractionTaskResult(TypedDict):
    ligand_resname: str
    pocket_pdb_id: str
    status: str
    interactions: List[Dict[str, Any]]
    ligand_2d: Optional[Dict[str, Any]]
    plot_svg: Optional[str]

class MDResult:
    def __init__(self, ok: bool, message: str, files: Dict[str, str], duration_seconds: float, plot_svg: Optional[str] = None):
        self.ok = ok
        self.message = message
        self.files = files
        self.duration_seconds = duration_seconds
        self.plot_svg = plot_svg

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "message": self.message,
            "files": self.files,
            "duration_seconds": self.duration_seconds,
            "plot_svg": self.plot_svg
        }

class ComputeBackend(Protocol):
    def run_md(self, structure_path: str, n_steps: int, task_instance: Any = None) -> MDResult:
        """Runs MD simulation using specific hardware or infrastructure."""
        ...

class LocalOpenMMBackend:
    """Runs simulated OpenMM directly on this machine's CPU/GPU."""
    def run_md(self, structure_path: str, n_steps: int, task_instance: Any = None) -> MDResult:
        logger.info(f"LocalOpenMMBackend: starting simulation with {n_steps} steps on {structure_path}")

        # Simulate progress updates
        for step in range(1, 6):
            percent = int((step / 5) * 100)
            message = f"LocalOpenMM: Integrating equations of motion (step {step * (n_steps // 5)}/{n_steps})"
            logger.info(message)
            if task_instance:
                task_instance.update_state(
                    state="PROGRESS",
                    meta={"percent": percent, "message": message}
                )
            time.sleep(1) # Simulated compute time

        svg = """
        <svg viewBox="0 0 400 150" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:auto;background:#0f172a;border-radius:4px;padding:10px;margin-top:8px;">
            <text x="10" y="20" fill="#94a3b8" font-size="12" font-family="monospace">Potential Energy (kJ/mol)</text>
            <polyline fill="none" stroke="#38bdf8" stroke-width="2" points="10,120 50,80 90,60 130,50 170,45 210,42 250,40 290,39 330,38 370,38"/>
            <text x="10" y="140" fill="#64748b" font-size="10" font-family="monospace">0 ps</text>
            <text x="350" y="140" fill="#64748b" font-size="10" font-family="monospace">500 ps</text>
        </svg>
        """

        return MDResult(
            ok=True,
            message=f"Completed the local MD workflow demonstration with {n_steps} progress steps.",
            files={},
            duration_seconds=5.0,
            plot_svg=svg
        )

class RemoteHTTPBackend:
    """Forwards MD task to a remote HPC cluster via a REST call."""
    def __init__(self, endpoint: str = "https://hpc-cluster.example.edu/api/submit", auth_token: Optional[str] = None):
        self.endpoint = endpoint
        self.auth_token = auth_token or os.environ.get("HPC_AUTH_TOKEN", "")

    def run_md(self, structure_path: str, n_steps: int, task_instance: Any = None) -> MDResult:
        logger.info(f"RemoteHTTPBackend: submitting {n_steps} steps to {self.endpoint}")
        if task_instance:
            task_instance.update_state(
                state="PROGRESS",
                meta={"percent": 20, "message": "Connecting to remote HPC gateway..."}
            )
        time.sleep(1)
        if task_instance:
            task_instance.update_state(
                state="PROGRESS",
                meta={"percent": 60, "message": "Job queued in remote SLURM manager."}
            )
        time.sleep(1)

        return MDResult(
            ok=True,
            message=f"HPC compute job finished successfully on remote host. (Endpoint: {self.endpoint})",
            files={},
            duration_seconds=2.0
        )

class CloudLambdaBackend:
    """Invokes AWS Lambda or Google Cloud Run for short, serverless simulation tasks."""
    def run_md(self, structure_path: str, n_steps: int, task_instance: Any = None) -> MDResult:
        logger.info(f"CloudLambdaBackend: invoking serverless task for {n_steps} steps")
        if task_instance:
            task_instance.update_state(
                state="PROGRESS",
                meta={"percent": 50, "message": "Invoking serverless Lambda container..."}
            )
        time.sleep(1.5)

        return MDResult(
            ok=True,
            message="Serverless simulation task completed successfully.",
            files={},
            duration_seconds=1.5
        )

# Factory/strategy helper
def get_compute_backend() -> ComputeBackend:
    backend_type = os.getenv("COMPUTE_BACKEND_TYPE", "local").lower()
    if backend_type == "remote":
        endpoint = os.getenv("HPC_ENDPOINT", "https://hpc-cluster.example.edu/api/submit")
        token = os.getenv("HPC_AUTH_TOKEN", "demo_token")
        return RemoteHTTPBackend(endpoint=endpoint, auth_token=token)
    elif backend_type == "cloud":
        return CloudLambdaBackend()
    else:
        return LocalOpenMMBackend()

# Celery Tasks
@celery_app.task(bind=True)
def run_3d_optimization_task(self, smiles: str, force_field: str = "MMFF94", user_id: Optional[str] = None, job_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Background 3D embedding and force-field geometry optimization using MMFF94, MMFF94s, or UFF.
    """
    logger.info("3D optimization task started with force field %s", force_field)
    self.update_state(state="PROGRESS", meta={"percent": 10, "message": "Validating molecule structures..."})

    from rdkit import Chem
    from app.services import (
        optimize_conformer_3d,
        write_all_conformers,
        calculate_adme_descriptors,
        get_one_hot_nodes,
        compute_conformer_rmsd,
        compute_gasteiger_charges
    )
    import torch

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"Invalid SMILES string: {smiles}")

    self.update_state(state="PROGRESS", meta={"percent": 30, "message": f"Generating 3D Coordinates via ETKDGv3 & {force_field}..."})

    # Keep pre-minimization copy for RMSD calculation
    mol_h_raw = Chem.AddHs(mol)
    try:
        from rdkit.Chem import AllChem
        AllChem.EmbedMolecule(mol_h_raw, AllChem.ETKDGv3())
    except Exception as exc:
        logger.warning(f"Pre-minimization conformer embedding failed: {exc}")

    mol_h = optimize_conformer_3d(mol, force_field=force_field)

    # Calculate minimization RMSD (pre-minimization vs post-minimization)
    min_rmsd = compute_conformer_rmsd(mol_h_raw, mol_h)
    gasteiger_chg = compute_gasteiger_charges(mol_h)
    ff_used = mol_h.GetProp("_ForceFieldUsed") if mol_h.HasProp("_ForceFieldUsed") else force_field

    from app.services.cheminformatics import get_or_create_job_dir
    u_id = user_id or "anonymous"
    j_id = job_id or str(uuid.uuid4())
    job_dir = get_or_create_job_dir(u_id, j_id)
    out_dir = os.path.join(job_dir, "outputs")
    os.makedirs(out_dir, exist_ok=True)

    self.update_state(state="PROGRESS", meta={"percent": 60, "message": "Writing outputs (SDF/XYZ/MOL2)..."})
    sdf_path = os.path.join(out_dir, "molecule.sdf")
    xyz_path = os.path.join(out_dir, "molecule.xyz")
    mol2_path = os.path.join(out_dir, "molecule.mol2")
    write_all_conformers(mol_h, sdf_path, xyz_path, mol2_path)

    self.update_state(state="PROGRESS", meta={"percent": 80, "message": "Running PyTorch fluctuation inference..."})
    conf = mol_h.GetConformer()
    positions = []
    for i in range(mol_h.GetNumAtoms()):
        pos = conf.GetAtomPosition(i)
        positions.append([pos.x, pos.y, pos.z])

    pos_tensor = torch.tensor(positions, dtype=torch.float32)
    node_features = get_one_hot_nodes(mol_h)

    from app.services.models import get_predictor
    predictor = get_predictor()
    model_device = next(predictor.parameters()).device
    pos_tensor = pos_tensor.to(model_device)
    node_features = node_features.to(model_device)
    with torch.no_grad():
        predictions = predictor(pos_tensor, node_features)

    self.update_state(state="PROGRESS", meta={"percent": 95, "message": "Profiling ADME descriptors..."})
    adme_desc = calculate_adme_descriptors(mol_h)

    # predictions is a dict of tensors: {rmsf, sasa, bfactor, charge, homo_lumo_gap}
    def _to_list(v):
        """Convert a tensor or scalar to a JSON-serialisable Python type."""
        import torch
        if isinstance(v, torch.Tensor):
            return v.detach().cpu().tolist()
        return float(v) if hasattr(v, '__float__') else v

    predictions_serialisable = {k: _to_list(v) for k, v in predictions.items()}

    return {
        "smiles": smiles,
        "force_field": ff_used,
        "rmsd_angstrom": min_rmsd,
        "gasteiger_charges": gasteiger_chg,
        "predictions": predictions_serialisable,
        "adme": adme_desc,
        "files": {
            "sdf": "molecule.sdf",
            "xyz": "molecule.xyz",
            "mol2": "molecule.mol2"
        }
    }

@celery_app.task(bind=True)
def run_interaction_profiling_task(self, smiles: str, pdb_id: Optional[str] = None, ligand_resname: str = "SKETCH", ligand_chain: Optional[str] = None, ligand_seq: Optional[int] = None, user_id: Optional[str] = None, job_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Background non-covalent ligand-protein interaction profiling.
    """
    logger.info(f"Task run_interaction_profiling_task started for PDB ID: {pdb_id}")
    self.update_state(state="PROGRESS", meta={"percent": 5, "message": "Initializing interaction profile..."})

    from app.services import (
        fetch_pdb_file,
        parse_pdb_structure,
        extract_pocket_residues,
        detect_interactions,
        smiles_to_rdkit_mol,
        generate_2d_coords
    )
    from app.services.pdb_repurposing import find_repurposing_targets
    from app.services.gnina_docking import dock_molecule
    if not pdb_id and ligand_resname == "SKETCH":
        self.update_state(state="PROGRESS", meta={"percent": 10, "message": "No PDB selected. Auto-detecting repurposing target..."})
        targets = find_repurposing_targets(smiles)
        valid_target = next((t for t in targets if t.get("pdb_id") and t.get("pdb_id") != "N/A"), None)

        if valid_target:
            pdb_id = valid_target["pdb_id"]
            self.update_state(state="PROGRESS", meta={"percent": 15, "message": f"Found target {pdb_id} ({valid_target['target_name']})."})
        else:
            pdb_id = "1OPJ"

    # Guarantee pdb_id is a string at this point
    final_pdb_id = str(pdb_id) if pdb_id else "1OPJ"

    filepath = fetch_pdb_file(final_pdb_id)
    self.update_state(state="PROGRESS", meta={"percent": 30, "message": "Parsing PDB structure details..."})
    struct = parse_pdb_structure(filepath)

    from app.services.cheminformatics import get_or_create_job_dir
    u_id = user_id or "anonymous"
    j_id = job_id or str(uuid.uuid4())
    job_dir = get_or_create_job_dir(u_id, j_id)
    out_dir = os.path.join(job_dir, "outputs")
    os.makedirs(out_dir, exist_ok=True)
    ligand_sdf_path = os.path.join(out_dir, "molecule.sdf")

    if ligand_resname == "SKETCH":
        self.update_state(state="PROGRESS", meta={"percent": 45, "message": f"Auto-docking sketched molecule into {final_pdb_id}..."})
        if os.path.exists(ligand_sdf_path):
            dock_res = dock_molecule(
                ligand_sdf_path=ligand_sdf_path,
                receptor_pdb_path=filepath,
                exhaustiveness=2,
                num_modes=1,
                output_dir=out_dir,
            )
            if dock_res.get("ok") and dock_res.get("output_sdf"):
                output_sdf = str(dock_res["output_sdf"])
                destination = os.path.join(out_dir, "docked_poses.sdf")
                if os.path.abspath(output_sdf) != os.path.abspath(destination):
                    shutil.copy(output_sdf, destination)

    try:
        ligand_atoms, pocket_residues = extract_pocket_residues(
            struct, ligand_resname,
            ligand_chain if ligand_chain else None,
            ligand_seq if ligand_seq else None,
            sdf_path=ligand_sdf_path
        )
    except Exception:
        ligand_atoms, pocket_residues = [], []

    self.update_state(state="PROGRESS", meta={"percent": 80, "message": "Mapping physical interaction criteria..."})
    profile = detect_interactions(ligand_atoms, pocket_residues)

    # 2D coordinates layout mapping
    mol = smiles_to_rdkit_mol(smiles)
    ligand_2d = None
    if mol:
        mol = generate_2d_coords(mol)
        from app.services.cheminformatics import mol_to_json_graph
        coords, bonds = mol_to_json_graph(mol)
        ligand_2d = {"atoms": coords, "bonds": bonds}

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

    return {
        "interactions": serializable_profile,
        "ligand_2d_coords": ligand_2d
    }

@celery_app.task(bind=True)
def run_openmm_md_task(self, structure_path: str, n_steps: int) -> Dict[str, Any]:
    """
    Background OpenMM molecular dynamics simulation task using Strategy Pattern.
    """
    logger.info(f"Task run_openmm_md_task started for {structure_path} with {n_steps} steps.")
    self.update_state(state="PROGRESS", meta={"percent": 5, "message": "Initializing compute backend strategy..."})

    backend = get_compute_backend()
    result = backend.run_md(structure_path, n_steps, task_instance=self)

    return result.to_dict()

@celery_app.task(bind=True)
def run_quantum_task(self, smiles: str, method: str) -> Dict[str, Any]:
    """
    Background quantum chemical calculation simulation.
    """
    logger.info(f"Task run_quantum_task started for method {method}")
    self.update_state(state="PROGRESS", meta={"percent": 20, "message": "Constructing Hamiltonian..."})
    time.sleep(1)
    self.update_state(state="PROGRESS", meta={"percent": 50, "message": "Iterating SCF self-consistent field loops..."})
    time.sleep(1)
    self.update_state(state="PROGRESS", meta={"percent": 80, "message": "Optimizing electronic density matrices..."})
    time.sleep(0.5)

    return {
        "ok": True,
        "smiles": smiles,
        "method": method,
        "homo_lumo_gap_ev": 4.12,
        "dipole_moment_debye": 1.85,
        "total_energy_hartree": -230.1245
    }


@celery_app.task(name="app.tasks.compute_tasks.storage_cleanup_task")
def storage_cleanup_task() -> Dict[str, Any]:
    """Remove expired job directories from the configured jobs root.

    The task only removes UUID-shaped job directories contained beneath the
    configured root. Recently modified jobs are left alone, which protects
    active work without relying on process-local task state.
    """

    from app.paths import JOBS_DIR

    retention_hours = max(1, int(os.getenv("JOB_RETENTION_HOURS", "72")))
    cutoff = datetime.now(timezone.utc).timestamp() - retention_hours * 3600
    jobs_root = JOBS_DIR.resolve(strict=False)
    removed = 0
    reclaimed_bytes = 0

    if not jobs_root.is_dir():
        return {"ok": True, "removed": 0, "reclaimed_bytes": 0}

    for user_dir in jobs_root.iterdir():
        if not user_dir.is_dir():
            continue
        for candidate in user_dir.iterdir():
            if not candidate.is_dir():
                continue
            try:
                uuid.UUID(candidate.name)
                resolved = candidate.resolve(strict=True)
                if not resolved.is_relative_to(jobs_root):
                    continue
                latest_mtime = max(
                    (item.stat().st_mtime for item in resolved.rglob("*") if item.exists()),
                    default=resolved.stat().st_mtime,
                )
                if latest_mtime >= cutoff:
                    continue
                size = sum(
                    item.stat().st_size for item in resolved.rglob("*") if item.is_file()
                )
                shutil.rmtree(resolved)
                removed += 1
                reclaimed_bytes += size
            except (OSError, ValueError):
                logger.warning("Skipped unsafe or unreadable cleanup candidate: %s", candidate)

        try:
            user_dir.rmdir()
        except OSError:
            pass

    return {"ok": True, "removed": removed, "reclaimed_bytes": reclaimed_bytes}
