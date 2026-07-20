import pytest
import sys
import os

os.environ.setdefault("FLASK_SECRET_KEY", "kinetic-sketch-pytest-secret-key")
os.environ.setdefault("MODEL_DEVICE", "cpu")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))

@pytest.fixture(autouse=True)
def clear_rate_limits():
    try:
        from app.main import test_login_attempts
        test_login_attempts.clear()
    except Exception:
        pass
