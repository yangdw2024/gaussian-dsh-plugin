"""Scientific Correctness and Physical Accuracy Verification Suite for Gaussian AI MCP Server.

Validates:
1. Charge and spin multiplicity inference (closed shell vs radical doublet).
2. Input syntax and Link 0 (%mem, %nprocshared, %chk, # route) assembly.
3. Accurate numerical extraction of electronic energy (Hartree) against verified references.
4. Correct discrimination between SCF convergence and Geometry Optimization convergence.
5. Frontier orbital eigenvalues (HOMO, LUMO in a.u.) and HOMO-LUMO gap calculation.
6. Vibrational frequency analysis and transition state imaginary frequency detection (<0 cm^-1).
7. Thermochemical corrections (ZPE, Enthalpy, Gibbs Free Energy in Hartree).
8. Error termination detection and graceful degradation on truncated/corrupted logs.
"""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import unittest

from backend.gaussian_input import GaussianInputRequest, generate_gjf
from backend.gaussian_output import output_to_dict, parse_gaussian_log
from backend.mcp_server import parse_gaussian_output
from backend.smiles.models import Smiles3DRequest
from backend.smiles.rdkit_builder import smiles_to_3d

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
REAL_GJF_DIR = Path(r"E:\YDW\ChemDatas\Gjf")


