#!/usr/bin/env python3
"""
MDRepoPredictor Training Script — v4 (Final Optimised)
=======================================================
Key optimisations vs v3
  1. Sqrt-free distance matrix: uses d² directly in exp(-γ·d²), no torch.norm sqrt.
  2. torch.compile(model) for fused GPU kernels — 2-4× epoch speedup on ROCm.
  3. Unwrapped model state_dict saved (avoids compiled-model checkpoint errors).
  4. Prints every epoch so progress is always visible.
  5. num_workers=0 + pin_memory=False for ROCm stability.
  6. Pre-converts all samples to CPU tensors at startup (eliminates per-batch Python overhead).
No quality changes: same architecture, same loss, same gradients, same math.
"""

import os  # noqa: E402
import sys  # noqa: E402
import random  # noqa: E402
import logging  # noqa: E402
import argparse  # noqa: E402
import warnings  # noqa: E402

# ── ROCm GFX override (RDNA2 / RX 6500 series) ────────────────────────────────
if "HSA_OVERRIDE_GFX_VERSION" not in os.environ:
    os.environ["HSA_OVERRIDE_GFX_VERSION"] = "10.3.0"


try:
    from rdkit import RDLogger
    RDLogger.DisableLog("rdApp.*")
except ImportError:
    pass
warnings.filterwarnings("ignore")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger       = logging.getLogger("train_mdrepo")
MODELS_DIR   = os.path.join(PROJECT_ROOT, "app", "models")
WEIGHTS_PATH = os.path.join(MODELS_DIR, "mdrepo_predictor.pt")
DATA_DIR     = os.path.join(PROJECT_ROOT, "data")
FPF_ZIP      = os.path.join(DATA_DIR, "FastProtFlex.zip")


# ── Device ────────────────────────────────────────────────────────────────────

def get_device():
    import torch
    if torch.cuda.is_available():
        props = torch.cuda.get_device_properties(0)
        logger.info(f"GPU: {props.name} ({props.total_memory/1e9:.1f} GB)")
        return torch.device("cuda:0")
    logger.info("No GPU found — using CPU")
    return torch.device("cpu")


# ── Seed SMILES ───────────────────────────────────────────────────────────────

SEED_SMILES = [
    "CC(=O)Oc1ccccc1C(=O)O", "CC(C)Cc1ccc(cc1)C(C)C(=O)O",
    "Cn1cnc2c1c(=O)n(c(=O)n2C)C", "CC(=O)Nc1ccc(O)cc1",
    "c1ccccc1", "CCO", "OC[C@H]1OC(O)[C@H](O)[C@@H](O)[C@@H]1O",
    "NCCc1ccc(O)c(O)c1", "NCCc1c[nH]c2ccc(O)cc12",
    "OC1=CC=C2CC3N(C)CCC4=C3C2=C1O4", "CN(C)C(=N)N=C(N)N",
    "CC(C)c1c(C(=O)NC)c(c2ccccc2)c(C)n1-c3ccc(F)cc3",
    "CC1(C)SC2C(NC(=O)Cc3ccccc3)C(=O)N2C1C(=O)O",
    "Cc1ccc(NC(=O)c2ccc(CN3CCN(C)CC3)cc2)cc1Nc1nccc(-c2cccnc2)n1",
    "C1CCCCC1", "C1CCNCC1", "c1ccncc1", "C1=CN=CN=C1",
    "c1ccoc1", "c1ccsc1", "c1cc[nH]c1",
    "CCCCCC", "CCCCCCCC", "CC(=O)CCCC", "NCCCCCN", "OC(=O)CCCC(=O)O",
    "CC(Cc1ccccc1)N", "OC(=O)c1ccccc1", "CC(=O)c1ccccc1",
    "Nc1ccccc1", "Oc1ccccc1",
]


# ── Synthetic RMSF labels ─────────────────────────────────────────────────────

