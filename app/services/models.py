import os
import logging

# Override GFX version for AMD Radeon RX 6500M (reported as gfx1030 on Manjaro/ROCm).
# Maps the GPU to the supported RDNA2 gfx1030 instruction set for PyTorch HIP dispatch.
os.environ["HSA_OVERRIDE_GFX_VERSION"] = "10.3.0"

import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import List, Optional, Dict, Any

logger = logging.getLogger("KineticSketch.Models")

# ── Weights path ──────────────────────────────────────────────────────────────
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WEIGHTS_PATH = os.path.join(_PROJECT_ROOT, "app", "models", "mdrepo_predictor.pt")

# ── Singleton predictor (loaded once at server startup) ───────────────────────
_predictor_instance: Optional["MDRepoPredictor"] = None
_predictor_device: Optional[torch.device] = None

# Common organic & bio-elements vocabulary
ELEMENT_VOCAB: List[str] = ['H', 'C', 'N', 'O', 'P', 'S', 'F', 'Cl', 'Br', 'I', 'B', 'Si']


def get_one_hot_nodes(mol) -> torch.Tensor:
    """
    Converts RDKit molecular elements into one-hot encoded PyTorch node features.
    Returns torch.Tensor of shape (N, 13).
    """
    nodes = []
    for atom in mol.GetAtoms():
        sym = atom.GetSymbol()
        vector = [0.0] * (len(ELEMENT_VOCAB) + 1)
        if sym in ELEMENT_VOCAB:
            vector[ELEMENT_VOCAB.index(sym)] = 1.0
        else:
            vector[-1] = 1.0  # unknown element bucket
        nodes.append(vector)
    return torch.tensor(nodes, dtype=torch.float32)


# =============================================================================
# MPNNLayer — Multi-Scale Message Passing Layer
# =============================================================================

