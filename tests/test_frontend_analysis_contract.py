from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_unified_input_has_a_real_analysis_bridge():
    sketch = (PROJECT_ROOT / "app/static/sketch.js").read_text(encoding="utf-8")
    page = (PROJECT_ROOT / "app/gui/index.html").read_text(encoding="utf-8")

    assert "window.submitSmilesFromExternal = submitSmilesAnalysis;" in sketch
    assert 'fetch("/api/analyze_smiles"' in sketch
    assert "await renderSmilesDirect(d.smiles" in page
    assert "await renderSmilesDirect(val)" in page


def test_removed_smiles_input_is_not_referenced():
    sketch = (PROJECT_ROOT / "app/static/sketch.js").read_text(encoding="utf-8")

    assert "visible_smiles_input" not in sketch


def test_frontend_cache_version_matches_fixed_bundle():
    page = (PROJECT_ROOT / "app/gui/index.html").read_text(encoding="utf-8")

    assert '<script src="/static/sketch.js?v=21"></script>' in page
