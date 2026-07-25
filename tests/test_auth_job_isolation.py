import pytest
import os
import json
import sqlite3
from app.main import flask_app, DB_USERS_PATH
from app.paths import JOBS_DIR

@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    flask_app.config["SECRET_KEY"] = "test-secret-key"

    def _cleanup():
        if os.path.exists(DB_USERS_PATH):
            try:
                conn = sqlite3.connect(DB_USERS_PATH)
                conn.cursor().execute("DELETE FROM users WHERE username LIKE 'testuser%' OR username LIKE 'sec_%' OR username LIKE 'owner%' OR username LIKE 'upload%'")
                conn.commit()
                conn.close()
            except Exception:
                pass

    _cleanup()
    with flask_app.test_client() as client:
        yield client
    _cleanup()

def test_public_routes_accessible(client):
    # 1. Root index.html must render non-empty valid HTML UI
    res = client.get("/")
    assert res.status_code == 200
    assert len(res.data) > 1000, "UI index.html must not be empty"
    assert b"KineticSketch" in res.data
    assert b"loginModal" in res.data or b"app" in res.data

    # 2. Static JavaScript bundle must render non-empty script content
    res = client.get("/static/sketch.js")
    assert res.status_code == 200
    assert len(res.data) > 1000, "UI sketch.js must not be empty"

    # 3. Static route must NOT expose workspace root files (e.g. molecule.sdf)
    res = client.get("/static/molecule.sdf")
    assert res.status_code == 404

    # 4. Health endpoint
    res = client.get("/health")
    assert res.status_code == 200

def test_protected_routes_require_auth(client):
    # Protected API should return 401
    res = client.post("/api/analyze_smiles", json={"smiles": "CCO"})
    assert res.status_code == 401
    assert b"Authentication required" in res.data

def test_auth_flow_and_job_isolation(client):
    # 1. Register a test user
    res = client.post("/api/auth/register", json={
        "username": "testuser_unique_1",
        "password": "testpassword123"
    })
    assert res.status_code == 200
    assert json.loads(res.data)["ok"] is True

    # Registering duplicate user should fail
    res = client.post("/api/auth/register", json={
        "username": "testuser_unique_1",
        "password": "testpassword123"
    })
    assert res.status_code == 400

    # 2. Login
    res = client.post("/api/auth/login", json={
        "username": "testuser_unique_1",
        "password": "testpassword123"
    })
    assert res.status_code == 200
    data = json.loads(res.data)
    assert data["ok"] is True
    user_id = data["user"]["id"]

    # Check session
    res = client.get("/api/auth/me")
    assert res.status_code == 200
    assert json.loads(res.data)["user"]["username"] == "testuser_unique_1"

    # 3. Analyze SMILES (this will create an isolated job directory)
    res = client.post("/api/analyze_smiles", json={"smiles": "CCO"})
    assert res.status_code == 200
    res_data = json.loads(res.data)
    assert res_data["ok"] is True
    job_id = res_data["job_id"]
    assert job_id is not None

    # Check that job directories exist and are properly scoped
    job_dir = os.path.join(JOBS_DIR, user_id, job_id)
    assert os.path.isdir(job_dir)
    assert os.path.isfile(os.path.join(job_dir, "outputs", "molecule.sdf"))
    assert os.path.isfile(os.path.join(job_dir, "outputs", "molecule.xyz"))
    assert os.path.isfile(os.path.join(job_dir, "outputs", "molecule.mol2"))
    assert os.path.isfile(os.path.join(job_dir, "outputs", "workspace_progress.json"))

    # 4. Download file securely
    res = client.get(f"/api/download/{job_id}/sdf")
    assert res.status_code == 200
    assert len(res.data) > 0

    # Logout
    client.post("/api/auth/logout")
    res = client.get("/api/auth/me")
    assert res.status_code == 401