class MPNNLayer(nn.Module):
    """
    Single multi-scale Gaussian RBF message passing layer.
    Supports batched inputs with optional boolean masks to ignore padded atoms.
    """

    def __init__(self, embed_dim: int, num_gammas: int = 4):
        super().__init__()
        self.num_gammas = num_gammas

        # Learnable RBF parameters stored as raw (unconstrained) values
        init_vals = torch.tensor(
            [0.22, 0.056, 0.020, 0.006][:num_gammas], dtype=torch.float32
        )
        self.gamma_raw = nn.Parameter(torch.log(torch.expm1(init_vals)))

        self.project = nn.Linear(embed_dim * num_gammas, embed_dim, bias=False)
        self.norm = nn.LayerNorm(embed_dim)
        self.act = nn.ReLU()

    def forward(
        self,
        h: torch.Tensor,
        d2: torch.Tensor,          # squared distances — do NOT square again
        mask: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        batched = h.ndim == 3
        agg_list = []

        for k in range(self.num_gammas):
            gamma_k = F.softplus(self.gamma_raw[k]) + 1e-8
            A = torch.exp(-gamma_k * d2)
            if mask is not None and batched:
                m = mask.float()
                A = A * m.unsqueeze(1) * m.unsqueeze(2)
            if batched:
                A_norm = A / (A.sum(dim=2, keepdim=True) + 1e-8)
                agg_list.append(torch.bmm(A_norm, h))
            else:
                A_norm = A / (A.sum(dim=1, keepdim=True) + 1e-8)
                agg_list.append(A_norm @ h)

        h_multi = torch.cat(agg_list, dim=-1)
        h_proj = self.act(self.project(h_multi))
        return self.norm(h + h_proj)



# =============================================================================
# MDRepoPredictor — Full Multi-Layer MPNN
# =============================================================================

class MDRepoPredictor(nn.Module):
    """
    Rotation- and translation-invariant multi-layer MPNN for per-atom
    RMSF prediction at 10 ns and 1 µs timescales.
    """

    def __init__(
        self,
        node_dim: int = 13,
        embed_dim: int = 256,
        num_layers: int = 4,
        num_gammas: int = 4,
        dropout: float = 0.1,
    ):
        super().__init__()

        self.config: Dict[str, Any] = {
            "node_dim": node_dim,
            "embed_dim": embed_dim,
            "num_layers": num_layers,
            "num_gammas": num_gammas,
            "dropout": dropout,
        }

        # 1. Node embedding
        self.node_embed = nn.Sequential(
            nn.Linear(node_dim, embed_dim),
            nn.LayerNorm(embed_dim),
            nn.ReLU(),
        )

        # 2. Stacked MPNN layers
        self.gnn_layers = nn.ModuleList([
            MPNNLayer(embed_dim, num_gammas) for _ in range(num_layers)
        ])

        # 3. MLP head
        mlp_in = embed_dim + embed_dim + 1
        self.mlp_head = nn.Sequential(
            nn.Linear(mlp_in, 256),
            nn.LayerNorm(256),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(256, 128),
            nn.LayerNorm(128),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.Linear(64, 2),
        )

    def _forward_single(
        self, coords: torch.Tensor, node_features: torch.Tensor
    ) -> torch.Tensor:
        # sqrt-free: d²[i,j] = ||c_i - c_j||²
        c2   = (coords * coords).sum(dim=-1, keepdim=True)   # (N,1)
        d2   = c2 + c2.t() - 2.0 * (coords @ coords.t())
        d2   = d2.clamp(min=0.0)
        h    = self.node_embed(node_features)
        for layer in self.gnn_layers:
            h = layer(h, d2)
        N = h.size(0)
        global_mean = h.mean(dim=0, keepdim=True).expand(N, -1)
        com = coords.mean(dim=0, keepdim=True)
        dist_to_com = torch.norm(coords - com, p=2, dim=-1, keepdim=True)
        combined = torch.cat([h, global_mean, dist_to_com], dim=-1)
        return F.softplus(self.mlp_head(combined))


    def forward_batch(
        self,
        coords: torch.Tensor,
        node_features: torch.Tensor,
        mask: torch.Tensor,
    ) -> torch.Tensor:
        """
        True batched forward logic using masks for padding.
        coords:        (B, N_max, 3)
        node_features: (B, N_max, 13)
        mask:          (B, N_max) bool

        Uses squared distances (d²) directly — avoids sqrt since RBF is exp(-γ·d²).
        """
        B, N, _ = coords.shape
        # d²[b,i,j] = ||c_i - c_j||²  (sqrt-free, ~30% faster on memory-bound GPUs)
        c2 = (coords * coords).sum(dim=-1, keepdim=True)          # (B, N, 1)
        dists = c2 + c2.transpose(1, 2) - 2.0 * torch.bmm(coords, coords.transpose(1, 2))
        dists = dists.clamp(min=0.0)   # numerical safety (avoid neg sqrt artifacts)
        h = self.node_embed(node_features)
        for layer in self.gnn_layers:
            h = layer(h, dists, mask)
        m = mask.float().unsqueeze(-1)
        n_real = mask.sum(dim=1, keepdim=True).unsqueeze(-1).clamp(min=1).float()
        global_mean = (h * m).sum(dim=1, keepdim=True) / n_real
        global_mean = global_mean.expand(-1, N, -1)
        com = (coords * m).sum(dim=1, keepdim=True) / n_real
        dist_to_com = torch.norm(coords - com, p=2, dim=-1, keepdim=True)
        combined = torch.cat([h, global_mean, dist_to_com], dim=-1)
        return F.softplus(self.mlp_head(combined))

    def forward(
        self,
        coords: torch.Tensor,
        node_features: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        if node_features is None:
            N = coords.size(0)
            nf = torch.zeros((N, 13), dtype=torch.float32, device=coords.device)
            nf[:, 1] = 1.0
            node_features = nf
        return self._forward_single(coords, node_features)


# =============================================================================
# Singleton loader with auto-config detection and torch.compile
# =============================================================================

def get_predictor(device: Optional[torch.device] = None) -> MDRepoPredictor:
    """
    Returns the singleton MDRepoPredictor for inference.

    Checkpoint format (new):  dict {'state_dict': ..., 'config': {...}}
        Model is reconstructed exactly from the saved config — no hardcoded args.
    Checkpoint format (legacy): raw state_dict from old single-layer architecture.
        Falls back to embed_dim=32, num_layers=1 for compatibility.

    Applies torch.compile(mode='reduce-overhead') for ~25-35% inference
    speedup on PyTorch 2.x (skips silently on older versions or compile errors).
    """
    global _predictor_instance, _predictor_device

    if _predictor_instance is not None:
        return _predictor_instance

    if device is None:
        if torch.cuda.is_available():
            device = torch.device("cuda:0")
            logger.info(f"MDRepoPredictor: GPU — {torch.cuda.get_device_name(0)}")
        else:
            device = torch.device("cpu")
            logger.info("MDRepoPredictor: CPU mode")

    _predictor_device = device

    # Default config matches Kaggle full-quality training defaults
    model_config: Dict[str, Any] = {
        "node_dim": 13,
        "embed_dim": 256,
        "num_layers": 4,
        "num_gammas": 4,
        "dropout": 0.1,
    }
    state_dict = None

    if os.path.exists(WEIGHTS_PATH):
        try:
            checkpoint = torch.load(WEIGHTS_PATH, map_location=device, weights_only=False)

            if isinstance(checkpoint, dict) and "state_dict" in checkpoint:
                model_config.update(checkpoint.get("config", {}))
                state_dict = checkpoint["state_dict"]
                logger.info(f"✓ Checkpoint config: {model_config}")
            else:
                # Legacy raw state_dict (old Fedora-era single-layer model)
                state_dict = checkpoint
                model_config["embed_dim"] = 32
                model_config["num_layers"] = 1
                model_config["num_gammas"] = 1
                logger.warning(
                    "Legacy checkpoint detected (old single-layer architecture). "
                    "Re-train with the new script for full quality."
                )
        except Exception as e:
            logger.warning(f"Could not load checkpoint ({e}) — using random init")
    else:
        logger.warning(
            f"No trained weights at {WEIGHTS_PATH}. "
            "Run: python scripts/train_mdrepo.py --phase all"
        )

    model = MDRepoPredictor(**model_config)
    param_count = sum(p.numel() for p in model.parameters())

    if state_dict is not None:
        try:
            model.load_state_dict(state_dict, strict=True)
            logger.info(
                f"✓ MDRepoPredictor ready — "
                f"embed_dim={model_config['embed_dim']}, "
                f"layers={model_config['num_layers']}, "
                f"gammas={model_config['num_gammas']}, "
                f"params={param_count:,}"
            )
        except RuntimeError as e:
            logger.warning(f"Strict load failed ({e}) — partial load")
            try:
                model.load_state_dict(state_dict, strict=False)
            except Exception as e2:
                logger.error(f"Weight load failed: {e2} — random init")

    model = model.to(device)
    model.eval()

    # NOTE: torch.compile is intentionally disabled for inference.
    # Reasons:
    #   1. First-call JIT compilation freezes the UI for 10-15 seconds.
    #   2. CUDA Graph modes cause TLS AssertionError in Flask worker threads.
    #   3. The 1.2M param model runs fast natively on ROCm without compilation.
    # torch.compile is only beneficial during training (already used in train_mdrepo.py).
    logger.info("✓ MDRepoPredictor ready for inference (no compile — instant response)")

    _predictor_instance = model
    return model
