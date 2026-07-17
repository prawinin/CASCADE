# scratch/test_new_apis.py
import json
import unittest
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "app"))
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app.main import flask_app

class TestNewAPIs(unittest.TestCase):
    def setUp(self):
        self.app = flask_app.test_client()
        self.app.testing = True

    def test_canvas_to_smiles(self):
        payload = {
            "atoms": [
                {"id": 1, "x": 10.0, "y": 10.0, "element": "C"},
                {"id": 2, "x": 20.0, "y": 10.0, "element": "O"}
            ],
            "bonds": [
                {"source": 1, "target": 2, "type": 2}
            ]
        }
        res = self.app.post("/api/canvas_to_smiles", json=payload)
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertTrue(data.get("ok"))
        self.assertEqual(data.get("smiles"), "C=O")

    def test_optimize_2d(self):
        payload = {
            "atoms": [
                {"id": 1, "x": 10.0, "y": 10.0, "element": "C"},
                {"id": 2, "x": 20.0, "y": 10.0, "element": "O"}
            ],
            "bonds": [
                {"source": 1, "target": 2, "type": 1}
            ]
        }
        res = self.app.post("/api/optimize_2d", json=payload)
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertTrue(data.get("ok"))
        self.assertIn("canvas_payload", data)
        atoms = data["canvas_payload"]["atoms"]
        self.assertEqual(len(atoms), 2)

    def test_descriptors(self):
        res = self.app.post("/api/descriptors", json={"smiles": "CC(=O)O"})
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertTrue(data.get("ok"))
        self.assertEqual(data.get("molecular_formula"), "C<sub>2</sub>H<sub>4</sub>O<sub>2</sub>")
        self.assertEqual(data.get("hbd"), 1)
        self.assertEqual(data.get("hba"), 1)

    def test_pdb_fetch_and_interactions(self):
        # Test fetch for 1OPJ
        res = self.app.get("/api/pdb/fetch?pdb_id=1OPJ")
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertTrue(data.get("ok"))
        self.assertEqual(data.get("pdb_id"), "1OPJ")
        self.assertGreater(len(data.get("ligands")), 0)
        
        # Test interactions for 1OPJ and STI (Imatinib)
        ligand = None
        for lig in data["ligands"]:
            if lig["resname"] == "STI":
                ligand = lig
                break
        if ligand is None:
            ligand = data["ligands"][0]
            
        inter_payload = {
            "smiles": "CC1=C(C=C(C=C1)NC2=NC=CC(=N2)C3=CN=CC=C3)NC(=O)C4=CC=C(C=C4)CN5CCN(CC5)C",
            "pdb_id": "1OPJ",
            "ligand_resname": ligand["resname"],
            "ligand_chain": ligand["chain"],
            "ligand_seq": ligand["seq"]
        }
        res_inter = self.app.post("/api/interactions", json=inter_payload)
        self.assertEqual(res_inter.status_code, 200)
        inter_data = json.loads(res_inter.data)
        self.assertTrue(inter_data.get("ok"))
        self.assertIn("interactions", inter_data)

if __name__ == "__main__":
    unittest.main()
