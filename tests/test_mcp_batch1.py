"""Comprehensive tests for Batch 1 MCP tools with Read/Write security boundary checks:
- gaussian_status
- generate_gaussian_input
- parse_gaussian_output
- diagnose_gaussian_error
"""
from __future__ import annotations

import asyncio
import os
import sys
import unittest
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import settings
from backend.mcp_server import mcp


class TestMCPBatch1(unittest.IsolatedAsyncioTestCase):
    async def test_tool_discovery(self):
        """Verify that all 4 tools are registered and discoverable."""
        tools = await mcp.list_tools()
        names = {t.name for t in tools}
        expected = {
            "gaussian_status",
            "generate_gaussian_input",
            "parse_gaussian_output",
            "diagnose_gaussian_error",
        }
        self.assertTrue(expected.issubset(names), f"Missing tools: {expected - names}")

    async def test_gaussian_status(self):
        """Verify gaussian_status returns complete environment status with segregated roots."""
        content, structured = await mcp.call_tool("gaussian_status", {})
        data = structured.get("result") if isinstance(structured, dict) and "result" in structured else structured
        if not data and content:
            import json
            data = json.loads(content[0].text)

        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["server_version"], "0.2.0")
        self.assertIn("gaussian", data)
        self.assertIn("directories", data)
        self.assertIn("resource_budget", data)
        self.assertIn("allowed_read_roots", data["directories"])
        self.assertIn("allowed_write_roots", data["directories"])
        self.assertTrue(len(data["directories"]["allowed_write_roots"]) >= 1)

    async def test_generate_gaussian_input_valid(self):
        """Verify generation of Gaussian .gjf for H2 molecule."""
        atoms = [
            ["H", 0.0, 0.0, 0.0],
            ["H", 0.0, 0.0, 0.74],
        ]
        params = {
            "job_name": "h2_test",
            "job_type": "opt",
            "method": "B3LYP",
            "basis": "6-31G(d)",
            "charge": 0,
            "multiplicity": 1,
            "atoms": atoms,
            "save_to_file": True,
        }
        content, structured = await mcp.call_tool("generate_gaussian_input", params)
        data = structured.get("result") if isinstance(structured, dict) and "result" in structured else structured
        if not data and content:
            import json
            data = json.loads(content[0].text)

        self.assertIn("content", data)
        self.assertIn("%mem=", data["content"])
        self.assertIn("%nosave", data["content"])
        self.assertIn("%chk=", data["content"])
        self.assertIn("# B3LYP/6-31G(d) opt", data["content"])
        self.assertEqual(data["atom_count"], 2)
        self.assertIsNotNone(data["saved_path"])

        saved = Path(data["saved_path"])
        self.assertTrue(saved.exists(), "GJF file was not written to disk")
        # Cleanup
        try:
            saved.unlink()
        except Exception:
            pass

    async def test_generate_gaussian_input_boundary_violation(self):
        """Verify that attempting to write to unauthorized directory is blocked."""
        atoms = [["H", 0.0, 0.0, 0.0], ["H", 0.0, 0.0, 0.74]]
        params = {
            "job_name": "evil_escape",
            "atoms": atoms,
            "save_to_file": True,
            "output_dir": "../../../../../Windows/System32",
        }
        with self.assertRaises(Exception) as ctx:
            await mcp.call_tool("generate_gaussian_input", params)
        self.assertTrue(
            "Security Boundary Violation" in str(ctx.exception)
            or "PermissionError" in str(ctx.exception)
            or "outside authorized" in str(ctx.exception)
        )

    async def test_generate_gaussian_input_rejects_writing_to_repo_source(self):
        """Crucial test: attempting to write generated gjf into project repo root must be blocked."""
        atoms = [["H", 0.0, 0.0, 0.0], ["H", 0.0, 0.0, 0.74]]
        params = {
            "job_name": "overwrite_attempt",
            "atoms": atoms,
            "save_to_file": True,
            "output_dir": str(PROJECT_ROOT),
        }
        with self.assertRaises(Exception) as ctx:
            await mcp.call_tool("generate_gaussian_input", params)
        self.assertTrue("Security Boundary Violation" in str(ctx.exception))

    async def test_generate_gaussian_input_atom_limit(self):
        """Verify that system exceeding atom safety limit is rejected."""
        large_atoms = [["C", float(i), 0.0, 0.0] for i in range(settings.max_atoms + 5)]
        params = {
            "job_name": "too_big",
            "atoms": large_atoms,
            "save_to_file": False,
        }
        with self.assertRaises(Exception) as ctx:
            await mcp.call_tool("generate_gaussian_input", params)
        self.assertIn("exceeding authorized", str(ctx.exception))

    async def test_parse_gaussian_output_content(self):
        """Verify parsing synthetic Gaussian output log."""
        sample_log = """
 Entering Gaussian System, Inc.
 # B3LYP/6-31G(d) opt
 -------------------
 Charge =  0 Multiplicity = 1
 NAtoms= 2 NBasis= 10
 SCF Done:  E(RB3LYP) =  -1.17547890123     A.U. after    6 cycles
 Alpha  occ. eigenvalues --   -0.58231
 Alpha virt. eigenvalues --    0.04523    0.12345
 Maximum Force            0.000012     YES
 RMS     Force            0.000008     YES
 Maximum Displacement     0.000045     YES
 RMS     Displacement     0.000030     YES
 Stationary point found.
 Normal termination of Gaussian 16 at Mon Nov 10 12:00:00 2026.
"""
        params = {"content": sample_log}
        content, structured = await mcp.call_tool("parse_gaussian_output", params)
        data = structured.get("result") if isinstance(structured, dict) and "result" in structured else structured
        if not data and content:
            import json
            data = json.loads(content[0].text)

        self.assertTrue(data["normal_termination"])
        self.assertEqual(data["final_energy"], -1.17547890123)
        self.assertTrue(data["opt_converged"])
        self.assertTrue(data["stationary_point"])
        self.assertAlmostEqual(data["homo_energy"], -0.58231, places=5)
        self.assertAlmostEqual(data["lumo_energy"], 0.04523, places=5)
        self.assertAlmostEqual(data["homo_lumo_gap"], 0.04523 - (-0.58231), places=5)

    async def test_parse_gaussian_output_boundary_violation(self):
        """Verify that reading unauthorized path is blocked by security boundary."""
        params = {"file_path": "C:\\Windows\\System32\\drivers\\etc\\hosts"}
        with self.assertRaises(Exception) as ctx:
            await mcp.call_tool("parse_gaussian_output", params)
        self.assertTrue(
            "Security Boundary Violation" in str(ctx.exception)
            or "PermissionError" in str(ctx.exception)
            or "outside authorized" in str(ctx.exception)
        )

    async def test_parse_gaussian_output_missing_file(self):
        """Verify proper error on non-existent file."""
        params = {"file_path": str(settings.work_dir / "ghost_file_12345.log")}
        with self.assertRaises(Exception) as ctx:
            await mcp.call_tool("parse_gaussian_output", params)
        self.assertTrue(
            "does not exist" in str(ctx.exception)
            or "FileNotFoundError" in str(ctx.exception)
        )

    async def test_diagnose_gaussian_error(self):
        """Verify error diagnosis matching curated computational chemistry rules."""
        params = {"error_text": "Convergence failure -- run terminated in Link 502"}
        content, structured = await mcp.call_tool("diagnose_gaussian_error", params)
        data = structured.get("result") if isinstance(structured, dict) and "result" in structured else structured
        if not data and content:
            import json
            data = json.loads(content[0].text)

        self.assertGreater(data["diagnosis_count"], 0)
        diagnoses = data["diagnoses"]
        error_names = [d["error"] for d in diagnoses]
        self.assertTrue(any("scf" in n.lower() or "convergence" in n.lower() or "收敛" in n for n in error_names))
        # Ensure solution is present and actionable
        self.assertIn("solution", diagnoses[0])
        self.assertTrue(len(diagnoses[0]["solution"]) > 5)

    async def test_diagnose_gaussian_error_with_sobko_unstarted_fallback(self):
        """Regression test: query_knowledge_base=True when Sobko is not running must fall back gracefully without blocking."""
        import time
        t0 = time.time()
        params = {
            "error_text": "Out-of-memory / 内存不足",
            "query_knowledge_base": True,
        }
        content, structured = await mcp.call_tool("diagnose_gaussian_error", params)
        elapsed = time.time() - t0
        self.assertLess(elapsed, 1.0, f"Call blocked for {elapsed:.2f}s instead of fast fallback!")
        data = structured.get("result") if isinstance(structured, dict) and "result" in structured else structured
        if not data and content:
            import json
            data = json.loads(content[0].text)
        self.assertGreater(data["diagnosis_count"], 0)

    async def test_diagnose_gaussian_error_empty(self):
        """Verify empty error string is rejected."""
        params = {"error_text": "   "}
        with self.assertRaises(Exception):
            await mcp.call_tool("diagnose_gaussian_error", params)


if __name__ == "__main__":
    unittest.main()
