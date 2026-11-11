"""Phase 3 Scientific Correctness & Boundary Verification Suite.

Covers the 10 computational chemistry accuracy boundaries audited in Phase 3:
1. SP vs Opt multi-step final energy selection.
2. Ground-state KS HOMO-LUMO gap vs TD-DFT vertical excited states (and parser newline boundary safety).
3. Exact Hartree / eV / kcal/mol / kJ/mol conversion factors & FCHK MO units.
4. Post-HF (CCSD(T), MP2) energy precedence over HF SCF reference + missing-correlation fallback warning.
5. Vibrational frequency stationary point classification (0 / 1 / >=2 imaginary modes) & thermochemistry totals.
6. RDKit ETKDGv3/MMFF94s force-field 3D conformer vs DFT equilibrium geometry disclaimer.
7. Strict Mock simulation isolation (`is_simulated=True`, `final_energy=None`, `scf_energy=None`, `total_*=None`).
8. Normal termination != Optimization converged (4-column G16 table with `NO`).
9. BSE metadata-only clarification vs `Gen`/`GenECP` missing basis definition warning.
10. Multi-step `Link1` partial completion / mid-step truncation / post-Normal Error termination detection.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import unittest

from backend.basis_set import BasisSetClient
from backend.fchk_reader import generate_mo_level_svg, read_fchk_orbital_info
from backend.gaussian_input import GaussianInputRequest, generate_gjf
from backend.gaussian_output import (
    HARTREE_TO_EV,
    HARTREE_TO_KCAL_MOL,
    HARTREE_TO_KJ_MOL,
    output_to_dict,
    parse_gaussian_log,
)
from backend.mcp_server import generate_gaussian_input_from_smiles
from backend.mock_worker import run_mock


class TestScientificPhase3(unittest.TestCase):
    def test_01_single_point_vs_opt_last_step_semantics(self):
        """Opt logs must pick the final converged step energy rather than step 1."""
        opt_log = """
 # B3LYP/6-31G(d,p) opt
 Optimization cycle   1
 SCF Done:  E(RB3LYP) =  -76.390000000     A.U. after    7 cycles
 Optimization cycle   2
 SCF Done:  E(RB3LYP) =  -76.422500123     A.U. after    4 cycles
         Item               Value     Threshold  Converged?
 Maximum Force            0.000012     0.000450     YES
 RMS     Force            0.000004     0.000300     YES
 Maximum Displacement     0.000080     0.001800     YES
 RMS     Displacement     0.000030     0.001200     YES
 Optimization completed.
    -- Stationary point found.
 Normal termination of Gaussian 16 at Thu Jan 01 00:00:00 2026.
"""
        parsed = output_to_dict(parse_gaussian_log(opt_log, filename="opt.log"))
        self.assertTrue(parsed["normal_termination"])
        self.assertEqual(parsed["calculation_type"], "opt")
        self.assertEqual(parsed["opt_steps"], 2)
        self.assertTrue(parsed["opt_converged"])
        self.assertTrue(parsed["stationary_point"])
        self.assertAlmostEqual(parsed["final_energy"], -76.422500123, places=9)

    def test_02_homo_lumo_gap_vs_tddft_excited_states(self):
        """TD-DFT excited state lines adjacent to Alpha virt eigenvalues must not crash parser."""
        td_log = """
 # TD(NStates=3) B3LYP/6-31G(d)
 Alpha  occ. eigenvalues --  -0.31250  -0.25000
 Alpha virt. eigenvalues --   0.04500   0.12000
 Excited State   1:      Singlet-A      3.5120 eV  353.03 nm  f=0.1425  <S**2>=0.000
 Excited State   2:      Singlet-B      4.8500 eV  255.64 nm  f=0.0040  <S**2>=0.000
 SCF Done:  E(RB3LYP) =  -128.456789012     A.U. after    6 cycles
 Normal termination of Gaussian 16 at Thu Jan 01 00:00:00 2026.
