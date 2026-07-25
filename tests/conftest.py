import pytest
import sys
import os

os.environ.setdefault("FLASK_SECRET_KEY", "kinetic-sketch-pytest-secret-key")
os.environ.setdefault("MODEL_DEVICE", "cpu")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

@pytest.fixture(autouse=True)
def clear_rate_limits():
    # Do not import the application just to service lightweight tests. Test
    # modules that exercise Flask import app.main during collection, before
    # this fixture runs, so their limiter state is still reset as intended.
    main_module = sys.modules.get("app.main")
    if main_module is not None:
        main_module.test_login_attempts.clear()
