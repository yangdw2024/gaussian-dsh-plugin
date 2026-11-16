"""V5.0 Codex CLI Acceptance Verification for Gaussian MCP Tools.

Executes tools via non-interactive Codex CLI under controlled sandbox (`--approve-for-me`),
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
AUDIT_JSON = AUDIT_DIR / "codex_12_tools_audit.json"

TOOLS_TO_TEST = [
    {
        "tool": "gaussian_status",
        "description": "Query Gaussian computational environment, paths, budget, and scheduler status",
        "prompt": "Use the gaussian_status tool from gaussian MCP server. Output only a one-line JSON string containing status and gaussian.exists.",
    },
    {
        "tool": "list_gaussian_jobs",
        "description": "List Gaussian jobs, queue count, and scheduler status",
        "prompt": "Use the list_gaussian_jobs tool from gaussian MCP server with limit=5. Output only total_jobs and has_active_running_job.",
    },
    {
        "tool": "generate_gaussian_input",
        "description": "Construct Gaussian .gjf file from molecular coordinates",
        "prompt": "Use the generate_gaussian_input tool from gaussian MCP server with job_name='h2_v5_audit', atoms=[['H', 0, 0, 0], ['H', 0, 0, 0.74]], save_to_file=false. Output the filename and atom_count.",
    },
    {
        "tool": "generate_gaussian_input_from_smiles",
        "description": "Generate 3D conformer from SMILES and construct .gjf file",
        "prompt": "Use the generate_gaussian_input_from_smiles tool from gaussian MCP server with smiles='CCO', job_name='v5_ethanol', save_to_file=false. Output atom_count and smiles_info charge.",
    },
    {
        "tool": "submit_gaussian_calculation",
        "description": "Preflight inspection and execution of Gaussian calculation",
        "prompt": "Use the submit_gaussian_calculation tool from gaussian MCP server with gjf_path='E:\\\\YDW\\\\ChemDatas\\\\Gjf\\\\lifecycle_tests\\\\h2_test_lifecycle.gjf', dry_run=true. Output ok, dry_run, and preflight status.",
    },
    {
        "tool": "get_gaussian_job_status",
        "description": "Query real-time calculation status and log tail",
        "prompt": "Use the list_gaussian_jobs tool first to find a job_id, then call get_gaussian_job_status with that job_id. Output the status and job_id.",
    },
    {
        "tool": "diagnose_gaussian_error",
        "description": "Diagnose Gaussian calculation errors and provide remedies",
        "prompt": "Use the diagnose_gaussian_error tool from gaussian MCP server with error_text='Convergence failure in SCF'. Output the number of diagnoses found and first solution.",
    },
    {
        "tool": "parse_gaussian_output",
        "description": "Parse Gaussian log and extract scientific metrics",
        "prompt": "Use the parse_gaussian_output tool from gaussian MCP server with content=' Entering Link 1 ... \\n SCF Done:  E(RHF) =  -1.1175 A.U.\\n Normal termination of Gaussian 16\\n'. Output normal_termination and final_energy.",
    },
]


def run_audit():
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    audit_results = []
    print(f"Starting Codex Acceptance Audit for V5.0 Gaussian MCP Tools...")
    print(f"Model: {MODEL}, Sandbox: normal approval via --approve-for-me")

    for idx, item in enumerate(TOOLS_TO_TEST, 1):
        tool_name = item["tool"]
        prompt = item["prompt"]
        print(f"\n[{idx}/{len(TOOLS_TO_TEST)}] Testing tool: {tool_name}...")

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

            tool_invoked = (
                f"gaussian/{tool_name}" in combined_text
                or f"mcp: gaussian/{tool_name}" in combined_text
                or f"gaussian__{tool_name}" in combined_text
                or f"Calling tool: {tool_name}" in combined_text
                or f"Called {tool_name}" in combined_text
            )
            passed = exit_code == 0 and tool_invoked

            status = "PASS" if passed else ("BLOCKED" if "approval" in combined_text.lower() or "rejected" in combined_text.lower() else "FAIL")

            record = {
                "index": idx,
                "tool": tool_name,
                "status": status,
                "exit_code": exit_code,
                "tool_invoked": tool_invoked,
                "duration_seconds": duration,
                "prompt": prompt,
                "codex_output_preview": stdout_text[-400:],
                "codex_events_preview": stderr_text[-400:],
            }
            audit_results.append(record)
            print(f"  Result: {status} (exit_code={exit_code}, duration={duration}s, tool_invoked={tool_invoked})")

        except subprocess.TimeoutExpired:
            print(f"  Result: FAIL (Timeout after 60s)")
            audit_results.append({
                "index": idx,
                "tool": tool_name,
                "status": "FAIL",
                "exit_code": -1,
                "tool_invoked": False,
                "duration_seconds": 60.0,
                "prompt": prompt,
                "codex_output_preview": "TIMED OUT",
                "codex_events_preview": "",
            })

    total = len(audit_results)
    passed_cnt = sum(1 for r in audit_results if r["status"] == "PASS")
    summary = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "client": "Codex CLI",
        "model": MODEL,
        "security_flags": "--approve-for-me --ephemeral",
        "total_tested": total,
        "passed": passed_cnt,
        "pass_rate": f"{(passed_cnt / total) * 100:.1f}%",
        "results": audit_results,
    }

    AUDIT_JSON.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n==========================================")
    print(f"Codex Audit Complete: {passed_cnt}/{total} PASSED ({summary['pass_rate']})")
    print(f"Audit log saved to: {AUDIT_JSON}")
    print(f"==========================================")


if __name__ == "__main__":
    run_audit()
