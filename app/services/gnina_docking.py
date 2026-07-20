"""
KineticSketch — GNINA Molecular Docking Service
Wraps the GNINA deep-learning-powered molecular docking engine.
GNINA is an AutoDock Vina fork that uses CNN scoring for pose ranking.

Setup: Download gnina binary from https://github.com/gnina/gnina/releases
       Place it in the project root or set GNINA_PATH env var.
"""

import os  # noqa: E402
import logging  # noqa: E402
import subprocess  # nosec B404
from typing import Dict, Any, List  # noqa: E402

logger = logging.getLogger("KineticSketch.GNINADocking")

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GNINA_PATH = os.getenv("GNINA_PATH", os.path.join(_PROJECT_ROOT, "gnina"))
DOCKING_OUTPUT_DIR = os.path.join(_PROJECT_ROOT, "scratch", "docking_results")
os.makedirs(DOCKING_OUTPUT_DIR, exist_ok=True)


def is_gnina_available() -> bool:
    """Check if GNINA binary is accessible and executable."""
    return os.path.isfile(GNINA_PATH) and os.access(GNINA_PATH, os.X_OK)


def dock_molecule(
    ligand_sdf_path: str,
    receptor_pdb_path: str,
    center_x: float = 0.0,
    center_y: float = 0.0,
    center_z: float = 0.0,
    size_x: float = 25.0,
    size_y: float = 25.0,
    size_z: float = 25.0,
    exhaustiveness: int = 8,
    num_modes: int = 9,
    cnn_scoring: str = "rescore",  # "none", "rescore", or "refinement"
    output_dir: str = None,
) -> Dict[str, Any]:
    """
    Run GNINA docking of a ligand against a receptor.

    Args:
        ligand_sdf_path: Path to the ligand SDF file
        receptor_pdb_path: Path to the receptor PDB file
        center_x/y/z: Center of the search box (Å)
        size_x/y/z: Dimensions of the search box (Å)
        exhaustiveness: Search exhaustiveness (higher = more thorough but slower)
        num_modes: Number of binding poses to generate
        cnn_scoring: CNN scoring mode — "rescore" uses CNN to re-rank Vina poses
        output_dir: Isolated output directory

    Returns:
        Dict with docking results including poses and scores
    """
    if not is_gnina_available():
        return {
            "ok": False,
            "error": "GNINA binary not found. Download from https://github.com/gnina/gnina/releases and place in project root."
        }

    out_dir = output_dir or DOCKING_OUTPUT_DIR
    os.makedirs(out_dir, exist_ok=True)
    output_sdf = os.path.join(out_dir, "docked_poses.sdf")
    log_path = os.path.join(out_dir, "docking_log.txt")

    cmd = [
        GNINA_PATH,
        "--receptor", receptor_pdb_path,
        "--ligand", ligand_sdf_path,
        "--center_x", str(center_x),
        "--center_y", str(center_y),
        "--center_z", str(center_z),
        "--size_x", str(size_x),
        "--size_y", str(size_y),
        "--size_z", str(size_z),
        "--exhaustiveness", str(exhaustiveness),
        "--num_modes", str(num_modes),
        "--cnn_scoring", cnn_scoring,
        "--out", output_sdf,
        "--log", log_path,
    ]

    logger.info(f"Running GNINA: {' '.join(cmd)}")

    try:
        result = subprocess.run(  # nosec B603
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
        )

        if result.returncode != 0:
            logger.error(f"GNINA failed: {result.stderr}")
            return {"ok": False, "error": f"GNINA exited with code {result.returncode}: {result.stderr[:500]}"}

        # Parse docking results from log
        poses = _parse_gnina_log(log_path)

        return {
            "ok": True,
            "output_sdf": output_sdf,
            "log_path": log_path,
            "poses": poses,
            "num_poses": len(poses),
        }

    except subprocess.TimeoutExpired:
        logger.error("GNINA docking timed out (5 min)")
        return {"ok": False, "error": "Docking timed out after 5 minutes"}
    except Exception as e:
        logger.error(f"GNINA docking error: {e}")
        return {"ok": False, "error": str(e)}


def _parse_gnina_log(log_path: str) -> List[Dict[str, Any]]:
    """Parse GNINA log file to extract pose scores."""
    poses = []
    if not os.path.exists(log_path):
        return poses

    try:
        with open(log_path) as f:
            in_table = False
            for line in f:
                line = line.strip()
                if line.startswith("mode"):
                    in_table = True
                    continue
                if in_table and line and line[0].isdigit():
                    parts = line.split()
                    if len(parts) >= 4:
                        poses.append({
                            "mode": int(parts[0]),
                            "affinity_kcal": float(parts[1]),
                            "cnn_score": float(parts[2]) if len(parts) > 2 else None,
                            "cnn_affinity": float(parts[3]) if len(parts) > 3 else None,
                        })
    except Exception as e:
        logger.warning(f"Error parsing GNINA log: {e}")

    return poses


def autobox_from_ligand(
    receptor_pdb_path: str,
    ligand_resname: str,
    padding: float = 4.0,
) -> Dict[str, float]:
    """
    Calculate docking box centered on an existing ligand in the receptor PDB.
    Useful for re-docking or docking new ligands into a known binding site.
    """
    try:
        from Bio.PDB import PDBParser
        parser = PDBParser(QUIET=True)
        struct = parser.get_structure("receptor", receptor_pdb_path)

        coords = []
        for model in struct:
            for chain in model:
                for residue in chain:
                    if residue.get_resname().strip() == ligand_resname.upper():
                        for atom in residue.get_atoms():
                            coords.append(atom.get_coord())

        if not coords:
            raise ValueError(f"Ligand '{ligand_resname}' not found in receptor PDB")

        import numpy as np
        coords = np.array(coords)
        center = coords.mean(axis=0)
        extent = coords.max(axis=0) - coords.min(axis=0) + 2 * padding

        return {
            "center_x": float(center[0]),
            "center_y": float(center[1]),
            "center_z": float(center[2]),
            "size_x": float(extent[0]),
            "size_y": float(extent[1]),
            "size_z": float(extent[2]),
        }
    except Exception as e:
        logger.error(f"Autobox calculation failed: {e}")
        return {
            "center_x": 0.0, "center_y": 0.0, "center_z": 0.0,
            "size_x": 25.0, "size_y": 25.0, "size_z": 25.0,
        }