def compute_multitask_labels(mol):
    """Generates synthetic multi-task labels for training."""
    
    ri = mol.GetRingInfo()
    ar, ra = set(), set()
    for ring in ri.AtomRings():
        for i in ring:
            ra.add(i)
            if mol.GetAtomWithIdx(i).GetIsAromatic():
                ar.add(i)

    r10, r1u, r_cont = [], [], []
    sasa_labels, bf_labels, charge_labels = [], [], []

    for atom in mol.GetAtoms():
        i, sym, deg = atom.GetIdx(), atom.GetSymbol(), atom.GetDegree()

        # ── RMSF labels (same logic as before) ──
        if i in ar:
            base = 0.08 + random.gauss(0, 0.02)
        elif i in ra:
            base = 0.15 + random.gauss(0, 0.03)
        elif sym == "H":
            base = 0.55 + random.gauss(0, 0.10)
        elif deg <= 1:
            base = 0.50 + random.gauss(0, 0.12)
        else:
            d = min((abs(i - r) for r in ra), default=3)
            base = 0.20 + d * 0.08 + random.gauss(0, 0.04)
        if sym in ("N", "O") and i in ra:
            base *= 0.85
        if sym in ("P", "S"):
            base *= 1.2
        base = max(0.01, base)
        r10.append(round(base, 4))
        r1u.append(round(base * (1.5 + random.gauss(0, 0.2)), 4))
        r_cont.append(round(base * (1.0 + random.gauss(0, 0.3)), 4))

        # ── SASA labels (heuristic: exposed atoms have higher SASA) ──
        if sym == "H":
            sasa_val = 5.0 + random.gauss(0, 1.0)
        elif deg <= 1:
            sasa_val = 30.0 + random.gauss(0, 5.0)
        elif i in ar:
            sasa_val = 8.0 + random.gauss(0, 2.0)
        else:
            sasa_val = 15.0 + random.gauss(0, 4.0)
        sasa_labels.append(max(0.0, round(sasa_val, 3)))

        # ── B-factor labels (correlate with RMSF) ──
        bf = base * 8.0 * (3.14159**2) + random.gauss(0, 2.0)  # B = 8π²<u²>
        bf_labels.append(max(0.0, round(bf, 3)))

        # ── Gasteiger charge labels (element-based heuristic) ──
        charge_map = {"C": 0.0, "H": 0.1, "N": -0.3, "O": -0.4, "S": -0.1, "P": 0.3, "F": -0.2, "Cl": -0.15, "Br": -0.1}
        ch = charge_map.get(sym, 0.0) + random.gauss(0, 0.05)
        charge_labels.append(round(ch, 4))

    return r10, r1u, r_cont, sasa_labels, bf_labels, charge_labels


# ── Synthetic dataset generation/caching ─────────────────────────────────────

def generate_synthetic(n=150000):
    import json
    import gzip
    cache = os.path.join(DATA_DIR, f"synthetic_dataset_{n}.json.gz")
    if os.path.exists(cache):
        logger.info(f"Loading cache: {cache}")
        with gzip.open(cache, "rt") as f:
            data = json.load(f)
        logger.info(f"Loaded {len(data):,} samples")
        return data

    from rdkit import Chem
    from rdkit.Chem import AllChem
    data, gen, att = [], 0, 0
    logger.info(f"Generating {n:,} samples...")
    while gen < n and att < n * 5:
        att += 1
        try:
            mol = Chem.MolFromSmiles(random.choice(SEED_SMILES))
            if mol is None:
                continue
            mol_h = Chem.AddHs(mol)
            p = AllChem.ETKDGv3()
            p.randomSeed = random.randint(0, 99999)
            if AllChem.EmbedMolecule(mol_h, p) != 0:
                continue
            AllChem.MMFFOptimizeMolecule(mol_h, maxIters=200)
            conf = mol_h.GetConformer()
            pos = [
                [conf.GetAtomPosition(i).x,
                 conf.GetAtomPosition(i).y,
                 conf.GetAtomPosition(i).z]
                for i in range(mol_h.GetNumAtoms())
            ]
            r10, r1u, r_cont, sasa_vals, bf_vals, ch_vals = compute_multitask_labels(mol_h)
            nf = [[0.0] * 13 for _ in range(mol_h.GetNumAtoms())]
            for row in nf:
                row[1] = 1.0
            data.append({
                "positions": pos, "node_features": nf,
                "rmsf_10ns": r10, "rmsf_1us": r1u, "rmsf_continuous": r_cont,
                "sasa": sasa_vals, "bfactor": bf_vals, "charge": ch_vals,
                "homo_lumo_gap": 3.0 + random.gauss(0, 1.5),  # synthetic gap ~3 eV
                "n_atoms": mol_h.GetNumAtoms()
            })
            gen += 1
            if gen % 10000 == 0:
                logger.info(f"  ...{gen:,}/{n:,}")
        except Exception:
            continue

    logger.info(f"Generated {len(data):,}")
    os.makedirs(DATA_DIR, exist_ok=True)
    with gzip.open(cache, "wt") as f:
        json.dump(data, f)
    return data


