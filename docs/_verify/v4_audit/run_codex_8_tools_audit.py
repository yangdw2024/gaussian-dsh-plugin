"""Comprehensive Codex CLI Acceptance Verification for all 8 Gaussian MCP Tools.

Executes each tool via non-interactive Codex CLI under controlled sandbox (`--approve-for-me`),
records input, output, latency, status (PASS / BLOCKED / FAIL), and produces structured evidence.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

CODEX_CMD = r"D:\nodejs\codex.cmd"
MODEL = "gpt-5.6-sol"
AUDIT_DIR = Path(__file__).resolve().parent
AUDIT_JSON = AUDIT_DIR / "codex_8_tools_audit.json"

TOOLS_TO_TEST = [
    {
        "tool": "gaussian_status",
        "description": "Query Gaussian computational environment, paths, budget, and scheduler status",
        "prompt": "Use the gaussian_status tool from gaussian MCP server. Output only a one-line JSON string containing status and gaussian.exists.",
    },
    {
        "tool": "generate_gaussian_input",
        "description": "Construct Gaussian .gjf file from molecular coordinates",
        "prompt": "Use the generate_gaussian_input tool from gaussian MCP server with job_name='h2_audit', atoms=[['H', 0, 0, 0], ['H', 0, 0, 0.74]], save_to_file=false. Output the filename and atom_count.",
    },
    {
        "tool": "parse_gaussian_output",
        "description": "Parse Gaussian log and extract scientific metrics",
        "prompt": "Use the parse_gaussian_output tool from gaussian MCP server with content=' Entering Link 1 ... \\n SCF Done:  E(RHF) =  -1.1175 A.U.\\n Normal termination of Gaussian 16\\n'. Output the normal_termination and final_energy.",
    },
    {
        "tool": "diagnose_gaussian_error",
        "description": "Diagnose Gaussian calculation errors and provide remedies",
        "prompt": "Use the diagnose_gaussian_error tool from gaussian MCP server with error_text='Convergence failure in SCF'. Output the number of diagnoses found and first solution.",
    },
    {
        "tool": "search_gaussian_keywords",
        "description": "Search curated keywords, functionals, job types, and SCF controls",
        "prompt": "Use the search_gaussian_keywords tool from gaussian MCP server with query='B3LYP', limit=3. Output the returned count and keyword names.",
    },
    {
        "tool": "search_basis_sets",
        "description": "Search Basis Set Exchange library with local cache",
        "prompt": "Use the search_basis_sets tool from gaussian MCP server with query='def2-svp', limit=2. Output count and basis_sets display names.",
    },
    {
        "tool": "get_basis_set",
        "description": "Fetch basis set definition for specified elements",
        "prompt": "Use the get_basis_set tool from gaussian MCP server with name='6-31g', elements=[1, 6], save_to_file=false. Output ok and content character length.",
    },
    {
        "tool": "generate_gaussian_input_from_smiles",
        "description": "Generate 3D conformer from SMILES and construct .gjf file",
        "prompt": "Use the generate_gaussian_input_from_smiles tool from gaussian MCP server with smiles='CCO', job_name='audit_ethanol', save_to_file=false. Output atom_count and smiles_info charge.",
    },
]


def run_test():
    audit_results = []
    print(f"Starting Codex Acceptance Audit for 8 MCP Tools (Model: {MODEL}, Sandbox: workspace-write via --approve-for-me)...")

    for idx, item in enumerate(TOOLS_TO_TEST, 1):
        tool_name = item["tool"]
        prompt = item["prompt"]
        print(f"\n[{idx}/8] Testing tool: {tool_name}...")

        cmd = [
            CODEX_CMD,
            "exec",
            "-m", MODEL,
            "--ephemeral",
            "--approve-for-me",
            prompt,
        ]

        t0 = time.time()
        try:
            # Send null input to stdin so non-interactive codex exec doesn't hang
            proc = subprocess.run(
                cmd,
                input="",
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=60,
            )
            duration = round(time.time() - t0, 3)
            exit_code = proc.returncode
            stdout_text = proc.stdout.strip()
            stderr_text = proc.stderr.strip()
            combined_text = f"{stdout_text}\n{stderr_text}"

            tool_invoked = f"gaussian/{tool_name}" in combined_text or f"mcp: gaussian/{tool_name}" in combined_text
            passed = exit_code == 0 and tool_invoked

            status = "PASS" if passed else ("BLOCKED" if "approval" in stdout_text.lower() else "FAIL")

            record = {
                "tool": tool_name,
                "description": item["description"],
                "prompt": prompt,
                "exit_code": exit_code,
                "duration_seconds": duration,
                "tool_invoked": tool_invoked,
                "status": status,
                "stdout_snippet": stdout_text[-1200:] if len(stdout_text) > 1200 else stdout_text,
                "stderr_snippet": stderr_text[:500] if stderr_text else "",
            }
            audit_results.append(record)
            print(f"    -> Status: {status} (Duration: {duration}s, Invoked: {tool_invoked})")

        except subprocess.TimeoutExpired:
            duration = round(time.time() - t0, 3)
            print(f"    -> Status: BLOCKED (Timeout after {duration}s)")
            audit_results.append({
                "tool": tool_name,
                "description": item["description"],
                "prompt": prompt,
                "exit_code": -1,
                "duration_seconds": duration,
                "tool_invoked": False,
                "status": "BLOCKED",
                "stdout_snippet": "Subprocess timed out after 60s",
                "stderr_snippet": "",
            })
        except Exception as exc:
            duration = round(time.time() - t0, 3)
            print(f"    -> Status: FAIL ({exc})")
            audit_results.append({
                "tool": tool_name,
                "description": item["description"],
                "prompt": prompt,
                "exit_code": -1,
                "duration_seconds": duration,
                "tool_invoked": False,
                "status": "FAIL",
                "stdout_snippet": str(exc),
                "stderr_snippet": "",
            })

    report = {
        "client": "OpenAI Codex CLI v0.148.0",
        "model": MODEL,
        "mode": "non-interactive stdio MCP",
        "sandbox": "workspace-write (governed by --approve-for-me)",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_tools": len(TOOLS_TO_TEST),
        "passed": sum(1 for r in audit_results if r["status"] == "PASS"),
        "blocked": sum(1 for r in audit_results if r["status"] == "BLOCKED"),
        "failed": sum(1 for r in audit_results if r["status"] == "FAIL"),
        "results": audit_results,
    }

    AUDIT_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nAudit complete! Report saved to {AUDIT_JSON}")
    print(f"Summary: {report['passed']} PASS, {report['blocked']} BLOCKED, {report['failed']} FAIL")


if __name__ == "__main__":
    run_test()
