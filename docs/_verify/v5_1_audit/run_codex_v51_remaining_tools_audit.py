"""V5.1 Codex CLI Acceptance Verification for Previously Uncovered Gaussian MCP Tools.

Covers the 4 tools not covered in V5.0's 8-tool Codex audit:
1. search_gaussian_keywords
2. search_basis_sets
3. get_basis_set
4. stop_gaussian_calculation (live mock submit -> verify is_simulated/real_gaussian_result -> stop)
"""
from __future__ import annotations

import json
import sys
import subprocess
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.config import settings
from backend.job_manager import job_manager

CODEX_CMD = r"D:\nodejs\codex.cmd"
MODEL = "gpt-5.6-sol"
AUDIT_DIR = Path(__file__).resolve().parent
AUDIT_JSON = AUDIT_DIR / "codex_remaining_tools_audit.json"

TESTS = [
    {
        "tool": "search_gaussian_keywords",
        "required_tools": ["search_gaussian_keywords"],
        "prompt": (
            "Call the search_gaussian_keywords tool from the gaussian MCP server with query='B3LYP'. "
            "Output a one-line JSON object containing keyword 'B3LYP' and the count of matches returned."
        ),
    },
    {
        "tool": "search_basis_sets",
        "required_tools": ["search_basis_sets"],
        "prompt": (
            "Call the search_basis_sets tool from the gaussian MCP server with query='def2-svp' and limit=5. "
            "Output a one-line JSON object containing the first matched basis set name and total results."
        ),
    },
    {
        "tool": "get_basis_set",
        "required_tools": ["get_basis_set"],
        "prompt": (
            "Call the get_basis_set tool from the gaussian MCP server with name='6-31g*', elements=[1, 6], "
            "format='gaussian94', save_to_file=false. Output a one-line JSON object with format and content_length."
        ),
    },
    {
        "tool": "stop_gaussian_calculation",
        "required_tools": [
            "generate_gaussian_input",
            "submit_gaussian_calculation",
            "stop_gaussian_calculation",
        ],
        "prompt": (
            "Do these 3 steps using the gaussian MCP server tools: "
            "1) Call generate_gaussian_input with job_name='v51_codex_stop_test', job_type='sp', method='HF', "
            "basis='STO-3G', atoms=[['H',0,0,0],['H',0,0,0.74]], save_to_file=true. "
            "2) Call submit_gaussian_calculation with the returned saved_path, job_name='v51_codex_stop_test', "
            "dry_run=false, mock_mode=true, mock_duration=15.0. Confirm is_simulated and real_gaussian_result. "
            "3) Call stop_gaussian_calculation with the returned job_id. "
            "Output a single JSON object containing job_id, stop_ok, status, is_simulated, and real_gaussian_result."
        ),
    },
    {
        "tool": "submit_gaussian_calculation_auth_guard",
        "required_tools": ["generate_gaussian_input", "submit_gaussian_calculation"],
        "prompt": (
            "Do these 2 steps using the gaussian MCP server tools: "
            "1) Call generate_gaussian_input with job_name='v51_codex_auth_guard', job_type='sp', method='HF', "
            "basis='STO-3G', atoms=[['H',0,0,0],['H',0,0,0.74]], save_to_file=true. "
            "2) Call submit_gaussian_calculation dry_run=true to obtain integrity_token, then attempt "
            "submit_gaussian_calculation with dry_run=false, confirmed=true, integrity_token=<token>, mock_mode=false "
            "(do NOT pass mock_mode=true). Confirm it is rejected cleanly without launching Gaussian. "
            "Output a single JSON object containing ok, rejected_layer, and error."
        ),
    },
]


def _cleanup_temp_jobs_and_files() -> None:
    """Clean up temporary v51_codex_* artifacts generated in default work/data dir."""
    try:
        for gj in job_manager.list_jobs(limit=50):
            jname = str(gj.get("job_name", ""))
            if jname.startswith("v51_codex_"):
                jid = gj.get("job_id")
                for k in ("gjf_path", "log_path", "chk_path"):
                    p = gj.get(k)
                    if p:
                        Path(p).unlink(missing_ok=True)
                if jid:
                    (job_manager.jobs_dir / f"{jid}.json").unlink(missing_ok=True)
                    (job_manager.jobs_dir / f"{jid}.recover.json").unlink(missing_ok=True)
        work_dir = settings.work_dir
        if work_dir.exists():
            for pat in ("v51_codex_*.gjf", "v51_codex_*.log", "v51_codex_*.chk"):
                for p in work_dir.glob(pat):
                    p.unlink(missing_ok=True)
    except Exception:
        pass


def run_audit() -> int:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    print("Starting Codex CLI V5.1 Acceptance Audit (remaining 4 tools + auth guard)...")
    print(f"Model: {MODEL}, Sandbox: --approve-for-me --ephemeral")

    for idx, item in enumerate(TESTS, 1):
        label = item["tool"]
        prompt = item["prompt"]
        print(f"\n[{idx}/{len(TESTS)}] Testing: {label}...")
        cmd = [
            CODEX_CMD,
            "exec",
            "-m",
            MODEL,
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
                errors="replace",
                timeout=90,
            )
            duration = round(time.time() - t0, 3)
            stdout_text = proc.stdout.strip()
            stderr_text = proc.stderr.strip()
            combined = f"{stdout_text}\n{stderr_text}"

            invoked_map = {
                req: (
                    f"gaussian/{req}" in combined
                    or f"mcp: gaussian/{req}" in combined
                    or f"gaussian__{req}" in combined
                )
                for req in item["required_tools"]
            }
            all_invoked = all(invoked_map.values())
            passed = proc.returncode == 0 and all_invoked
            if label == "submit_gaussian_calculation_auth_guard":
                passed = passed and ("human_authorization" in combined or "human" in combined.lower())

            status = (
                "PASS"
                if passed
                else ("BLOCKED" if "approval" in combined.lower() else "FAIL")
            )
            results.append(
                {
                    "index": idx,
                    "test": label,
                    "required_tools": invoked_map,
                    "status": status,
                    "exit_code": proc.returncode,
                    "duration_seconds": duration,
                    "codex_output_preview": stdout_text[-600:],
                    "codex_events_preview": stderr_text[-800:],
                }
            )
            print(f"  Result: {status} (exit_code={proc.returncode}, duration={duration}s, invoked={invoked_map})")
        except subprocess.TimeoutExpired:
            results.append(
                {
                    "index": idx,
                    "test": label,
                    "required_tools": {t: False for t in item["required_tools"]},
                    "status": "FAIL",
                    "exit_code": -1,
                    "duration_seconds": 90.0,
                    "codex_output_preview": "TIMED OUT",
                    "codex_events_preview": "",
                }
            )
            print("  Result: FAIL (Timeout after 90s)")

    _cleanup_temp_jobs_and_files()

    passed_cnt = sum(1 for r in results if r["status"] == "PASS")
    summary = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "client": "Codex CLI",
        "model": MODEL,
        "security_flags": "--approve-for-me --ephemeral",
        "total_tested": len(results),
        "passed": passed_cnt,
        "pass_rate": f"{(passed_cnt / len(results)) * 100:.1f}%",
        "results": results,
    }
    AUDIT_JSON.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nCodex V5.1 Audit Complete: {passed_cnt}/{len(results)} PASSED ({summary['pass_rate']})")
    print(f"Audit log saved to: {AUDIT_JSON}")
    return 0 if passed_cnt == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(run_audit())