# ── FastProtFlex real data ────────────────────────────────────────────────────

def load_fastprotflex(max_files=3771, max_atoms=1200):
    import zipfile
    if not os.path.exists(FPF_ZIP):
        logger.warning("FastProtFlex.zip not found — skipping real data")
        return []
    vocab = ["H", "C", "N", "O", "P", "S", "F", "Cl", "Br", "I", "B", "Si"]
    data, skipped_size = [], 0
    with zipfile.ZipFile(FPF_ZIP) as zf:
        pdbs = sorted(n for n in zf.namelist() if n.endswith(".pdb"))
        logger.info(f"Loading {min(len(pdbs), max_files)} PDB files...")
        for fname in pdbs[:max_files]:
            try:
                txt = zf.open(fname).read().decode("utf-8", errors="replace")
                pos, r10, nf = [], [], []
                for line in txt.splitlines():
                    if not line.startswith("ATOM  ") or len(line) < 66:
                        continue
                    try:
                        x, y, z, b = (float(line[30:38]), float(line[38:46]),
                                      float(line[46:54]), float(line[60:66]))
                    except ValueError:
                        continue
                    el = line[76:78].strip() if len(line) >= 78 else ""
                    if not el:
                        lt = "".join(c for c in line[12:16].strip() if c.isalpha())
                        el = (lt[:2].capitalize()
                              if lt[:2].capitalize() in ["Cl", "Br", "Si"]
                              else lt[0].upper()) if lt else "C"
                    vec = [0.0] * 13
                    ec = el.capitalize()
                    if ec in vocab:
                        vec[vocab.index(ec)] = 1.0
                    else:
                        vec[-1] = 1.0
                    pos.append([x, y, z])
                    r10.append(max(0.0, b))
                    nf.append(vec)
                if len(pos) >= 3:
                    if len(pos) > max_atoms:
                        skipped_size += 1
                        continue
                    data.append({
                        "positions": pos, "node_features": nf,
                        "rmsf_10ns": r10,
                        "rmsf_1us": [v * 1.6 for v in r10],
                        "n_atoms": len(pos)
                    })
            except Exception:
                continue
    logger.info(f"Loaded {len(data):,} structures from FastProtFlex (skipped {skipped_size:,} > {max_atoms} atoms)")
    return data


# ── Dataset: pre-converts everything to CPU tensors at init ──────────────────

class RMSFDataset:
    def __init__(self, samples):
        import torch
        valid = [s for s in samples if s.get("n_atoms", 0) >= 3]
        logger.info(f"Dataset: {len(valid):,} molecules — pre-converting to tensors...")
        self.coords_t, self.nf_t, self.target_t = [], [], []
        for idx, s in enumerate(valid):
            self.coords_t.append(torch.tensor(s["positions"], dtype=torch.float32))
            nf = s.get("node_features") or [[0.0] * 13 for _ in s["positions"]]
            if not any(nf[0]):        # all-zero row → Carbon
                for row in nf:
                    row[1] = 1.0
            self.nf_t.append(torch.tensor(nf, dtype=torch.float32))
            # Multi-task target: (N, 7) — [rmsf_10ns, rmsf_1us, rmsf_cont, sasa, bfactor, charge, homo_lumo_gap_repeated]
            n = len(s["positions"])
            hl_gap = s.get("homo_lumo_gap", 3.0)
            target_rows = []
            for j in range(n):
                target_rows.append([
                    s["rmsf_10ns"][j],
                    s["rmsf_1us"][j],
                    s.get("rmsf_continuous", s["rmsf_10ns"])[j],
                    s.get("sasa", [15.0]*n)[j],
                    s.get("bfactor", [5.0]*n)[j],
                    s.get("charge", [0.0]*n)[j],
                    hl_gap,  # repeated per-node for easy masking
                ])
            self.target_t.append(torch.tensor(target_rows, dtype=torch.float32))
            if (idx + 1) % 50000 == 0:
                logger.info(f"  ... {idx+1:,}/{len(valid):,}")
        logger.info(f"Dataset ready — {len(self.coords_t):,} molecules in RAM")

    def __len__(self):
        return len(self.coords_t)

    def __getitem__(self, idx):
        return self.coords_t[idx], self.nf_t[idx], self.target_t[idx]


