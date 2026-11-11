"""Level 2 Protocol Integration Test for Gaussian MCP Server over stdio.

Spawns the MCP Server subprocess via stdio transport, sends standard JSON-RPC 2.0 frames,
and verifies tool listing, tool execution, and error handling without any stdout pollution.
"""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYTHON_EXE = sys.executable


class TestMCPProtocolStdio(unittest.TestCase):
    def setUp(self):
        cmd = [PYTHON_EXE, "mcp_server.py"]
        self.proc = subprocess.Popen(
            cmd,
            cwd=str(PROJECT_ROOT),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self.req_id = 0

    def tearDown(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    def send_rpc(self, method: str, params: dict | None = None) -> dict:
        self.req_id += 1
        msg = {
            "jsonrpc": "2.0",
            "id": self.req_id,
            "method": method,
        }
        if params is not None:
            msg["params"] = params
        wire = json.dumps(msg) + "\n"
        self.proc.stdin.write(wire)
        self.proc.stdin.flush()

        # Read line from stdout (must be valid JSON-RPC, no logging noise)
        line = self.proc.stdout.readline()
        if not line:
            stderr_out = self.proc.stderr.read()
            raise RuntimeError(f"Server closed connection unexpectedly. Stderr: {stderr_out}")
        try:
            return json.loads(line)
        except json.JSONDecodeError as exc:
            raise AssertionError(f"Stdout pollution detected! Non-JSON received: {line!r}") from exc

    def send_notification(self, method: str, params: dict | None = None) -> None:
        msg = {
            "jsonrpc": "2.0",
            "method": method,
        }
        if params is not None:
            msg["params"] = params
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()

    def test_full_stdio_handshake_and_tools(self):
        # 1. Initialize
        init_resp = self.send_rpc("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0.0"}
        })
        self.assertIn("result", init_resp, f"Initialize failed: {init_resp}")
        server_info = init_resp["result"].get("serverInfo", {})
        self.assertIn("Gaussian", server_info.get("name", ""))

        # 2. Initialized Notification
        self.send_notification("notifications/initialized")

        # 3. Tools list
        tools_resp = self.send_rpc("tools/list")
        self.assertIn("result", tools_resp)
        tools = tools_resp["result"]["tools"]
        tool_names = [t["name"] for t in tools]
        expected_tools = [
            "gaussian_status",
            "generate_gaussian_input",
            "parse_gaussian_output",
            "diagnose_gaussian_error",
            "search_gaussian_keywords",
            "search_basis_sets",
            "get_basis_set",
            "generate_gaussian_input_from_smiles",
            "submit_gaussian_calculation",
            "get_gaussian_job_status",
            "list_gaussian_jobs",
            "stop_gaussian_calculation",
            "extract_structure_from_file",
            "postprocess_capabilities",
            "create_postprocess_task",
            "get_postprocess_task",
            "list_postprocess_tasks",
        ]
        for expected in expected_tools:
            self.assertIn(expected, tool_names, f"Tool '{expected}' not found in registered tools")
        extra = set(tool_names) - set(expected_tools)
        self.assertTrue(extra.issubset({"sobko_search", "sobko_fetch"}), f"Unexpected tools: {extra}")

        # 4. Call gaussian_status
        status_resp = self.send_rpc("tools/call", {
            "name": "gaussian_status",
            "arguments": {}
        })
        self.assertIn("result", status_resp)
        content_items = status_resp["result"]["content"]
        self.assertTrue(len(content_items) > 0)
        status_data = json.loads(content_items[0]["text"])
        self.assertEqual(status_data["status"], "ok")

        # 5. Call generate_gaussian_input
        gen_resp = self.send_rpc("tools/call", {
            "name": "generate_gaussian_input",
            "arguments": {
                "job_name": "stdio_h2",
                "atoms": [["H", 0, 0, 0], ["H", 0, 0, 0.74]],
                "save_to_file": False
            }
        })
        self.assertIn("result", gen_resp)
        gen_data = json.loads(gen_resp["result"]["content"][0]["text"])
        self.assertIn("# B3LYP/6-31G(d,p) opt", gen_data["content"])
        self.assertEqual(gen_data["atom_count"], 2)

        # 6. Call diagnose_gaussian_error
        diag_resp = self.send_rpc("tools/call", {
            "name": "diagnose_gaussian_error",
            "arguments": {"error_text": "Out-of-memory in Link 502"}
        })
        self.assertIn("result", diag_resp)
        diag_data = json.loads(diag_resp["result"]["content"][0]["text"])
        self.assertGreater(diag_data["diagnosis_count"], 0)

        # 7. Call search_gaussian_keywords (Batch 2)
        kw_resp = self.send_rpc("tools/call", {
            "name": "search_gaussian_keywords",
            "arguments": {"query": "B3LYP", "limit": 5}
        })
        self.assertIn("result", kw_resp)
        kw_data = json.loads(kw_resp["result"]["content"][0]["text"])
        self.assertGreater(kw_data["count"], 0)

        # 8. Call generate_gaussian_input_from_smiles (Batch 2)
        smiles_resp = self.send_rpc("tools/call", {
            "name": "generate_gaussian_input_from_smiles",
            "arguments": {
                "smiles": "CCO",
                "job_name": "stdio_ethanol",
                "save_to_file": False
            }
        })
        self.assertIn("result", smiles_resp)
        smiles_data = json.loads(smiles_resp["result"]["content"][0]["text"])
        self.assertEqual(smiles_data["atom_count"], 9)
        self.assertIn("ethanol", smiles_data["filename"])


if __name__ == "__main__":
    unittest.main()
