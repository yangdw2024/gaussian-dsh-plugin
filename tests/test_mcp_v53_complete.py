"""Phase 2 comprehensive tests for all 17 core MCP tools, optional Sobko extension,
structure extraction hardening, and Multiwfn/VMD/formchk post-processing hardening.
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend import app as backend_app
from backend import config as backend_config
from backend import mcp_server, structure_reader
from backend.postprocess import multiwfn as mwfn_mod
from backend.postprocess import vmd as vmd_mod
from backend.postprocess.manager import PostprocessManager, postprocess_manager
from backend.postprocess.models import PostprocessRequest


def _extract_mcp_result(res):
    content, structured = res
    if isinstance(structured, dict) and "result" in structured:
        return structured["result"]
    if structured is not None:
        return structured
    if content:
        return json.loads(content[0].text)
    return {}


def _write_minimal_fchk(path: Path) -> None:
    """Write a minimal valid Gaussian .fchk fixture suitable for fchk_reader / mo_levels."""
    lines = [
        "Minimal H2 test fchk for unit tests",
        "SP        RHF                                                         STO-3G",
        "Number of atoms                            I                2",
        "Charge                                     I                0",
        "Multiplicity                               I                1",
        "Number of electrons                        I                2",
        "Number of alpha electrons                  I                1",
        "Number of beta electrons                   I                1",
        "Number of basis functions                  I                2",
        "Number of independent functions            I                2",
        "Atomic numbers                             I   N=           2",
        "           1           1",
        "Current cartesian coordinates              R   N=           6",
        "  0.00000000E+00  0.00000000E+00  0.00000000E+00  0.00000000E+00  0.00000000E+00",
        "  1.39839733E+00",
        "Total Energy                               R    -1.11675931E+00",
        "Alpha Orbital Energies                     R   N=           2",
        " -5.78202900E-01  6.70319700E-01",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_cube(path: Path, nx: int, ny: int, nz: int) -> None:
    lines = [
        "Test cube header",
        "Generated in test",
        "    1    0.000000    0.000000    0.000000",
        f"{nx:5d}    0.200000    0.000000    0.000000",
        f"{ny:5d}    0.000000    0.200000    0.000000",
        f"{nz:5d}    0.000000    0.000000    0.200000",
        "    1    1.000000    0.000000    0.000000    0.000000",
        " 0.00000E+00",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class TestConfigAndStructureReader(unittest.TestCase):
    def test_config_no_duplicate_data_dir_override(self):
        with tempfile.TemporaryDirectory(prefix="cfg_test_") as td:
            env = {
                **os.environ,
                "GAUSSIAN_DATA_DIR": td,
            }
            out = subprocess.check_output(
                [
                    sys.executable,
                    "-c",
                    "import json; from backend.config import settings, SERVICE_VERSION; "
                    "print(json.dumps({'data_dir': str(settings.data_dir), 'version': SERVICE_VERSION}))",
                ],
                cwd=str(PROJECT_ROOT),
                env=env,
                text=True,
            )
            parsed = json.loads(out.strip())
            self.assertEqual(Path(parsed["data_dir"]).resolve(), Path(td).resolve())
            self.assertEqual(parsed["version"], backend_config.SERVICE_VERSION)

    def test_periodic_table_heavy_elements_and_dummy_handling(self):
        self.assertEqual(structure_reader._atnum_to_symbol(22), "Ti")
        self.assertEqual(structure_reader._atnum_to_symbol(46), "Pd")
        self.assertEqual(structure_reader._atnum_to_symbol(78), "Pt")
        self.assertEqual(structure_reader._atnum_to_symbol(118), "Og")
        self.assertIsNone(structure_reader._atnum_to_symbol(0))
        with self.assertRaises(ValueError):
            structure_reader._atnum_to_symbol(999)

        # Log orientation containing Ti and a dummy atom (atomic number 0)
        log_text = (
            "                         Standard orientation:\n"
            " ---------------------------------------------------------------------\n"
            " Center     Atomic      Atomic             Coordinates (Angstroms)\n"
            " Number     Number       Type             X           Y           Z\n"
            " ---------------------------------------------------------------------\n"
            "      1         22           0        0.000000    0.000000    0.000000\n"
            "      2          0           0        1.000000    0.000000    0.000000\n"
            "      3          8           0       -1.600000    0.000000    0.000000\n"
            " ---------------------------------------------------------------------\n"
        )
        coords, dummies = structure_reader._parse_orientation_block(log_text)
        self.assertEqual(dummies, 1)
        self.assertEqual([c[0] for c in coords], ["Ti", "O"])

    def test_extract_smiles_no_temp_dir_leak_and_rdkit_fallback(self):
        with tempfile.TemporaryDirectory(prefix="sr_test_") as td:
            tmp_root = Path(td)
            gjf = tmp_root / "ethanol.gjf"
            gjf.write_text(
                "# B3LYP/6-31G(d)\n\nethanol\n\n0 1\n"
                "C  -1.1867  -0.2472   0.0000\n"
                "C   0.2683   0.2330   0.0000\n"
                "O   1.0972  -0.9163   0.0000\n"
                "H  -1.7875   0.6656   0.0000\n"
                "H  -1.5724  -0.7852   0.8700\n"
                "H  -1.2698  -0.8805  -0.8860\n"
                "H   0.4150   0.8548   0.8860\n"
                "H   0.4609   0.8226  -0.8960\n"
                "H   1.9936  -0.5964   0.0000\n\n",
                encoding="utf-8",
            )

            before_dirs = set(Path(tempfile.gettempdir()).glob("struct_*"))
            res_ob = structure_reader.extract_smiles_from_file(str(gjf))
            after_ob = set(Path(tempfile.gettempdir()).glob("struct_*"))
            self.assertEqual(before_dirs, after_ob, "struct_* temp dir leaked in OpenBabel path")
            self.assertEqual(res_ob["natoms_guess"], 9)
            self.assertTrue(len(res_ob["smiles"]) >= 2)

            # Force RDKit fallback when obabel executable is missing
            with mock.patch.object(backend_config.settings, "obabel_exe", tmp_root / "missing_obabel.exe"):
                res_rk = structure_reader.extract_smiles_from_file(str(gjf))
            after_rk = set(Path(tempfile.gettempdir()).glob("struct_*"))
            self.assertEqual(before_dirs, after_rk, "struct_* temp dir leaked in RDKit fallback path")
            self.assertEqual(res_rk["extractor"], "rdkit_fallback")
            self.assertEqual(res_rk["natoms_guess"], 9)
            self.assertIn("O", res_rk["smiles"])
            self.assertIn("C", res_rk["smiles"])


class TestPostprocessHardening(unittest.TestCase):
    def test_generate_rdg_cube_commands_consistent_with_batch(self):
        cmds = mwfn_mod.generate_rdg_cube_commands(grid="coarse")
        lines = cmds.strip().splitlines()
        self.assertEqual(lines[0], "20")
        self.assertEqual(lines[1], "1")
        self.assertEqual(lines[2], "1")
        self.assertEqual(lines[3], "3")
        self.assertEqual(lines[-3:], ["0", "0", "q"])

    def test_cube_limit_enforced_before_vmd_render(self):
        with tempfile.TemporaryDirectory(prefix="pp_limit_") as td:
            td_p = Path(td)
            fchk = td_p / "tiny.fchk"
            _write_minimal_fchk(fchk)

            mgr = PostprocessManager()
            cube_out = td_p / "big_orb000001.cub"
            # 100*100*100 = 1,000,000 points
            _write_cube(cube_out, 100, 100, 100)

            with mock.patch.object(backend_config.settings, "data_dir", td_p / "data"), \
                 mock.patch.object(backend_config.settings, "postprocess_max_grid_points", 500_000), \
                 mock.patch.dict(os.environ, {"GAUSSIAN_DATA_DIR": str(td_p / "data")}), \
                 mock.patch("backend.postprocess.multiwfn.run_orbital_cube_batch", return_value=[cube_out]), \
                 mock.patch("backend.postprocess.vmd.render_orbitals") as vmd_mock:
                req = PostprocessRequest(kind="orbitals", fchk_path=str(fchk), orbitals=[1], grid="coarse", render=True)
                task = mgr.create_task(req)
                res = mgr.run_task(task.task_id, req, enforce_sandbox=False)

            self.assertFalse(res["ok"])
            self.assertIn("超过上限", res["error"])
            vmd_mock.assert_not_called()

    def test_vmd_cleans_intermediate_tga_after_png(self):
        with tempfile.TemporaryDirectory(prefix="vmd_clean_") as td:
            td_p = Path(td)
            cube = td_p / "orb000001.cub"
            _write_cube(cube, 2, 2, 2)
            fake_vmd = td_p / "vmd.exe"
            fake_vmd.write_text("stub", encoding="utf-8")

            from PIL import Image

            def _fake_spawn(cmd, cwd=None, stdout_file=None, stderr_file=None, env=None):
                tga = Path(cmd[cmd.index("-args") + 2])
                Image.new("RGB", (8, 8), color=(10, 20, 30)).save(tga, format="TGA")
                proc = mock.MagicMock()
                proc.returncode = 0
                proc.wait.return_value = 0
                return proc

            with mock.patch.object(backend_config.settings, "vmd_exe", fake_vmd), \
                 mock.patch.object(vmd_mod, "spawn_subprocess", side_effect=_fake_spawn):
                pngs = vmd_mod.render_orbitals([cube], td_p)

            self.assertEqual(len(pngs), 1)
            self.assertTrue(pngs[0].exists())
            self.assertEqual(pngs[0].suffix, ".png")
            self.assertFalse((td_p / "orbital_0.tga").exists(), "Intermediate .tga was not cleaned up")


class TestMCP17ToolsAndOptionalSobko(unittest.IsolatedAsyncioTestCase):
    async def test_all_17_core_tools_registered(self):
        tools = await mcp_server.mcp.list_tools()
        names = {t.name for t in tools}
        missing = set(mcp_server.CORE_TOOL_NAMES) - names
        self.assertEqual(missing, set(), f"Missing core MCP tools: {missing}")
        self.assertEqual(len(mcp_server.CORE_TOOL_NAMES), 17)

    async def test_extract_and_postprocess_mcp_tools_with_sandbox(self):
        with tempfile.TemporaryDirectory(prefix="mcp_v53_") as td:
            td_p = Path(td)
            work_dir = td_p / "work"
            data_dir = td_p / "data"
            outside_dir = td_p / "outside"
            work_dir.mkdir()
            data_dir.mkdir()
            outside_dir.mkdir()

            gjf = work_dir / "water.gjf"
            gjf.write_text(
                "# HF/STO-3G\n\nwater\n\n0 1\n"
                "O   0.0000   0.0000   0.1173\n"
                "H   0.0000   0.7572  -0.4692\n"
                "H   0.0000  -0.7572  -0.4692\n\n",
                encoding="utf-8",
            )
            fchk = work_dir / "h2.fchk"
            _write_minimal_fchk(fchk)
            secret_outside = outside_dir / "secret.gjf"
            secret_outside.write_text(gjf.read_text(encoding="utf-8"), encoding="utf-8")

            with mock.patch.object(backend_config.settings, "work_dir", work_dir), \
                 mock.patch.object(backend_config.settings, "data_dir", data_dir), \
                 mock.patch.dict(
                     os.environ,
                     {
                         "GAUSSIAN_WORK_DIR": str(work_dir),
                         "GAUSSIAN_DATA_DIR": str(data_dir),
                         "GAUSSIAN_ALLOWED_DIRS": str(work_dir),
                     },
                 ):
                # 1. extract_structure_from_file works cleanly inside allowed root
                ext_res = _extract_mcp_result(
                    await mcp_server.mcp.call_tool("extract_structure_from_file", {"file_path": str(gjf)})
                )
                self.assertTrue(ext_res["ok"])
                self.assertEqual(ext_res["natoms_guess"], 3)
                self.assertIn("O", ext_res["smiles"])

                # 2. extract_structure_from_file rejects outside path
                with self.assertRaises(Exception):
                    await mcp_server.mcp.call_tool("extract_structure_from_file", {"file_path": str(secret_outside)})

                # 3. postprocess_capabilities returns structured status
                cap_res = _extract_mcp_result(
                    await mcp_server.mcp.call_tool("postprocess_capabilities", {})
                )
                self.assertTrue(cap_res["ok"])
                self.assertIn("mo_levels", cap_res["supported_kinds"])

                # 4. create_postprocess_task with outside fchk is rejected
                with self.assertRaises(Exception):
                    await mcp_server.mcp.call_tool(
                        "create_postprocess_task",
                        {"kind": "mo_levels", "fchk_path": str(secret_outside)},
                    )

                # 5. create_postprocess_task mo_levels succeeds and generates SVG artifact
                pp_res = _extract_mcp_result(
                    await mcp_server.mcp.call_tool(
                        "create_postprocess_task",
                        {"kind": "mo_levels", "fchk_path": str(fchk), "wait": True, "wait_timeout_seconds": 30.0},
                    )
                )
                self.assertTrue(pp_res["ok"], pp_res)
                self.assertTrue(pp_res["completed"], pp_res)
                task_id = pp_res["task_id"]
                artifacts = pp_res["task"]["artifacts"]
                self.assertTrue(any(a["name"] == "mo_levels.svg" and a["size_bytes"] > 0 for a in artifacts))

                # 6. get_postprocess_task & list_postprocess_tasks
                got_res = _extract_mcp_result(
                    await mcp_server.mcp.call_tool("get_postprocess_task", {"task_id": task_id})
                )
                self.assertTrue(got_res["ok"])
                self.assertEqual(got_res["status"], "completed")

                # Traversal task_id rejected
                with self.assertRaises(Exception):
                    await mcp_server.mcp.call_tool("get_postprocess_task", {"task_id": "../evil"})

                list_res = _extract_mcp_result(
                    await mcp_server.mcp.call_tool("list_postprocess_tasks", {"kind_filter": "mo_levels"})
                )
                self.assertTrue(list_res["ok"])
                self.assertTrue(any(t["task_id"] == task_id for t in list_res["tasks"]))


class TestOptionalSobkoGracefulDegradation(unittest.TestCase):
    def _stdio_list_tools(self, env_overrides: dict) -> list[str]:
        env = {**os.environ, **env_overrides}
        proc = subprocess.Popen(
            [sys.executable, "-m", "backend.mcp_server"],
            cwd=str(PROJECT_ROOT),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            env=env,
        )
        try:
            init_req = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0"},
                },
            }
            notify = {"jsonrpc": "2.0", "method": "notifications/initialized"}
            list_req = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
            payload = "\n".join([json.dumps(init_req), json.dumps(notify), json.dumps(list_req)]) + "\n"
            stdout, stderr = proc.communicate(payload, timeout=15)
            responses = [json.loads(line) for line in stdout.splitlines() if line.strip()]
            list_resp = next(r for r in responses if r.get("id") == 2)
            return [t["name"] for t in list_resp["result"]["tools"]]
        finally:
            if proc.poll() is None:
                proc.kill()

    def test_mcp_starts_cleanly_without_sobko(self):
        with tempfile.TemporaryDirectory(prefix="no_sobko_") as td:
            tools = self._stdio_list_tools(
                {
                    "SOBKO_PROJECT_DIR": str(Path(td) / "missing_sobko_repo"),
                    "GAUSSIAN_MCP_ENABLE_SOBKO": "auto",
                    "GAUSSIAN_DATA_DIR": str(Path(td) / "data"),
                    "GAUSSIAN_WORK_DIR": str(Path(td) / "work"),
                }
            )
            self.assertEqual(len(tools), 17)
            self.assertNotIn("sobko_search", tools)
            self.assertIn("extract_structure_from_file", tools)
            self.assertIn("create_postprocess_task", tools)

    def test_sobko_explicit_enable_without_dir_graceful_error(self):
        with tempfile.TemporaryDirectory(prefix="sobko_graceful_") as td:
            tools = self._stdio_list_tools(
                {
                    "SOBKO_PROJECT_DIR": str(Path(td) / "missing_sobko_repo"),
                    "GAUSSIAN_MCP_ENABLE_SOBKO": "true",
                    "GAUSSIAN_DATA_DIR": str(Path(td) / "data"),
                    "GAUSSIAN_WORK_DIR": str(Path(td) / "work"),
                }
            )
            self.assertEqual(len(tools), 19)
            self.assertIn("sobko_search", tools)
            self.assertIn("sobko_fetch", tools)

            # Call sobko_search via subprocess when missing -> structured error, zero crash
            env = {
                **os.environ,
                "SOBKO_PROJECT_DIR": str(Path(td) / "missing_sobko_repo"),
                "GAUSSIAN_MCP_ENABLE_SOBKO": "true",
                "GAUSSIAN_DATA_DIR": str(Path(td) / "data"),
                "GAUSSIAN_WORK_DIR": str(Path(td) / "work"),
            }
            out = subprocess.check_output(
                [
                    sys.executable,
                    "-c",
                    "import asyncio, json; from backend.mcp_server import mcp; "
                    "c, s = asyncio.run(mcp.call_tool('sobko_search', {'query': 'B3LYP'})); "
                    "print(json.dumps(s.get('result', s)))",
                ],
                cwd=str(PROJECT_ROOT),
                env=env,
                text=True,
            )
            data = json.loads(out.strip())
            self.assertFalse(data["ok"])
            self.assertFalse(data["configured"])


if __name__ == "__main__":
    unittest.main()