"""
        parsed = output_to_dict(parse_gaussian_log(td_log, filename="td.log"))
        self.assertTrue(parsed["normal_termination"])
        self.assertEqual(parsed["calculation_type"], "td")
        self.assertAlmostEqual(parsed["homo_energy"], -0.25000, places=5)
        self.assertAlmostEqual(parsed["lumo_energy"], 0.04500, places=5)
        self.assertAlmostEqual(parsed["homo_lumo_gap"], 0.29500, places=5)
        self.assertAlmostEqual(parsed["homo_lumo_gap_ev"], round(0.29500 * HARTREE_TO_EV, 6), places=5)
        self.assertEqual(len(parsed["excited_states"]), 2)
        self.assertAlmostEqual(parsed["excited_states"][0]["energy_ev"], 3.5120, places=4)
        self.assertAlmostEqual(parsed["excited_states"][0]["oscillator_strength"], 0.1425, places=4)
        self.assertTrue(any("TD-DFT" in c for c in parsed["scientific_caveats"]))

        td_gjf = generate_gjf(GaussianInputRequest(job_name="td_chk", job_type="td", atoms=[("H", 0, 0, 0), ("H", 0, 0, 0.74)]))
        self.assertTrue(any("TD-DFT" in w or "垂直激发" in w for w in td_gjf["warnings"]))

    def test_03_energy_units_and_conversion_constants(self):
        """Explicit Hartree, eV, kcal/mol, and kJ/mol conversion precision and FCHK MO units."""
        self.assertAlmostEqual(HARTREE_TO_EV, 27.211386245988, places=10)
        self.assertAlmostEqual(HARTREE_TO_KCAL_MOL, 627.5094740631, places=8)
        self.assertAlmostEqual(HARTREE_TO_KJ_MOL, 2625.4996394799, places=8)

        d = output_to_dict(parse_gaussian_log("SCF Done:  E(RHF) =  -1.000000000  A.U. after 2 cycles\nAlpha  occ. eigenvalues --  -0.50000\nAlpha virt. eigenvalues --   0.50000\nNormal termination of Gaussian 16\n"))
        conv = d["energy_units_detail"]["conversions"]
        self.assertAlmostEqual(conv["1_hartree_ev"], HARTREE_TO_EV, places=10)
        self.assertAlmostEqual(d["homo_energy_ev"], round(-0.5 * HARTREE_TO_EV, 6), places=6)
        self.assertAlmostEqual(d["lumo_energy_ev"], round(0.5 * HARTREE_TO_EV, 6), places=6)
        self.assertAlmostEqual(d["homo_lumo_gap_ev"], round(1.0 * HARTREE_TO_EV, 6), places=6)

        fchk_sample = Path(r"D:\Multiwfn\Multiwfn_3.8_bin_Win64\examples\CH3Cl.fchk")
        if fchk_sample.exists():
            info = read_fchk_orbital_info(fchk_sample)
            self.assertIsNotNone(info.gap)
            self.assertAlmostEqual(info.gap, (info.lumo_energy - info.homo_energy) * 27.2114, places=3)
            svg = generate_mo_level_svg(info)
            self.assertIn("Hartree", svg)
            self.assertIn("eV", svg)

    def test_04_post_hf_energy_priority_and_missing_correlation_warning(self):
        """CCSD(T) and MP2 total energies must override HF SCF Done; missing Post-HF warns explicitly."""
        ccsdt_log = """
 # CCSD(T)/cc-pVTZ
 SCF Done:  E(RHF) =  -76.050000000     A.U. after    7 cycles
 EUMP2 =    -0.25000000000000D+00
 CCSD(T)=  -76.35123456789D+00
 Normal termination of Gaussian 16 at Thu Jan 01 00:00:00 2026.
"""
        c_res = output_to_dict(parse_gaussian_log(ccsdt_log))
        self.assertAlmostEqual(c_res["final_energy"], -76.35123456789, places=11)
        self.assertAlmostEqual(c_res["scf_energy"], -76.05, places=6)
        self.assertEqual(c_res["energy_method"], "CCSD(T)")

        mp2_log = """
 # MP2/6-311+G(d,p)
 SCF Done:  E(RHF) =  -76.040000000     A.U. after    6 cycles
 E2 =    -0.2100000000D+00 EUMP2 =    -0.76250000000000D+02
 Normal termination of Gaussian 16 at Thu Jan 01 00:00:00 2026.
"""
        m_res = output_to_dict(parse_gaussian_log(mp2_log))
        self.assertAlmostEqual(m_res["final_energy"], -76.25, places=9)
        self.assertAlmostEqual(m_res["scf_energy"], -76.04, places=6)
        self.assertEqual(m_res["energy_method"], "MP2 (EUMP2)")

        missing_corr_log = """
 # CCSD(T)/cc-pVTZ
 SCF Done:  E(RHF) =  -76.050000000     A.U. after    7 cycles
 Error termination via Lnk1e in D:\\G16W\\l913.exe