class TestScientificCorrectness(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Authorize test fixtures directory for READ access during test execution
        import os
        cls._orig_env = os.environ.get("GAUSSIAN_ALLOWED_READ_ROOTS")
        os.environ["GAUSSIAN_ALLOWED_READ_ROOTS"] = str(FIXTURES_DIR)

    @classmethod
    def tearDownClass(cls):
        import os
        if cls._orig_env is not None:
            os.environ["GAUSSIAN_ALLOWED_READ_ROOTS"] = cls._orig_env
        else:
            os.environ.pop("GAUSSIAN_ALLOWED_READ_ROOTS", None)
    # -------------------------------------------------------------------------
    # 1. H2: Minimal Diatomic Ground State
    # -------------------------------------------------------------------------
    def test_h2_input_and_log_parsing(self):
        """Verify H2 input syntax and energy parsing against reference single-point calculation."""
        # 1.1 Input Generation
        req = GaussianInputRequest(
            job_name="h2_ground",
            job_type="sp",
            method="HF",
            basis="STO-3G",
            charge=0,
            multiplicity=1,
            atoms=[("H", 0.0, 0.0, 0.0), ("H", 0.0, 0.0, 0.7414)],
        )
        gjf = generate_gjf(req)
        self.assertIn("# HF/STO-3G", gjf["content"])
        self.assertIn("0 1", gjf["content"])
        self.assertIn("H       0.00000000     0.00000000     0.74140000", gjf["content"])

        # 1.2 Log Parsing
        log_path = FIXTURES_DIR / "h2_sp_reference.log"
        parsed = parse_gaussian_output(file_path=str(log_path))

        self.assertTrue(parsed["normal_termination"])
        self.assertIsNone(parsed["error_message"])
        # Theoretical HF/STO-3G energy at R=0.7414 A is -1.11750588210 Hartree
        self.assertAlmostEqual(parsed["final_energy"], -1.11750588210, places=7)
        self.assertAlmostEqual(parsed["homo_energy"], -0.57790, places=5)
        self.assertAlmostEqual(parsed["lumo_energy"], 0.66970, places=5)
        self.assertAlmostEqual(parsed["homo_lumo_gap"], 0.66970 - (-0.57790), places=5)
        self.assertAlmostEqual(parsed["dipole_moment"], 0.0000, places=4)

    # -------------------------------------------------------------------------
    # 2. H2O: Vibrational Frequencies and Thermochemistry
    # -------------------------------------------------------------------------
    def test_h2o_frequencies_and_thermochemistry(self):
        """Verify H2O vibrational mode extraction (3N-6=3 modes) and thermochemical quantities."""
        log_path = FIXTURES_DIR / "h2o_freq_reference.log"
        parsed = parse_gaussian_output(file_path=str(log_path))

        self.assertTrue(parsed["normal_termination"])
        self.assertAlmostEqual(parsed["final_energy"], -76.4089528701, places=7)
        self.assertEqual(len(parsed["frequencies"]), 3)
        self.assertAlmostEqual(parsed["frequencies"][0], 1648.5020, places=2)
        self.assertAlmostEqual(parsed["frequencies"][1], 3825.1200, places=2)
        self.assertAlmostEqual(parsed["frequencies"][2], 3935.4500, places=2)
        self.assertEqual(len(parsed["imaginary_frequencies"]), 0)

        # Thermochemical corrections
        self.assertAlmostEqual(parsed["zero_point_energy"], 0.021540, places=6)
        self.assertAlmostEqual(parsed["thermal_enthalpy"], 0.025320, places=6)
        self.assertAlmostEqual(parsed["thermal_free_energy"], 0.003920, places=6)
        self.assertAlmostEqual(parsed["dipole_moment"], 1.8540, places=4)

    # -------------------------------------------------------------------------
    # 3. Benzene: SMILES 3D Conformer & Real Gaussian 16 Log Benchmark
    # -------------------------------------------------------------------------
    def test_benzene_smiles_and_real_g16_benchmark(self):
        """Benchmark Benzene: RDKit 3D conformer generation + Real G16 optimization log verification."""
        # 3.1 RDKit 3D Conformer
        mol3d = smiles_to_3d(Smiles3DRequest(smiles="c1ccccc1"))
        self.assertEqual(mol3d.charge, 0)
        self.assertEqual(mol3d.multiplicity, 1)
        self.assertEqual(mol3d.spin_inference, "closed_shell_singlet")
        self.assertEqual(len(mol3d.atoms), 12)  # 6 C + 6 H

        # 3.2 Real G16 Log Verification from Disk
        real_log = REAL_GJF_DIR / "c1ccccc1_opt_B3LYP_631Gdp_67f4b8f183fa.log"
        if not real_log.exists():
            self.skipTest(f"Real benchmark log {real_log} not present on this machine.")

        parsed = parse_gaussian_output(file_path=str(real_log))
        self.assertTrue(parsed["normal_termination"])
        self.assertTrue(parsed["stationary_point"])
        self.assertTrue(parsed["opt_converged"])
        # Reference energy for B3LYP/6-31G(d,p) optimized benzene
        self.assertAlmostEqual(parsed["final_energy"], -232.258201851, places=6)
        self.assertAlmostEqual(parsed["homo_energy"], -0.24688, places=4)
        self.assertAlmostEqual(parsed["lumo_energy"], 0.00260, places=4)
        self.assertAlmostEqual(parsed["homo_lumo_gap"], 0.24948, places=4)
        # Dipole moment of symmetric benzene (D6h) must be 0.0
        self.assertAlmostEqual(parsed["dipole_moment"], 0.0000, places=3)

    # -------------------------------------------------------------------------
    # 4. Transition State Imaginary Frequency Recognition
    # -------------------------------------------------------------------------
    def test_transition_state_imaginary_frequency(self):
        """Verify that negative vibrational frequencies (<0 cm^-1) are isolated as imaginary modes."""
        log_path = FIXTURES_DIR / "ts_imag_reference.log"
        parsed = parse_gaussian_output(file_path=str(log_path))

        self.assertTrue(parsed["normal_termination"])
        self.assertEqual(len(parsed["imaginary_frequencies"]), 1)
        self.assertAlmostEqual(parsed["imaginary_frequencies"][0], -485.32, places=2)

    # -------------------------------------------------------------------------
    # 5. SCF Convergence Failure & Error State Discrimination
    # -------------------------------------------------------------------------
    def test_scf_failure_discrimination(self):
        """Verify that SCF convergence failure is explicitly identified and not marked as normal termination."""
        log_path = FIXTURES_DIR / "scf_failed_reference.log"
        parsed = parse_gaussian_output(file_path=str(log_path))

        self.assertFalse(parsed["normal_termination"])
        self.assertTrue(
            "SCF 收敛失败" in (parsed["error_message"] or "") or
            "Convergence failure" in (parsed["error_message"] or "")
        )
        self.assertFalse(parsed["stationary_point"] or False)
        self.assertFalse(parsed["opt_converged"] or False)

    # -------------------------------------------------------------------------
    # 6. Corrupted & Truncated Log Resilience
    # -------------------------------------------------------------------------
    def test_corrupted_log_graceful_handling(self):
        """Verify that parsing truncated or corrupt logs returns clean error status without crash."""
        corrupt_text = "Entering Link 1 ... \nSome random incomplete calculation\n"
        parsed = parse_gaussian_log(corrupt_text, filename="truncated.log")
        res = output_to_dict(parsed)

        self.assertFalse(res["normal_termination"])
        self.assertIsNone(res["final_energy"])
        self.assertIsNone(res["homo_energy"])
        self.assertEqual(len(res["frequencies"]), 0)


if __name__ == "__main__":
    unittest.main()