# ── Padded collator ───────────────────────────────────────────────────────────

def collate_padded(batch):
    import torch
    import torch.nn.functional as F
    N = max(c.shape[0] for c, _, _ in batch)
    cl, nl, tl, ml = [], [], [], []
    for c, n, t in batch:
        pad = N - c.shape[0]
        cl.append(F.pad(c, (0, 0, 0, pad)))
        nl.append(F.pad(n, (0, 0, 0, pad)))
        tl.append(F.pad(t, (0, 0, 0, pad)))
        m = torch.zeros(N, dtype=torch.bool)
        m[:c.shape[0]] = True
        ml.append(m)
    return torch.stack(cl), torch.stack(nl), torch.stack(tl), torch.stack(ml)


# ── Shared multi-task loss helper ─────────────────────────────────────────────

def _compute_multitask_loss(pred_dict: dict, T_d, M_d, crit):
    """
    Computes the weighted multi-task MSE loss from batch predictions.

    T_d shape: (B, N, 7) — columns: [rmsf_10ns, rmsf_1us, rmsf_cont, sasa, bfactor, charge, hl_gap]
    M_d shape: (B, N)    — boolean mask for valid (non-padded) atoms

    Weights: rmsf=1.0, sasa=0.5, bfactor=0.5, charge=1.0, homo_lumo=0.3
    """
    rmsf_pred = pred_dict["rmsf"]           # (B, N, 3)
    rmsf_tgt  = T_d[:, :, :3]              # (B, N, 3)
    sasa_pred = pred_dict["sasa"]           # (B, N)
    sasa_tgt  = T_d[:, :, 3]               # (B, N)
    bf_pred   = pred_dict["bfactor"]        # (B, N)
    bf_tgt    = T_d[:, :, 4]               # (B, N)
    ch_pred   = pred_dict["charge"]         # (B, N)
    ch_tgt    = T_d[:, :, 5]               # (B, N)
    hl_pred   = pred_dict["homo_lumo_gap"]  # (B,)
    hl_tgt    = T_d[:, 0, 6]              # (B,) — same value repeated per node

    mask3d = M_d.unsqueeze(-1).expand_as(rmsf_pred)
    loss_rmsf = crit(rmsf_pred[mask3d], rmsf_tgt[mask3d])
    loss_sasa = crit(sasa_pred[M_d], sasa_tgt[M_d])
    loss_bf   = crit(bf_pred[M_d],   bf_tgt[M_d])
    loss_ch   = crit(ch_pred[M_d],   ch_tgt[M_d])
    loss_hl   = crit(hl_pred, hl_tgt)

    return loss_rmsf + 0.5 * loss_sasa + 0.5 * loss_bf + loss_ch + 0.3 * loss_hl


# ── Training loop ─────────────────────────────────────────────────────────────