"""
        miss_res = output_to_dict(parse_gaussian_log(missing_corr_log))
        self.assertFalse(miss_res["normal_termination"])
        self.assertAlmostEqual(miss_res["final_energy"], -76.05, places=6)
        self.assertTrue(any("Post-HF" in w and "回退为参考态" in w for w in miss_res["warnings"]))

    def test_05_imaginary_frequencies_character_and_thermochemistry(self):
        """Distinguish 0, 1 (TS), and >=2 imaginary frequencies and compute total thermal energies."""
        base_thermo = """
 Zero-point correction=                           0.020000 (Hartree/Particle)
 Thermal correction to Enthalpy=                  0.023000
 Thermal correction to Gibbs Free Energy=         0.005000
 Sum of electronic and zero-point Energies=          -76.380000
 Sum of electronic and thermal Energies=             -76.378000
 Sum of electronic and thermal Enthalpies=           -76.377000
 Sum of electronic and thermal Free Energies=        -76.395000
 SCF Done:  E(RB3LYP) =  -76.400000000     A.U. after    6 cycles
 Normal termination of Gaussian 16 at Thu Jan 01 00:00:00 2026.
"""
        ts_1 = "# B3LYP/6-31G(d) freq\n Frequencies --   -485.10   510.20   1200.40\n" + base_thermo
        r1 = output_to_dict(parse_gaussian_log(ts_1))
        self.assertEqual(r1["imaginary_frequencies"], [-485.1])
        self.assertIn("first_order_saddle_point_or_ts", r1["stationary_point_character"])
        self.assertTrue(any("过渡态" in w or "IRC" in w for w in r1["warnings"]))
        self.assertAlmostEqual(r1["total_zpe_energy"], -76.380000, places=6)
        self.assertAlmostEqual(r1["total_enthalpy"], -76.377000, places=6)
        self.assertAlmostEqual(r1["total_free_energy"], -76.395000, places=6)
        self.assertTrue(any("298.15 K" in c for c in r1["scientific_caveats"]))

        ts_2 = "# B3LYP/6-31G(d) freq\n Frequencies --   -512.34   -85.12   412.50\n" + base_thermo
        r2 = output_to_dict(parse_gaussian_log(ts_2))
        self.assertEqual(len(r2["imaginary_frequencies"]), 2)
        self.assertIn("higher_order_saddle_point", r2["stationary_point_character"])
        self.assertTrue(any("高阶鞍点" in w for w in r2["warnings"]))

    def test_06_rdkit_mmff_vs_dft_geometry_disclaimer(self):
        """SMILES -> GJF must clearly separate MMFF94s force-field initial geometry from DFT equilibrium."""
        sp_res = generate_gaussian_input_from_smiles(
            smiles="CCO",
            job_name="etoh_mmff_chk",
            job_type="sp",
            num_conformers=4,
            save_to_file=False,
        )
        sinfo = sp_res["smiles_info"]
        self.assertIn("MMFF94s", sinfo["geometry_disclaimer"])
        self.assertIn("NOT a DFT/ab initio equilibrium geometry", sinfo["geometry_disclaimer"])
        self.assertIn("kcal/mol", sinfo["mmff_energy_unit"])
        self.assertTrue(any("MMFF94s" in w and "sp" in w for w in sp_res["warnings"]))

    def test_07_mock_simulation_zero_contamination_isolation(self):
        """Mock worker logs must never populate final_energy, scf_energy, or thermochemistry totals."""
        with tempfile.TemporaryDirectory() as td:
            gjf_path = Path(td) / "water.gjf"
            log_path = Path(td) / "water.log"
            gjf_path.write_text("# B3LYP/6-31G(d) opt\n\nwater\n\n0 1\nO 0 0 0\nH 0 0 0.96\nH 0 0.96 0\n\n", encoding="utf-8")
            run_mock(gjf_path=gjf_path, log_path=log_path, fail_scf=False, duration=0.02, steps=2)
            content = log_path.read_text(encoding="utf-8")

        parsed = output_to_dict(parse_gaussian_log(content, filename="water.log"))
        self.assertTrue(parsed["is_simulated"])
        self.assertFalse(parsed["real_gaussian_result"])
        self.assertEqual(parsed["execution_mode"], "mock_simulation")
        self.assertEqual(parsed["energy_source"], "mock_simulation_placeholder")
        self.assertIsNone(parsed["final_energy"])
        self.assertIsNone(parsed["scf_energy"])
        self.assertIsNone(parsed["total_zpe_energy"])
        self.assertIsNone(parsed["total_enthalpy"])
        self.assertIsNone(parsed["total_free_energy"])
        self.assertIsNotNone(parsed["simulated_energy"])
        self.assertTrue(parsed["simulation_warning"])

    def test_08_normal_termination_with_unconverged_opt_and_4col_table(self):
        """Normal termination with NO in 4-column convergence table must flag opt_converged=False."""
        log_text = """
 # B3LYP/6-31G(d) opt
 SCF Done:  E(RB3LYP) =  -1.150000000     A.U. after    4 cycles
         Item               Value     Threshold  Converged?
 Maximum Force            0.012345     0.000450     NO
 RMS     Force            0.008000     0.000300     NO
 Maximum Displacement     0.001000     0.001800     YES
 RMS     Displacement     0.000700     0.001200     YES
 Normal termination of Gaussian 16 at Thu Jan 01 00:00:00 2026.
