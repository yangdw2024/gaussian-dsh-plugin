"""Test suite for Phase 3 MCP Tools: Batch 2.

Covers:
1. search_gaussian_keywords
2. search_basis_sets
3. get_basis_set
4. generate_gaussian_input_from_smiles
"""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import unittest

from backend.config import settings
from backend.mcp_server import (
    generate_gaussian_input_from_smiles,
    get_basis_set,
    search_basis_sets,
    search_gaussian_keywords,
)


class TestMCPBatch2(unittest.TestCase):
    def test_search_keywords_basic(self):
        res = search_gaussian_keywords(query="opt")
        self.assertGreater(res["count"], 0)
        keywords = [item["keyword"].lower() for item in res["results"]]
        self.assertTrue(any("opt" in kw for kw in keywords))
        self.assertIn("任务类型", res["available_categories"])

    def test_search_keywords_with_category_filter(self):
        res = search_gaussian_keywords(query="b3lyp", category="方法与泛函")
        self.assertGreater(res["count"], 0)
        for r in res["results"]:
            self.assertEqual(r["category"], "方法与泛函")

    def test_search_keywords_invalid_category(self):
        with self.assertRaises(ValueError):
            search_gaussian_keywords(query="test", category="NonExistentCategory")

    def test_search_basis_sets(self):
        res = search_basis_sets(query="def2-svp", limit=5)
        self.assertGreater(res["count"], 0)
        names = [b["name"].lower() for b in res["basis_sets"]]
        self.assertTrue(any("def2-svp" in n for n in names))

    def test_search_basis_sets_with_family_filter(self):
        res = search_basis_sets(query="pople", family="pople", limit=10)
        self.assertGreater(res["count"], 0)
        for b in res["basis_sets"]:
            self.assertEqual(b.get("family", "").lower(), "pople")

    def test_get_basis_set_success(self):
        res = get_basis_set(name="6-31g", elements=[1, 6], format="gaussian94")
        self.assertTrue(res.get("ok"))
        self.assertIn("content", res)
        self.assertTrue(len(res["content"]) > 50)

    def test_get_basis_set_save_to_authorized_file(self):
        out_file = settings.work_dir / "test_custom_basis.gbs"
        try:
            res = get_basis_set(
                name="6-31g",
                elements=[1, 6],
                save_to_file=True,
                output_path=str(out_file),
            )
            self.assertTrue(res.get("ok"))
            self.assertEqual(Path(res["saved_path"]).resolve(), out_file.resolve())
            self.assertTrue(out_file.exists())
        finally:
            if out_file.exists():
                out_file.unlink()

    def test_get_basis_set_rejects_unauthorized_write(self):
        project_root = Path(__file__).resolve().parent.parent
        evil_path = project_root / "evil_basis.gbs"
        with self.assertRaises(PermissionError):
            get_basis_set(
                name="6-31g",
                elements=[1, 6],
                save_to_file=True,
                output_path=str(evil_path),
            )

    def test_generate_input_from_smiles_ethanol(self):
        res = generate_gaussian_input_from_smiles(
            smiles="CCO",
            job_name="ethanol_test",
            job_type="opt",
            method="B3LYP",
            basis="6-31G(d,p)",
            save_to_file=False,
        )
        self.assertIn("# B3LYP/6-31G(d,p) opt", res["content"])
        self.assertEqual(res["atom_count"], 9)  # 2 C + 1 O + 6 H = 9 atoms
        self.assertEqual(res["smiles_info"]["charge"], 0)
        self.assertEqual(res["smiles_info"]["multiplicity"], 1)
        self.assertIsNone(res["saved_path"])

    def test_generate_input_from_smiles_benzene_file_save(self):
        expected_file = settings.work_dir / "benzene_test.gjf"
        try:
            res = generate_gaussian_input_from_smiles(
                smiles="c1ccccc1",
                job_name="benzene_test",
                job_type="opt freq",
                method="wB97XD",
                basis="def2-SVP",
                save_to_file=True,
            )
            self.assertIn("# wB97XD/def2-SVP opt freq", res["content"])
            self.assertEqual(res["atom_count"], 12)  # 6 C + 6 H = 12
            self.assertTrue(expected_file.exists())
            self.assertEqual(Path(res["saved_path"]).resolve(), expected_file.resolve())
        finally:
            if expected_file.exists():
                expected_file.unlink()

    def test_generate_input_from_smiles_rejects_disconnected_salt(self):
        with self.assertRaises(ValueError) as ctx:
            generate_gaussian_input_from_smiles(
                smiles="[Na+].[Cl-]",
                allow_disconnected=False,
            )
        self.assertIn("SMILES 包含", str(ctx.exception))

    def test_generate_input_from_smiles_rejects_unauthorized_dir(self):
        project_root = Path(__file__).resolve().parent.parent
        with self.assertRaises(PermissionError):
            generate_gaussian_input_from_smiles(
                smiles="CCO",
                save_to_file=True,
                output_dir=str(project_root),
            )


if __name__ == "__main__":
    unittest.main()
