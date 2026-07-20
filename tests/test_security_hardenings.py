import pytest
import json
import io
import gzip
import os
import sqlite3
from unittest.mock import Mock, patch
from app.main import flask_app, DB_USERS_PATH

@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    flask_app.config["SECRET_KEY"] = "test-secret-key-security"

    def _cleanup():
        if os.path.exists(DB_USERS_PATH):
            try:
                conn = sqlite3.connect(DB_USERS_PATH)
                conn.cursor().execute("DELETE FROM users WHERE username LIKE 'sec_%' OR username LIKE 'owner%' OR username LIKE 'upload%'")
                conn.commit()
                conn.close()
            except Exception:
                pass

    _cleanup()
    with flask_app.test_client() as client:
        yield client
    _cleanup()

def test_path_traversal_prevention(client):
    # Register and login
    client.post("/api/auth/register", json={"username": "sec_user1", "password": "password12345"})
    client.post("/api/auth/login", json={"username": "sec_user1", "password": "password12345"})

    # Attempt download with invalid/traversal job_id
    res = client.get("/api/download/../etc/passwd/sdf")
    assert res.status_code in (400, 404)

    res = client.get("/api/download/invalid-uuid-format/sdf")
    assert res.status_code == 400

def test_task_ownership_enforcement(client):
    # User 1 registers and logs in
    client.post("/api/auth/register", json={"username": "owner1", "password": "password12345"})
    client.post("/api/auth/login", json={"username": "owner1", "password": "password12345"})

    queued = Mock(id="ownership-task-id")
    pending = Mock(state="PENDING", result=None, info=None)
    with patch("app.main._redis_available", return_value=True), \
         patch("app.tasks.run_3d_optimization_task.delay", return_value=queued), \
         patch("celery.result.AsyncResult", return_value=pending):
        res = client.post("/api/tasks/submit", json={"task_type": "optimize_3d", "params": {"smiles": "CCO"}})
        assert res.status_code == 200
        task_id = json.loads(res.data)["task_id"]

        res = client.get(f"/api/tasks/status/{task_id}")
        assert res.status_code == 200

    # User 2 logs in
    client.post("/api/auth/logout")
    client.post("/api/auth/register", json={"username": "owner2", "password": "password12345"})
    client.post("/api/auth/login", json={"username": "owner2", "password": "password12345"})

    # User 2 tries to check status of User 1's task
    res = client.get(f"/api/tasks/status/{task_id}")
    assert res.status_code == 403
    assert b"Access forbidden" in res.data

    # User 2 tries to cancel User 1's task
    res = client.delete(f"/api/tasks/cancel/{task_id}")
    assert res.status_code == 403

def test_pdb_upload_security_checks(client):
    client.post("/api/auth/register", json={"username": "upload_user", "password": "password12345"})
    client.post("/api/auth/login", json={"username": "upload_user", "password": "password12345"})

    # 1. Non-PDB content should be rejected
    data = {"file": (io.BytesIO(b"NOT A PDB FILE"), "test.pdb")}
    res = client.post("/api/pdb/upload", data=data, content_type="multipart/form-data")
    assert res.status_code == 400
    assert b"Invalid file content" in res.data

    # 2. Decompressed zip-bomb (>10 MB) should be rejected
    large_stream = io.BytesIO()
    with gzip.GzipFile(fileobj=large_stream, mode="wb") as gz:
        gz.write(b"HEADER    TEST PDB\n" + b"ATOM      1  N   ALA A   1       0.000   0.000   0.000  1.00 10.00           N\n" * 200000)
    large_stream.seek(0)

    data = {"file": (large_stream, "bomb.pdb.gz")}
    res = client.post("/api/pdb/upload", data=data, content_type="multipart/form-data")
    assert res.status_code == 400
    assert b"exceeds limit" in res.data or b"too many" in res.data

def test_login_rate_limiting(client):
    from app.main import test_login_attempts
    test_login_attempts.clear()
    # Attempt 5 rapid logins from the same client IP
    for i in range(5):
        client.post("/api/auth/login", json={"username": "nonexistent", "password": "wrong"})

    # 6th attempt should return 429 Too Many Requests
    res = client.post("/api/auth/login", json={"username": "nonexistent", "password": "wrong"})
    assert res.status_code == 429
    assert b"Too many login attempts" in res.data


def test_liveness_and_readiness(client):
    live = client.get("/health/live")
    assert live.status_code == 200
    assert live.get_json()["status"] == "live"

    with patch("app.main._redis_available", return_value=False):
        not_ready = client.get("/health/ready")
    assert not_ready.status_code == 503
    assert not_ready.get_json()["checks"]["redis"] is False

    with patch("app.main._redis_available", return_value=True):
        ready = client.get("/health/ready")
    assert ready.status_code == 200
    assert ready.get_json()["status"] == "ready"
