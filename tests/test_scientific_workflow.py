"""V5.0 Scientific Closed-Loop Workflow End-to-End Integration Test.

Validates the full scientific pipeline:
1. SMILES Input -> RDKit 3D Conformer Generation (generate_gaussian_input_from_smiles).
2. Automated GJF Input File Generation with Link 0 directives and Cartesian coordinates.
3. Preflight Inspection & Cryptographic Token Generation (submit_gaussian_calculation dry-run).
4. Controlled Mock Gaussian Calculation Execution (submit_gaussian_calculation mock_mode).
5. Real-time Status Polling & Convergence Progress Tracking (get_gaussian_job_status).
6. Output Log Parsing & Thermochemical / Electronic Structure Extraction (parse_gaussian_output).
7. Verification of Scientific Closed Loop:
   - Energy progression & convergence.
   - Dipole moment.
   - Frontier orbital eigenvalues (HOMO / LUMO).
   - Normal termination signature.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from backend.config import settings
from backend.mcp_server import (
    diagnose_gaussian_error,
    generate_gaussian_input_from_smiles,
    get_gaussian_job_status,
    parse_gaussian_output,
    submit_gaussian_calculation,
)


class TestScientificWorkflow(unittest.TestCase):
    """End-to-end integration test verifying complete computational chemistry closed-loop."""

    @classmethod
    def setUpClass(cls):
        cls._saved_env = {
            k: os.environ.get(k)
            for k in (
                "GAUSSIAN_DATA_DIR",
                "GAUSSIAN_WORK_DIR",
                "GAUSSIAN_ALLOWED_WRITE_ROOTS",
                "GAUSSIAN_ALLOWED_READ_ROOTS",
                "GAUSSIAN_ALLOW_REAL_EXECUTION",
            )
        }
        cls.tmp_root = Path(tempfile.mkdtemp(prefix="gaussian_sci_wf_"))
        cls.data_dir = cls.tmp_root / "data"
        cls.workflow_dir = cls.tmp_root / "work"
        cls.data_dir.mkdir(parents=True, exist_ok=True)
        cls.workflow_dir.mkdir(parents=True, exist_ok=True)

        os.environ["GAUSSIAN_DATA_DIR"] = str(cls.data_dir.resolve())
        os.environ["GAUSSIAN_WORK_DIR"] = str(cls.workflow_dir.resolve())
        os.environ["GAUSSIAN_ALLOWED_WRITE_ROOTS"] = str(cls.workflow_dir.resolve())
        os.environ["GAUSSIAN_ALLOWED_READ_ROOTS"] = str(cls.workflow_dir.resolve())
        os.environ["GAUSSIAN_ALLOW_REAL_EXECUTION"] = "false"

    @classmethod
    def tearDownClass(cls):
        for k, v in cls._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(cls.tmp_root, ignore_errors=True)

    def test_full_scientific_closed_loop_ethanol(self):
        """End-to-end test on Ethanol (SMILES: 'CCO'):

        SMILES -> 3D Conformer -> GJF -> Preflight -> Mock G16 -> Status Polling -> Output Parsing
        """
        # Step 1: Generate 3D conformer and GJF from SMILES
        smiles_input = "CCO"
        gjf_gen_res = generate_gaussian_input_from_smiles(
            smiles=smiles_input,
            job_name="ethanol_closed_loop",
            job_type="opt",
            method="B3LYP",
            basis="6-31G(d)",
            mem="4GB",
            nproc=4,
            save_to_file=True,
            output_dir=str(self.workflow_dir),
        )

        self.assertTrue(gjf_gen_res.get("saved_path"))
        saved_gjf_path = Path(gjf_gen_res["saved_path"])
        self.assertTrue(saved_gjf_path.exists())
        self.assertEqual(gjf_gen_res["smiles_info"]["canonical_smiles"], "CCO")
        self.assertEqual(gjf_gen_res["atom_count"], 9)  # C2 H6 O = 9 atoms

        # Step 2: Preflight dry-run check & token issuance
        dry_res = submit_gaussian_calculation(
            gjf_path=str(saved_gjf_path),
            job_name="ethanol_closed_loop",
            dry_run=True,
        )

        self.assertTrue(dry_res.get("ok"))
        self.assertTrue(dry_res.get("dry_run"))
        preflight = dry_res.get("preflight", {})
        self.assertTrue(preflight.get("preflight_passed"))
        self.assertEqual(preflight.get("atom_count"), 9)
        self.assertEqual(preflight.get("charge"), 0)
        self.assertEqual(preflight.get("multiplicity"), 1)
        token = preflight.get("execution_token")
        self.assertIsNotNone(token)

        # Step 3: Controlled Mock Gaussian Job Execution
        sub_res = submit_gaussian_calculation(
            gjf_path=str(saved_gjf_path),
            job_name="ethanol_closed_loop",
            dry_run=False,
            mock_mode=True,
            mock_duration=0.8,
        )

        self.assertTrue(sub_res.get("ok"), str(sub_res))
        self.assertTrue(sub_res.get("is_simulated"))
        self.assertFalse(sub_res.get("real_gaussian_result"))
        job_id = sub_res.get("job_id")
        self.assertIsNotNone(job_id)
        self.assertEqual(sub_res.get("status"), "running")

        # Step 4: Poll status until completion
        max_wait = 5.0
        elapsed = 0.0
        completed = False
        final_status = None

        while elapsed < max_wait:
            time.sleep(0.3)
            elapsed += 0.3
            status_res = get_gaussian_job_status(job_id=job_id)
            self.assertTrue(status_res.get("ok"))
            if status_res.get("status") == "completed":
                completed = True
                final_status = status_res
                break

        self.assertTrue(completed, f"Job did not complete within {max_wait}s: {final_status}")
        self.assertTrue(final_status.get("is_simulated"))
        self.assertFalse(final_status.get("real_gaussian_result"))
        self.assertIsNone(final_status.get("last_energy"))
        self.assertIsNotNone(final_status.get("simulated_energy"))
        self.assertTrue(final_status.get("simulation_warning"))

        log_path_str = final_status.get("log_path")
        self.assertIsNotNone(log_path_str)
        log_file = Path(log_path_str)
        self.assertTrue(log_file.exists())

        # Step 5: Parse Gaussian output log with parse_gaussian_output
        parse_res = parse_gaussian_output(
            file_path=str(log_file),
        )

        # Step 6: Validate scientific completeness AND strict mock-energy isolation
        self.assertTrue(parse_res.get("normal_termination"))
        self.assertIsNone(parse_res.get("error_message"))
        self.assertEqual(parse_res.get("charge"), 0)
        self.assertEqual(parse_res.get("multiplicity"), 1)
        self.assertTrue(parse_res.get("is_simulated"))
        self.assertFalse(parse_res.get("real_gaussian_result"))
        self.assertEqual(parse_res.get("energy_source"), "mock_simulation_placeholder")
        self.assertTrue(parse_res.get("simulation_warning"))

        # Simulated energies must NEVER be reported in final_energy
        self.assertIsNone(parse_res.get("final_energy"))
        sim_energy = parse_res.get("simulated_energy")
        self.assertIsNotNone(sim_energy)
        self.assertLess(sim_energy, -70.0)  # Synthetic placeholder around -76.4 A.U.
        self.assertTrue(parse_res.get("stationary_point"))
        self.assertTrue(parse_res.get("opt_converged"))
        self.assertEqual(parse_res.get("opt_steps"), 3)

        # Dipole moment
        dipole = parse_res.get("dipole_moment")
        self.assertIsNotNone(dipole)
        self.assertAlmostEqual(dipole, 1.85, delta=0.05)

        # Frontier orbital analysis
        homo = parse_res.get("homo_energy")
        lumo = parse_res.get("lumo_energy")
        gap = parse_res.get("homo_lumo_gap")
        self.assertIsNotNone(homo)
        self.assertIsNotNone(lumo)
        self.assertIsNotNone(gap)
        self.assertGreater(gap, 0.0)
        self.assertAlmostEqual(gap, lumo - homo, places=5)

    def test_benzene_scf_failure_closed_loop_and_diagnosis(self):
        """End-to-end failure diagnosis closed loop on Benzene (c1ccccc1):

        SMILES -> 3D Conformer -> GJF -> Submit with fail_scf=True -> Polling failed ->
        Output Parsing error detection -> Automated Error Diagnosis recommendations
        """
        # Step 1: Generate Benzene GJF
        gjf_res = generate_gaussian_input_from_smiles(
            smiles="c1ccccc1",
            job_name="benzene_scf_fail_test",
            job_type="opt",
            method="B3LYP",
            basis="6-31G(d)",
            save_to_file=True,
            output_dir=str(self.workflow_dir),
        )
        saved_gjf = Path(gjf_res["saved_path"])
        self.assertTrue(saved_gjf.exists())

        # Step 2: Submit with fail_scf=True
        sub_res = submit_gaussian_calculation(
            gjf_path=str(saved_gjf),
            job_name="benzene_scf_fail_test",
            dry_run=False,
            mock_mode=True,
            fail_scf=True,
            mock_duration=0.5,
        )
        self.assertTrue(sub_res.get("ok"))
        job_id = sub_res.get("job_id")

        # Step 3: Poll status until failed
        max_wait = 4.0
        elapsed = 0.0
        failed = False
        final_status = None

        while elapsed < max_wait:
            time.sleep(0.3)
            elapsed += 0.3
            st = get_gaussian_job_status(job_id=job_id)
            if st.get("status") == "failed":
                failed = True
                final_status = st
                break

        self.assertTrue(failed, f"Job did not fail as expected: {final_status}")
        log_file = Path(final_status.get("log_path"))
        self.assertTrue(log_file.exists())

        # Step 4: Parse failure log
        parse_res = parse_gaussian_output(file_path=str(log_file))
        self.assertFalse(parse_res.get("normal_termination"))
        err_msg = parse_res.get("error_message")
        self.assertIsNotNone(err_msg)
        self.assertIn("SCF 收敛失败", err_msg)

        # Step 5: Automated diagnosis
        diag_res = diagnose_gaussian_error(
            error_text=err_msg,
            log_tail=final_status.get("log_tail"),
        )
        self.assertIn("diagnoses", diag_res)
        diagnoses = diag_res.get("diagnoses", [])
        self.assertGreater(len(diagnoses), 0)
        # Verify recommendation addresses SCF convergence
        any_scf_advice = any("scf" in d.get("error", "").lower() or "scf" in d.get("description", "").lower() for d in diagnoses)
        self.assertTrue(any_scf_advice, f"Expected SCF diagnosis advice, got {diagnoses}")


if __name__ == "__main__":
    unittest.main()
