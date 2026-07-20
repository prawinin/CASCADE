import pytest
import torch
from app.services.models import get_predictor

def test_model_loading_and_prediction():
    # Load model securely (singleton)
    model = get_predictor()
    assert model is not None
    
    # Run prediction on mock positions and features
    device = next(model.parameters()).device
    test_pos = torch.randn(5, 3).to(device)
    test_feats = torch.zeros(5, 13).to(device)
    test_feats[:, 1] = 1.0  # carbon
    
    # Check predictions output
    with torch.no_grad():
        preds = model(test_pos, test_feats)
        
    assert "rmsf" in preds
    assert "sasa" in preds
    assert "bfactor" in preds
    assert "charge" in preds
    assert "homo_lumo_gap" in preds
    
    assert preds["rmsf"].shape == (5, 3)
    assert preds["sasa"].shape == (5,)
    assert preds["bfactor"].shape == (5,)
    assert preds["charge"].shape == (5,)

def test_model_fail_closed_on_missing_weights(tmp_path, monkeypatch):
    # Set WEIGHTS_PATH to a non-existent path
    fake_path = str(tmp_path / "non_existent.pt")
    monkeypatch.setattr("app.services.models.WEIGHTS_PATH", fake_path)
    
    # Reset singleton to force reload
    monkeypatch.setattr("app.services.models._predictor_instance", None)
    
    with pytest.raises(FileNotFoundError):
        get_predictor()

def test_model_fail_closed_on_invalid_hash(tmp_path, monkeypatch):
    # Create a corrupted weights file
    corrupt_file = tmp_path / "corrupted_weights.pt"
    corrupt_file.write_text("corrupted content")
    
    monkeypatch.setattr("app.services.models.WEIGHTS_PATH", str(corrupt_file))
    monkeypatch.setattr("app.services.models._predictor_instance", None)
    
    with pytest.raises(ValueError, match="Checkpoint SHA-256 mismatch"):
        get_predictor()
