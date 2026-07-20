import pytest
from unittest.mock import patch
from app.main import flask_app

@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    flask_app.secret_key = "test-secret-key-12345"
    with flask_app.test_client() as client:
        yield client

@patch("app.main._redis_available")
def test_browser_contract_workflow(mock_redis_available, client, tmp_path):
    """
    Tests the exact sequence of endpoints as executed by sketch.js:
    Login -> Analyze -> Task Submit -> Task Status -> Download
    """
    mock_redis_available.return_value = True

    # 1. Register & Login
    res = client.post("/api/auth/register", json={"username": "test_contract_user", "password": "password12345"})
    res = client.post("/api/auth/login", json={"username": "test_contract_user", "password": "password12345"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["ok"] is True
    
    # Check session
    res = client.get("/api/auth/me")
    assert res.status_code == 200
    data = res.get_json()
    assert data["user"]["username"] == "test_contract_user"
    
    import uuid
    job_id = str(uuid.uuid4())

    # 2. Analyze SMILES
    res = client.post("/api/analyze_smiles", json={"smiles": "C", "job_id": job_id})
    assert res.status_code == 200
    assert res.get_json()["ok"] is True

    # 3. Download the generated SDF for rendering
    res = client.get(f"/api/download/{job_id}/sdf")
    assert res.status_code == 200
    assert b"V2000" in res.data or b"END" in res.data
    
    # 4. Submit Compute Task (optimize_3d)
    with patch("app.tasks.run_3d_optimization_task.delay") as mock_delay:
        class MockAsyncResult:
            def __init__(self, task_id):
                self.id = task_id
            @property
            def state(self):
                return "SUCCESS"
            @property
            def result(self):
                return {"ok": True, "job_id": job_id}
            def get(self, timeout=None):
                return {"ok": True, "job_id": job_id}
                
        mock_delay.return_value = MockAsyncResult("fake-task-id")
        
        res = client.post("/api/tasks/submit", json={
            "task_type": "optimize_3d",
            "params": {"smiles": "C", "force_field": "MMFF94"},
            "job_id": job_id
        })
        assert res.status_code == 200
        data = res.get_json()
        assert data["ok"] is True
        task_id = data["task_id"]
        assert isinstance(task_id, str)
        
        # 5. Check Task Status
        with patch("celery.result.AsyncResult", return_value=MockAsyncResult(task_id)):
            res = client.get(f"/api/tasks/status/{task_id}")
            assert res.status_code == 200
            status_data = res.get_json()
            assert status_data["status"] == "SUCCESS"
