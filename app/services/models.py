import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import List
from rdkit import Chem

# Common organic & bio-elements vocabulary mapping for GNN node arrays
ELEMENT_VOCAB: List[str] = ['H', 'C', 'N', 'O', 'P', 'S', 'F', 'Cl', 'Br', 'I', 'B', 'Si']

def get_one_hot_nodes(mol: Chem.Mol) -> torch.Tensor:
    """
    Converts RDKit molecular elements into one-hot encoded PyTorch node features.
    
    Creates a one-hot encoding for each atom in the molecule. Unknown elements
    are encoded as all-zeros in the last dimension.
    
    Args:
        mol: RDKit Mol object
    
    Returns:
        torch.Tensor of shape (N, 13) with one-hot encoded atom types
    """
    nodes = []
    for atom in mol.GetAtoms():
        sym = atom.GetSymbol()
        vector = [0.0] * (len(ELEMENT_VOCAB) + 1)
        if sym in ELEMENT_VOCAB:
            vector[ELEMENT_VOCAB.index(sym)] = 1.0
        else:
            vector[-1] = 1.0
        nodes.append(vector)
    return torch.tensor(nodes, dtype=torch.float32)


class MDRepoPredictor(nn.Module):
    """
    Fast-inference rotation- and translation-invariant PyTorch neural network.
    
    Processes absolute 3D Cartesian coordinates and one-hot node features
    to predict simulated Root Mean Square Fluctuation (RMSF) / atomic variances
    at 10 ns and 1 µs marks based on MDRepo open trajectory benchmarks.
    
    Architecture:
    - Node embedding layer (13 → embed_dim)
    - Gaussian RBF adjacency computation (translation & rotation invariant)
    - Neighborhood aggregation
    - Distance-to-center-of-mass feature
    - MLP prediction head (2 outputs per atom)
    """
    def __init__(self, node_dim: int = 13, embed_dim: int = 32):
        """
        Initialize MDRepo predictor network.
        
        Args:
            node_dim: Dimension of input node features (one-hot element encoding)
            embed_dim: Dimension of node embedding layer
        """
        super().__init__()
        # Node element embedding
        self.node_embed = nn.Linear(node_dim, embed_dim)
        
        # Radial basis function distance weight parameter
        self.gamma = nn.Parameter(torch.tensor(0.5, dtype=torch.float32))
        
        # Prediction head
        self.predictor = nn.Sequential(
            nn.Linear(embed_dim * 2 + 1, 64),
            nn.ReLU(),
            nn.Linear(64, 32),
            nn.ReLU(),
            nn.Linear(32, 2)  # Predictions: [variance_10ns, variance_1us]
        )

    def forward(self, coords: torch.Tensor, node_features: torch.Tensor = None) -> torch.Tensor:
        """
        Forward pass: Predict atomic fluctuations from 3D structure.
        Supports both Taipy single-conformer coordinates (N, 3) and batched coords (B, N, 3) from tests.
        
        Args:
            coords: Conformer Cartesian coordinates tensor, shape (N, 3) or (B, N, 3)
            node_features: Positional one-hot encoded element array, shape (N, 13) or (B, N, 13), optional
        
        Returns:
            variance_predictions: Positive variance tensor, shape (N, 2) or (B, N, 2)
        """
        is_batched = False
        if coords.ndim == 3:
            is_batched = True
            batch_size, N, _ = coords.shape
            if batch_size == 0 or N == 0:
                return torch.zeros((batch_size, N, 2) if N > 0 else (batch_size, 0, 2), dtype=torch.float32)
            coords_flat = coords.view(-1, 3)
        else:
            coords_flat = coords
            N = coords.size(0)
            batch_size = 1

        if N == 0 or coords_flat.size(0) == 0:
            if is_batched:
                return torch.zeros((batch_size, N, 2), dtype=torch.float32)
            return torch.zeros((0, 2), dtype=torch.float32)

        # Generate default node features (assuming all carbon atoms) if not provided
        if node_features is None:
            total_atoms = coords_flat.size(0)
            node_features_flat = torch.zeros((total_atoms, 13), dtype=torch.float32, device=coords.device)
            node_features_flat[:, 1] = 1.0  # ELEMENT_VOCAB index 1 represents Carbon ('C')
        else:
            if is_batched and node_features.ndim == 3:
                node_features_flat = node_features.view(-1, 13)
            else:
                node_features_flat = node_features

        # 1. Embed node element features
        h = F.relu(self.node_embed(node_features_flat))  # Shape: (total_atoms, embed_dim)

        # 2. Compute pairwise Euclidean distances within each separate batch item
        if is_batched:
            coords_reshaped = coords_flat.view(batch_size, N, 3)
            h_reshaped = h.view(batch_size, N, -1)
            
            diffs = coords_reshaped.unsqueeze(2) - coords_reshaped.unsqueeze(1)  # (B, N, N, 3)
            dists = torch.norm(diffs, p=2, dim=-1)  # (B, N, N)
            
            A = torch.exp(-self.gamma * (dists ** 2))  # (B, N, N)
            row_sums = A.sum(dim=2, keepdim=True) + 1e-6
            A_norm = A / row_sums
            
            h_agg = torch.bmm(A_norm, h_reshaped)  # (B, N, embed_dim)
            
            com = coords_reshaped.mean(dim=1, keepdim=True)  # (B, 1, 3)
            dist_to_com = torch.norm(coords_reshaped - com, p=2, dim=-1, keepdim=True)  # (B, N, 1)
            
            combined = torch.cat([h_reshaped, h_agg, dist_to_com], dim=-1)  # (B, N, embed_dim * 2 + 1)
            raw_preds = self.predictor(combined)
            predictions = F.softplus(raw_preds)  # (B, N, 2)
            return predictions
        else:
            # Single sample/flattened coordinates of shape (N, 3)
            diffs = coords_flat.unsqueeze(1) - coords_flat.unsqueeze(0)
            dists = torch.norm(diffs, p=2, dim=-1)  # (N, N)
            
            A = torch.exp(-self.gamma * (dists ** 2))  # (N, N)
            row_sums = A.sum(dim=1, keepdim=True) + 1e-6
            A_norm = A / row_sums
            
            h_agg = A_norm @ h  # Shape: (N, embed_dim)
            
            com = coords_flat.mean(dim=0, keepdim=True)  # (1, 3)
            dist_to_com = torch.norm(coords_flat - com, p=2, dim=-1, keepdim=True)  # (N, 1)
            
            combined = torch.cat([h, h_agg, dist_to_com], dim=-1)  # (N, embed_dim * 2 + 1)
            raw_preds = self.predictor(combined)
            predictions = F.softplus(raw_preds)  # Enforce non-negativity
            return predictions
