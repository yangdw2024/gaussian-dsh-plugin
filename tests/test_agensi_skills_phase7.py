"""Phase 7 tests: verify standalone Agensi CLI tools and ZIP packaging guarantees."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import package_agensi_skills as pkg_agensi  # noqa: E402


class TestAgensiSkillsPhase7(unittest.TestCase):
    def test_01_gjf_helper_standalone_xyz_to_gjf_and_validate(self) -> None:
        helper = REPO_ROOT / "skills" / "gaussian-job-setup" / "scripts" / "gjf_helper.py"
        with tempfile.TemporaryDirectory(prefix="agensi_gjf_") as td:
            tdp = Path(td)
            xyz = tdp / "h2.xyz"
            xyz.write_text("2\nH2 test\nH 0.0 0.0 0.0\nH 0.0 0.0 0.74\n", encoding="utf-8")
            gjf = tdp / "h2.gjf"
            r1 = subprocess.run(
                [sys.executable, str(helper), "xyz-to-gjf", str(xyz), "-o", str(gjf), "--solvent", "water"],
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertEqual(r1.returncode, 0)
            content = gjf.read_text(encoding="utf-8")
            self.assertIn("scrf=(iefpcm,solvent=water)", content)
            self.assertTrue(content.endswith("\n\n"))

            r2 = subprocess.run(
                [sys.executable, str(helper), "validate", str(gjf)],
                capture_output=True,
                text=True,
                check=True,
            )
            report = json.loads(r2.stdout)
            self.assertTrue(report["valid"])
            self.assertEqual(report["atom_count"], 2)

            bad_gjf = tdp / "bad_parity.gjf"
            bad_gjf.write_text("%chk=h2.chk\n#p HF/STO-3G\n\ntest\n\n0 2\nH 0 0 0\nH 0 0 0.74\n\n", encoding="utf-8")
            r3 = subprocess.run(
                [sys.executable, str(helper), "validate", str(bad_gjf)],
                capture_output=True,
                text=True,
                check=True,
            )
            rep3 = json.loads(r3.stdout)
            self.assertTrue(any("parity mismatch" in w.lower() for w in rep3["warnings"]))

    def test_02_log_analyzer_parses_real_h2_fixture(self) -> None:
        analyzer = REPO_ROOT / "skills" / "gaussian-output-analysis" / "scripts" / "log_analyzer.py"
        fixture = REPO_ROOT / "tests" / "fixtures" / "h2_sp_reference.log"
        r = subprocess.run(
            [sys.executable, str(analyzer), str(fixture), "--format", "json"],
            capture_output=True,
            text=True,
            check=True,
        )
        data = json.loads(r.stdout)
        self.assertTrue(data["normal_termination"])
        self.assertFalse(data["is_simulated"])
        self.assertAlmostEqual(data["scf_energy_hartree"], -1.1175058821, places=6)
        self.assertIsNotNone(data["homo_lumo_gap_ev"])

    def test_03_multiwfn_recipe_enforces_16m_grid_cap(self) -> None:
        tool = REPO_ROOT / "skills" / "gaussian-postprocessing" / "scripts" / "multiwfn_recipe.py"
        ok = subprocess.run(
            [sys.executable, str(tool), "check-grid", "--nx", "200", "--ny", "200", "--nz", "200"],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertTrue(json.loads(ok.stdout)["within_limit"])

        over = subprocess.run(
            [sys.executable, str(tool), "check-grid", "--nx", "300", "--ny", "300", "--nz", "300"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(over.returncode, 2)
        self.assertFalse(json.loads(over.stdout)["within_limit"])

        with tempfile.TemporaryDirectory(prefix="agensi_mw_") as td:
            rec = subprocess.run(
                [sys.executable, str(tool), "recipe", "--kind", "rdg", "--grid", "medium", "--stem", "dimer", "--out-dir", td],
                capture_output=True,
                text=True,
                check=True,
            )
            payload = json.loads(rec.stdout)
            self.assertEqual(payload["kind"], "rdg")
            self.assertTrue((Path(td) / "multiwfn_input.txt").exists())
            self.assertTrue((Path(td) / "render.tcl").exists())

    def test_04_package_agensi_skills_zip_root_frontmatter_and_sanitization(self) -> None:
        with tempfile.TemporaryDirectory(prefix="agensi_zips_") as td:
            zips = pkg_agensi.package_all(REPO_ROOT / "skills", Path(td), expected_version="0.3.0")
            self.assertEqual(len(zips), 3)
            names_built = {z.name for z in zips}
            self.assertEqual(
                names_built,
                {
                    "gaussian-job-setup-v0.3.0.zip",
                    "gaussian-output-analysis-v0.3.0.zip",
                    "gaussian-postprocessing-v0.3.0.zip",
                },
            )
            for zp in zips:
                with zipfile.ZipFile(zp, "r") as zf:
                    members = set(zf.namelist())
                    self.assertIn("SKILL.md", members)
                    meta = pkg_agensi.parse_frontmatter(zf.read("SKILL.md").decode("utf-8"))
                    self.assertEqual(meta["version"], "0.3.0")
                    self.assertTrue(any(m.startswith("scripts/") and m.endswith(".py") for m in members))
                    self.assertIn("templates/mcp-config.json", members)


if __name__ == "__main__":
    unittest.main()
