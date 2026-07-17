import os
import sys
import unittest
import json

# Ensure parent paths are configured for imports
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "app"))
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app.main import flask_app
from app.tasks import celery_app
from app.tasks.task_schemas import TaskSubmitSchema
from marshmallow import ValidationError

# Force Celery to run tasks synchronously for unit testing without Redis connection
celery_app.conf.update(
    task_always_eager=True,
    task_eager_propagates=True,
    task_store_eager_result=True,
    broker_url='memory://',
    result_backend='cache+memory://'
)
celery_app._backend = celery_app._get_backend()

class TestCeleryTasks(unittest.TestCase):
    def setUp(self):
        self.app = flask_app.test_client()
        self.app.testing = True

    def test_task_schema_validation(self):
        schema = TaskSubmitSchema()
        
        # Valid cases
        valid_opt = {"task_type": "optimize_3d", "params": {"smiles": "CCO"}}
        data = schema.load(valid_opt)
        schema.validate_params(data)
        self.assertEqual(data["task_type"], "optimize_3d")

        valid_profile = {
            "task_type": "interaction_profile",
            "params": {
                "smiles": "CCO",
                "pdb_id": "1OPJ",
                "ligand_resname": "STI"
            }
        }
        data = schema.load(valid_profile)
        schema.validate_params(data)

        # Invalid cases
        invalid_type = {"task_type": "invalid_type", "params": {}}
        with self.assertRaises(ValidationError):
            schema.load(invalid_type)

        invalid_params = {"task_type": "optimize_3d", "params": {"invalid_key": "val"}}
        data = schema.load(invalid_params)
        with self.assertRaises(ValidationError):
            schema.validate_params(data)

    def test_run_3d_optimization_task_direct(self):
        from app.tasks import run_3d_optimization_task
        res = run_3d_optimization_task.apply(args=("CC",)).get()
        
        self.assertEqual(res["smiles"], "CC")
        self.assertIn("predictions", res)
        self.assertIn("adme", res)
        self.assertIn("files", res)
        self.assertEqual(res["files"]["sdf"], "molecule.sdf")

    def test_strategy_pattern_backends(self):
        from app.tasks import get_compute_backend
        from app.tasks.compute_tasks import LocalOpenMMBackend, RemoteHTTPBackend, CloudLambdaBackend

        # Local
        os.environ["COMPUTE_BACKEND_TYPE"] = "local"
        backend = get_compute_backend()
        self.assertIsInstance(backend, LocalOpenMMBackend)
        res_local = backend.run_md("molecule.sdf", 500)
        self.assertTrue(res_local.ok)
        self.assertIn("trajectory_pdb", res_local.files)

        # Remote
        os.environ["COMPUTE_BACKEND_TYPE"] = "remote"
        backend = get_compute_backend()
        self.assertIsInstance(backend, RemoteHTTPBackend)
        res_remote = backend.run_md("molecule.sdf", 1000)
        self.assertTrue(res_remote.ok)

        # Cloud
        os.environ["COMPUTE_BACKEND_TYPE"] = "cloud"
        backend = get_compute_backend()
        self.assertIsInstance(backend, CloudLambdaBackend)
        res_cloud = backend.run_md("molecule.sdf", 200)
        self.assertTrue(res_cloud.ok)

        # Clean up
        if "COMPUTE_BACKEND_TYPE" in os.environ:
            del os.environ["COMPUTE_BACKEND_TYPE"]

    def test_api_endpoints_eager(self):
        # 1. Test Task Submission
        payload = {
            "task_type": "optimize_3d",
            "params": {"smiles": "C"}
        }
        res = self.app.post("/api/tasks/submit", json=payload)
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertTrue(data.get("ok"))
        self.assertIn("task_id", data)
        self.assertIn("estimated_time", data)

        task_id = data["task_id"]

        # 2. Test Task Status (since it is eager/completed, it should return SUCCESS status)
        res_status = self.app.get(f"/api/tasks/status/{task_id}")
        self.assertEqual(res_status.status_code, 200)
        status_data = json.loads(res_status.data)
        self.assertEqual(status_data["status"], "SUCCESS")
        self.assertIsNotNone(status_data["result"])
        self.assertEqual(status_data["result"]["smiles"], "C")

        # 3. Test Task Cancel/Revoke
        res_cancel = self.app.delete(f"/api/tasks/cancel/{task_id}")
        self.assertEqual(res_cancel.status_code, 200)
        cancel_data = json.loads(res_cancel.data)
        self.assertTrue(cancel_data["ok"])

if __name__ == "__main__":
    unittest.main()
