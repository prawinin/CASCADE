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

    def forward(self, coords: torch.Tensor, node_features: torch.Tensor) -> torch.Tensor:
        """
        Forward pass: Predict atomic fluctuations from 3D structure.
        
        Args:
            coords: Conformer Cartesian coordinates tensor, shape (N, 3)
            node_features: Positional one-hot encoded element array, shape (N, 13)
        
        Returns:
            variance_predictions: Positive variance tensor, shape (N, 2)
        """
        N = coords.size(0)
        if N == 0:
            return torch.zeros((0, 2), dtype=torch.float32)

        # 1. Embed node element features
        h = F.relu(self.node_embed(node_features))  # Shape: (N, embed_dim)

        # 2. Compute pairwise Euclidean distances (Translation & Rotation Invariant)
        # Coordinates broadcasting: (N, 1, 3) - (1, N, 3) -> (N, N, 3)
        diffs = coords.unsqueeze(1) - coords.unsqueeze(0)
        dists = torch.norm(diffs, p=2, dim=-1)  # Shape: (N, N)

        # 3. Compute adjacency matrix using Gaussian Radial Basis Function (RBF)
        A = torch.exp(-self.gamma * (dists ** 2))  # Shape: (N, N)

        # Normalize adjacency for stable spatial neighborhood aggregation
        row_sums = A.sum(dim=1, keepdim=True) + 1e-6
        A_norm = A / row_sums

        # Aggregate neighborhood embeddings
        h_agg = A_norm @ h  # Shape: (N, embed_dim)

        # 4. Compute distance to center of mass (Translation & Rotation Invariant feature)
        com = coords.mean(dim=0, keepdim=True)  # Shape: (1, 3)
        dist_to_com = torch.norm(coords - com, p=2, dim=-1, keepdim=True)  # Shape: (N, 1)

        # 5. Concatenate local features, neighborhood aggregated features, and distance to center of mass
        combined = torch.cat([h, h_agg, dist_to_com], dim=-1)  # Shape: (N, embed_dim * 2 + 1)

        # 6. Predict and enforce positive atomic variance values
        raw_preds = self.predictor(combined)
        predictions = F.softplus(raw_preds)  # Enforce non-negativity
        
        return predictions