"""
        parsed = output_to_dict(parse_gaussian_log(log_text, filename="unconv_opt.log"))
        self.assertTrue(parsed["normal_termination"])
        self.assertFalse(parsed["opt_converged"])
        self.assertFalse(parsed["stationary_point"])
        self.assertAlmostEqual(parsed["max_force"], 0.012345, places=6)
        self.assertTrue(any("未收敛到驻点" in w for w in parsed["warnings"]))

    def test_09_bse_metadata_only_vs_gen_ecp_warning(self):
        """Offline BSE index must advertise metadata_only=True; Gen/GenECP without append_text warns."""
        client = BasisSetClient(base_url="https://invalid.domain.never.resolves.example.com")
        client._metadata_cache = None
        items = client.list_basis_sets()
        self.assertTrue(items)
        self.assertTrue(items[0].get("metadata_only"))
        self.assertIn("get_basis_set", items[0].get("note", ""))

        res_gen = generate_gjf(GaussianInputRequest(job_name="fe_gen", method="B3LYP", basis="GenECP", atoms=[("Fe", 0, 0, 0)]))
        self.assertTrue(any("GenECP" in w and "append_text" in w for w in res_gen["warnings"]))

    def test_10_incomplete_multistep_link1_and_truncated_log(self):
        """Step 1 Normal termination followed by Link1 failure or truncation must NOT report normal_termination=True."""
        link1_err = """
 # B3LYP/6-31G(d) opt
 SCF Done:  E(RB3LYP) =  -76.410000000     A.U. after    5 cycles
 Optimization completed.
    -- Stationary point found.
 Normal termination of Gaussian 16 at Thu Jan 01 00:00:00 2026.
 --Link1--
 # B3LYP/6-31G(d) freq
 SCF Done:  E(RB3LYP) =  -76.410000000     A.U. after    5 cycles
 Error termination via Lnk1e in D:\\G16W\\l716.exe
"""
        r_err = output_to_dict(parse_gaussian_log(link1_err, filename="link1_err.log"))
        self.assertFalse(r_err["normal_termination"])
        self.assertTrue(r_err["incomplete_multistep"])
        self.assertEqual(r_err["route_steps"], 2)
        self.assertEqual(r_err["calculation_type"], "freq")
        self.assertTrue(any("多步" in w for w in r_err["warnings"]))

        link1_trunc = """
 Entering Link 1 = D:\\G16W\\l1.exe
 # B3LYP/6-31G(d) opt
 SCF Done:  E(RB3LYP) =  -76.410000000     A.U. after    5 cycles
 Normal termination of Gaussian 16 at Thu Jan 01 00:00:00 2026.
 Entering Link 1 = D:\\G16W\\l1.exe
 # B3LYP/6-31G(d) freq
 SCF Done:  E(RB3LYP) =  -76.410000000     A.U. after    5 cycles
"""
        r_trunc = output_to_dict(parse_gaussian_log(link1_trunc, filename="link1_trunc.log"))
        self.assertFalse(r_trunc["normal_termination"])
        self.assertTrue(r_trunc["incomplete_multistep"])
        self.assertEqual(r_trunc["route_steps"], 2)
        self.assertTrue(any("多步" in w for w in r_trunc["warnings"]))


if __name__ == "__main__":
    unittest.main()