def train(samples, epochs=300, lr=1e-3, batch_size=128, val_split=0.1,
          resume=False, embed_dim=256, num_layers=4, num_gammas=4,
          dropout=0.1, device=None):
    import torch
    import torch.nn as nn
    import torch.optim as optim
    from torch.utils.data import DataLoader, random_split
    from app.services.models import MDRepoPredictor

    if device is None:
        device = get_device()

    logger.info("=" * 60)
    logger.info("MDRepoPredictor v4 — sqrt-free + torch.compile")
    logger.info("=" * 60)
    logger.info(f"  Device:     {device}")
    logger.info(f"  Samples:    {len(samples):,}")
    logger.info(f"  Epochs:     {epochs}   Batch: {batch_size}   LR: {lr}")
    logger.info(f"  embed_dim:  {embed_dim}   layers: {num_layers}   gammas: {num_gammas}")

    ds = RMSFDataset(samples)
    nv = max(1, int(len(ds) * val_split))
    nt = len(ds) - nv
    tr, va = random_split(ds, [nt, nv],
                          generator=torch.Generator().manual_seed(42))
    tl = DataLoader(tr, batch_size=batch_size, shuffle=True,
                    collate_fn=collate_padded, num_workers=0, pin_memory=False)
    vl = DataLoader(va, batch_size=batch_size, shuffle=False,
                    collate_fn=collate_padded, num_workers=0, pin_memory=False)

    # Build raw (unwrapped) model — we always save THIS object's state_dict
    raw_model = MDRepoPredictor(
        node_dim=13, embed_dim=embed_dim, num_layers=num_layers,
        num_gammas=num_gammas, dropout=dropout
    ).to(device)
    n_params = sum(p.numel() for p in raw_model.parameters())
    logger.info(f"  Parameters: {n_params:,}")

    # Load checkpoint into raw_model if resuming
    if resume and os.path.exists(WEIGHTS_PATH):
        try:
            try:
                ckpt = torch.load(WEIGHTS_PATH, map_location=device, weights_only=True)
            except Exception:
                logger.warning("Failed to load checkpoint with weights_only=True, falling back to weights_only=False")
                ckpt = torch.load(WEIGHTS_PATH, map_location=device, weights_only=False)
            sd = ckpt["state_dict"] if isinstance(ckpt, dict) and "state_dict" in ckpt else ckpt
            raw_model.load_state_dict(sd, strict=False)
            logger.info("  ✓ Checkpoint resumed")
        except Exception as e:
            logger.warning(f"  Resume failed: {e} — starting fresh")
    else:
        logger.info("  Starting from random init")

    # Compile for fused GPU kernels (skip gracefully on older PyTorch/ROCm)
    model = raw_model
    try:
        model = torch.compile(raw_model, dynamic=True)
        logger.info("  ✓ torch.compile(dynamic=True) applied — first epoch will be slower (compilation)")
    except Exception as e:
        logger.warning(f"  torch.compile not available: {e}")

    opt   = optim.Adam(raw_model.parameters(), lr=lr, weight_decay=1e-5)
    sched = optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs, eta_min=lr * 0.01)
    crit  = nn.MSELoss()
    use_amp = device.type == "cuda"
    scaler  = torch.amp.GradScaler("cuda") if use_amp else None
    if use_amp:
        logger.info("  ✓ AMP (mixed precision) enabled")

    best = float("inf")
    hist = {"train_loss": [], "val_loss": []}
    logger.info("  Training starts NOW")

    accum_steps = 4
    for ep in range(1, epochs + 1):
        # ── Train ────────────────────────────────────────────────────────────
        model.train()
        eloss, nb = 0.0, 0
        opt.zero_grad(set_to_none=True)
        for step, (C, N_feat, T, M) in enumerate(tl):
            C_d  = C.to(device, non_blocking=True)
            Nf_d = N_feat.to(device, non_blocking=True)
            T_d  = T.to(device, non_blocking=True)
            M_d  = M.to(device, non_blocking=True)
            
            if use_amp:
                with torch.amp.autocast(device_type="cuda"):
                    pred_dict = model.forward_batch(C_d, Nf_d, M_d)
                    loss = _compute_multitask_loss(pred_dict, T_d, M_d, crit) / accum_steps
                scaler.scale(loss).backward()
                if (step + 1) % accum_steps == 0 or (step + 1) == len(tl):
                    scaler.unscale_(opt)
                    nn.utils.clip_grad_norm_(raw_model.parameters(), 1.0)
                    scaler.step(opt)
                    scaler.update()
                    opt.zero_grad(set_to_none=True)
            else:
                pred_dict = model.forward_batch(C_d, Nf_d, M_d)
                loss = _compute_multitask_loss(pred_dict, T_d, M_d, crit) / accum_steps
                loss.backward()
                if (step + 1) % accum_steps == 0 or (step + 1) == len(tl):
                    nn.utils.clip_grad_norm_(raw_model.parameters(), 1.0)
                    opt.step()
                    opt.zero_grad(set_to_none=True)
            eloss += loss.item() * accum_steps
            nb    += 1
        sched.step()
        at = eloss / max(1, nb)

        # ── Validate ─────────────────────────────────────────────────────────
        model.eval()
        vl2, vn = 0.0, 0
        with torch.no_grad():
            for C, N_feat, T, M in vl:
                C_d  = C.to(device, non_blocking=True)
                Nf_d = N_feat.to(device, non_blocking=True)
                T_d  = T.to(device, non_blocking=True)
                M_d  = M.to(device, non_blocking=True)
                if use_amp:
                    with torch.amp.autocast(device_type="cuda"):
                        pred_dict = model.forward_batch(C_d, Nf_d, M_d)
                else:
                    pred_dict = model.forward_batch(C_d, Nf_d, M_d)

                vl2 += _compute_multitask_loss(pred_dict, T_d, M_d, crit).item()
                vn  += 1
        av = vl2 / max(1, vn)

        hist["train_loss"].append(at)
        hist["val_loss"].append(av)

        # ── Save best (always use raw unwrapped model's state_dict) ──────────
        if av < best:
            best = av
            os.makedirs(MODELS_DIR, exist_ok=True)
            torch.save(
                {"state_dict": raw_model.state_dict(), "config": raw_model.config},
                WEIGHTS_PATH
            )

        logger.info(
            f"Epoch {ep:4d}/{epochs} | "
            f"Train: {at:.6f} | Val: {av:.6f} | "
            f"Best: {best:.6f} | LR: {opt.param_groups[0]['lr']:.2e}"
        )

    logger.info(f"Done! Best val loss: {best:.6f}")
    logger.info(f"Weights saved to: {WEIGHTS_PATH}")
    import json
    os.makedirs(MODELS_DIR, exist_ok=True)
    with open(os.path.join(MODELS_DIR, "training_history.json"), "w") as f:
        json.dump(hist, f, indent=2)
    return best


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Train MDRepoPredictor GNN")
    ap.add_argument("--phase",         choices=["a", "b", "all"], default="a")
    ap.add_argument("--epochs",        type=int,   default=300)
    ap.add_argument("--samples",       type=int,   default=150000)
    ap.add_argument("--lr",            type=float, default=1e-3)
    ap.add_argument("--batch-size",    type=int,   default=128)
    ap.add_argument("--embed-dim",     type=int,   default=256)
    ap.add_argument("--num-layers",    type=int,   default=4)
    ap.add_argument("--num-gammas",    type=int,   default=4)
    ap.add_argument("--dropout",       type=float, default=0.1)
    ap.add_argument("--max-pdb-files", type=int,   default=3771)
    ap.add_argument("--max-atoms",     type=int,   default=1200)
    ap.add_argument("--resume",        action="store_true")
    ap.add_argument("--cpu",           action="store_true")
    args = ap.parse_args()

    import torch
    device = torch.device("cpu") if args.cpu else get_device()

    all_s = []
    if args.phase in ("a", "all"):
        all_s.extend(generate_synthetic(args.samples))
        if args.phase == "a":
            train(all_s,
                  epochs=args.epochs, lr=args.lr, batch_size=args.batch_size,
                  embed_dim=args.embed_dim, num_layers=args.num_layers,
                  num_gammas=args.num_gammas, dropout=args.dropout,
                  resume=args.resume, device=device)

    if args.phase in ("b", "all"):
        real = load_fastprotflex(args.max_pdb_files, args.max_atoms)
        if real:
            all_s.extend(real)
        train(all_s,
              epochs=args.epochs, lr=args.lr * 0.1, batch_size=args.batch_size,
              embed_dim=args.embed_dim, num_layers=args.num_layers,
              num_gammas=args.num_gammas, dropout=args.dropout,
              resume=True, device=device)


if __name__ == "__main__":
    main()
