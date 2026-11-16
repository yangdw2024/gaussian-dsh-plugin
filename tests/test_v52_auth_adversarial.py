"""V5.2 Adversarial Execution Authorization & Trust-Boundary Test Suite.

Exercises 7 adversarial attack vectors across MCP tools, REST endpoints, and
out-of-band human approval artifacts:
  1. Reading `<data_dir>/approvals/.human_signing_key` & `grants/` via MCP path sandbox (including whitelist escalation).
  2. Auditing live `mcp_server.py` stdio tool registry to confirm NO admin/signing/shell tools exist.
  3. Calling `/v1/admin/jobs/approve` with missing/wrong Bearer or non-loopback origin, plus testing DSH `/v1/jobs`
     enforcement of all 3 authorization layers (file_integrity -> human_authorization -> host_execution_gate).
  4. Forged HMAC tokens & mutated env flags (`GAUSSIAN_ALLOW_REAL_EXECUTION` without `.human_signing_key`).
  5. Replaying single-use `human_approval_token` and consuming single-use `grants/*.json` receipts.
  6. Tampering `.gjf` content or escalating `mem`/`nproc`/`job_name` after human approval.
  7. Cross-job token reuse (`Job A` -> `Job B`) & malformed/non-existent `job_id` status/stop path probing.

IMPORTANT ARCHITECTURAL NOTE:
  `GAUSSIAN_ALLOW_REAL_EXECUTION=false` + out-of-band `.human_signing_key` protect the MCP tool boundary
  and HTTP admin boundary against autonomous Agent calls. However, if a host grants the Agent OS-level
  shell execution (`bash`/`powershell`) under the SAME OS user account that owns `.human_signing_key`,
  that same-UID process could read host files or invoke CLI scripts unless OS-level privilege separation
  (dedicated service user + NTFS ACLs) is applied. Tests below verify both the enforced MCP/HTTP guarantees
  and document the explicit OS privilege separation boundary.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from backend.app import app  # noqa: E402
from backend.config import settings  # noqa: E402
from backend.execution_policy import (  # noqa: E402
    _approvals_dir,
    _hmac_sign,
    authorize_calculation_as_human,
    calculate_content_sha256,
)
from backend.mcp_server import (  # noqa: E402
    get_gaussian_job_status,
    parse_gaussian_output,
    stop_gaussian_calculation,
    submit_gaussian_calculation,
)
from backend.security import validate_safe_path  # noqa: E402

H2_A = (
    "%mem=2GB\n"
    "%nprocshared=2\n"
    "#p HF/STO-3G sp\n\n"
    "H2 adversarial A\n\n"
    "0 1\n"
    "H  0.0  0.0  0.0\n"
    "H  0.0  0.0  0.74\n\n"
)

H2_B = (
    "%mem=2GB\n"
    "%nprocshared=2\n"
    "#p HF/STO-3G sp\n\n"
    "H2 adversarial B\n\n"
    "0 1\n"
    "H  0.0  0.0  0.0\n"
    "H  0.0  0.0  0.75\n\n"
)


class TestV52AuthAdversarial(unittest.TestCase):
    """Adversarial hardening tests for MCP & DSH execution authorization boundaries."""

    def setUp(self) -> None:
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="gaussian_v52_adv_"))
        self.data_dir = self.tmp_dir / "data"
        self.work_dir = self.tmp_dir / "work"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.work_dir.mkdir(parents=True, exist_ok=True)

        self._orig_env = {
            k: os.environ.get(k)
            for k in (
                "GAUSSIAN_DATA_DIR",
                "GAUSSIAN_WORK_DIR",
                "GAUSSIAN_ALLOWED_READ_ROOTS",
                "GAUSSIAN_ALLOWED_WRITE_ROOTS",
                "GAUSSIAN_ALLOW_REAL_EXECUTION",
                "GAUSSIAN_HUMAN_APPROVAL_SECRET",
                "GAUSSIAN_POLICY_SECRET",
                "GAUSSIAN_MANAGED_TOKEN",
            )
        }
        self._orig_work_dir = settings.work_dir
        self._orig_data_dir = settings.data_dir
        self._orig_managed_token = settings.managed_token

        os.environ["GAUSSIAN_DATA_DIR"] = str(self.data_dir)
        os.environ["GAUSSIAN_WORK_DIR"] = str(self.work_dir)
        os.environ["GAUSSIAN_ALLOWED_READ_ROOTS"] = str(self.work_dir)
        os.environ["GAUSSIAN_ALLOWED_WRITE_ROOTS"] = str(self.work_dir)
        os.environ["GAUSSIAN_ALLOW_REAL_EXECUTION"] = "false"
        os.environ.pop("GAUSSIAN_HUMAN_APPROVAL_SECRET", None)
        os.environ["GAUSSIAN_POLICY_SECRET"] = "v52-test-integrity-secret"
        os.environ["GAUSSIAN_MANAGED_TOKEN"] = "v52-host-admin-secret"

        settings.work_dir = self.work_dir
        settings.data_dir = self.data_dir
        settings.managed_token = "v52-host-admin-secret"
        (self.data_dir / "jobs").mkdir(parents=True, exist_ok=True)
        (self.data_dir / "logs").mkdir(parents=True, exist_ok=True)

        self.gjf_a = self.work_dir / "h2_a.gjf"
        self.gjf_b = self.work_dir / "h2_b.gjf"
        self.gjf_a.write_text(H2_A, encoding="utf-8")
        self.gjf_b.write_text(H2_B, encoding="utf-8")

    def tearDown(self) -> None:
        settings.work_dir = self._orig_work_dir
        settings.data_dir = self._orig_data_dir
        settings.managed_token = self._orig_managed_token
        for k, v in self._orig_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_01_adversarial_secret_and_grant_exfiltration_blocked_even_with_read_whitelist(self) -> None:
        """Attack 1: Even if READ roots include data_dir, approvals/.human_signing_key & grants remain blocked."""
        dry = submit_gaussian_calculation(gjf_path=str(self.gjf_a), dry_run=True)
        pre = dry["preflight"]
        grant_info = authorize_calculation_as_human(
            gjf_path=self.gjf_a,
            preflight_id=pre["preflight_id"],
            expected_sha256=pre["input_file"]["sha256"],
            mem="2GB",
            nproc=2,
            approved_by="pi_reviewer",
            save_receipt=True,
        )
        key_file = _approvals_dir() / ".human_signing_key"
        grant_file = Path(grant_info["receipt_saved"])
        self.assertTrue(key_file.exists())
        self.assertTrue(grant_file.exists())

        # Attacker broadens GAUSSIAN_ALLOWED_READ_ROOTS to include data_dir & approvals directly
        os.environ["GAUSSIAN_ALLOWED_READ_ROOTS"] = f"{self.work_dir};{self.data_dir};{_approvals_dir()}"

        for target in (key_file, grant_file, _approvals_dir() / "consumed" / "fake.used"):
            with self.assertRaises(PermissionError):
                validate_safe_path(target, mode="read")
            with self.assertRaises(PermissionError):
                parse_gaussian_output(file_path=str(target))
            with self.assertRaises(PermissionError):
                submit_gaussian_calculation(gjf_path=str(target), dry_run=True)

        # Relative traversal back into ../data/approvals/.human_signing_key
        rel_escape = os.path.relpath(key_file, self.work_dir)
        with self.assertRaises(PermissionError):
            validate_safe_path(rel_escape, mode="read")

    def test_02_mcp_stdio_registry_exposes_no_signing_or_admin_primitives(self) -> None:
        """Attack 2: Live mcp_server.py exposes strictly approved tools (17 core + optional Sobko) and blocks admin signing calls."""
        env = os.environ.copy()
        env["PYTHONPATH"] = str(REPO_ROOT)
        proc = subprocess.Popen(
            [sys.executable, "mcp_server.py"],
            cwd=str(REPO_ROOT),
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        try:
            assert proc.stdin and proc.stdout
            proc.stdin.write(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {},
                            "clientInfo": {"name": "adv-audit", "version": "1.0"},
                        },
                    }
                )
                + "\n"
            )
            proc.stdin.flush()
            init_resp = json.loads(proc.stdout.readline())
            self.assertIn("result", init_resp)

            proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}) + "\n")
            proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}) + "\n")
            proc.stdin.flush()
            tools_resp = json.loads(proc.stdout.readline())
            tool_names = {t["name"] for t in tools_resp["result"]["tools"]}

            approved_core = {
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
            }
            optional_sobko = {"sobko_search", "sobko_fetch"}
            self.assertEqual(approved_core - tool_names, set())
            self.assertEqual((tool_names - approved_core) - optional_sobko, set())
            forbidden_names = {
                "authorize_calculation_as_human",
                "admin_approve_gaussian_job",
                "run_shell",
                "execute_command",
                "approve_gaussian_job",
            }
            self.assertEqual(tool_names & forbidden_names, set())

            # Direct RPC invocation of forbidden admin function MUST fail
            proc.stdin.write(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 3,
                        "method": "tools/call",
                        "params": {"name": "authorize_calculation_as_human", "arguments": {}},
                    }
                )
                + "\n"
            )
            proc.stdin.flush()
            forged_call = json.loads(proc.stdout.readline())
            is_err = ("error" in forged_call) or bool(forged_call.get("result", {}).get("isError"))
            self.assertTrue(is_err, f"Expected error invoking nonexistent admin tool: {forged_call}")
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
            for s in (proc.stdin, proc.stdout, proc.stderr):
                if s:
                    try:
                        s.close()
                    except Exception:
                        pass

    def test_03_http_admin_auth_and_dsh_jobs_three_layer_parity(self) -> None:
        """Attack 3: /v1/admin/jobs/approve rejects invalid auth; /v1/jobs enforces all 3 layers."""
        with TestClient(app) as client:
            payload = {
                "gjf_path": str(self.gjf_a),
                "preflight_id": "fake_preflight_123",
                "job_name": "h2_a",
            }
            # Missing bearer when GAUSSIAN_MANAGED_TOKEN is set -> 403
            r_no_auth = client.post("/v1/admin/jobs/approve", json=payload)
            self.assertEqual(r_no_auth.status_code, 403)

            # Wrong bearer -> 403
            r_bad_auth = client.post(
                "/v1/admin/jobs/approve",
                json=payload,
                headers={"Authorization": "Bearer wrong-attacker-token"},
            )
            self.assertEqual(r_bad_auth.status_code, 403)

            # Even if GAUSSIAN_MANAGED_TOKEN is unset, TestClient non-loopback host ("testclient") -> 403
            settings.managed_token = None
            os.environ.pop("GAUSSIAN_MANAGED_TOKEN", None)
            r_non_loopback = client.post("/v1/admin/jobs/approve", json=payload)
            self.assertEqual(r_non_loopback.status_code, 403)

            # Restore managed token and check DSH POST /v1/jobs 3-layer parity under mocked g16
            settings.managed_token = "v52-host-admin-secret"
            os.environ["GAUSSIAN_ALLOW_REAL_EXECUTION"] = "true"

            # Direct POST /v1/jobs without integrity_token -> blocked at Layer 1 (file_integrity)
            with mock.patch("subprocess.Popen") as popen_mock:
                r1 = client.post("/v1/jobs", json={"job_name": "h2_a", "gjf_content": H2_A})
                self.assertEqual(r1.status_code, 200)
                b1 = r1.json()
                self.assertFalse(b1.get("ok"))
                self.assertEqual(b1.get("rejected_layer"), "file_integrity")
                popen_mock.assert_not_called()

                # POST /v1/jobs dry_run -> get integrity_token + preflight_id
                r_dry = client.post(
                    "/v1/jobs",
                    json={"job_name": "h2_a", "gjf_content": H2_A, "mem": "2GB", "nproc": 2, "dry_run": True},
                )
                self.assertTrue(r_dry.json()["ok"])
                pre = r_dry.json()["preflight"]

                # Submit via /v1/jobs with integrity_token ONLY (no human_approval_token) -> human_authorization
                r2 = client.post(
                    "/v1/jobs",
                    json={
                        "job_name": "h2_a",
                        "gjf_content": H2_A,
                        "mem": "2GB",
                        "nproc": 2,
                        "integrity_token": pre["integrity_token"],
                    },
                )
                self.assertFalse(r2.json().get("ok"))
                self.assertEqual(r2.json().get("rejected_layer"), "human_authorization")
                popen_mock.assert_not_called()

                # Now obtain human approval via bearer-protected /v1/admin/jobs/approve, BUT flip host gate false -> stops at host_execution_gate
                os.environ["GAUSSIAN_ALLOW_REAL_EXECUTION"] = "false"
                r_adm = client.post(
                    "/v1/admin/jobs/approve",
                    json={
                        "gjf_path": str(self.gjf_a),
                        "preflight_id": pre["preflight_id"],
                        "expected_sha256": pre["input_file"]["sha256"],
                        "job_name": "h2_a",
                        "mem": "2GB",
                        "nproc": 2,
                        "save_receipt": False,
                    },
                    headers={"Authorization": "Bearer v52-host-admin-secret"},
                )
                self.assertEqual(r_adm.status_code, 200)
                human_tok = r_adm.json()["human_approval_token"]

                r3 = client.post(
                    "/v1/jobs",
                    json={
                        "job_name": "h2_a",
                        "gjf_content": H2_A,
                        "mem": "2GB",
                        "nproc": 2,
                        "integrity_token": pre["integrity_token"],
                        "human_approval_token": human_tok,
                    },
                )
                self.assertFalse(r3.json().get("ok"))
                self.assertEqual(r3.json().get("rejected_layer"), "host_execution_gate")
                popen_mock.assert_not_called()

    def test_04_forged_hmac_and_agent_env_mutation_cannot_forge_human_grant(self) -> None:
        """Attack 4: Setting GAUSSIAN_ALLOW_REAL_EXECUTION=true & forging HMAC cannot mint human approval."""
        dry = submit_gaussian_calculation(gjf_path=str(self.gjf_a), dry_run=True, mem="2GB", nproc=2)
        pre = dry["preflight"]

        # Attacker mutates host execution flag in process env without possessing .human_signing_key
        os.environ["GAUSSIAN_ALLOW_REAL_EXECUTION"] = "true"
        forged_payload = {
            "kind": "human_approval",
            "grants_human_approval": True,
            "preflight_id": pre["preflight_id"],
            "sha256": pre["input_file"]["sha256"],
            "job_name": "h2_a",
            "mem": "2GB",
            "nproc": 2,
            "approved_by": "attacker",
            "nonce": "deadbeef" * 4,
            "exp": 9999999999.0,
        }
        forged_tok = _hmac_sign("GAUSSIAN_HUMAN_APPROVAL_DOMAIN::attacker-guessed-key", forged_payload)
        res = submit_gaussian_calculation(
            gjf_path=str(self.gjf_a),
            job_name="h2_a",
            mem="2GB",
            nproc=2,
            dry_run=False,
            mock_mode=False,
            integrity_token=pre["integrity_token"],
            human_approval_token=forged_tok,
        )
        self.assertFalse(res.get("ok"))
        self.assertEqual(res.get("rejected_layer"), "human_authorization")

    def test_05_single_use_token_and_receipt_replay_blocked(self) -> None:
        """Attack 5: Replaying consumed human_approval_token or receipt fails immediately without launching g16."""
        dry = submit_gaussian_calculation(gjf_path=str(self.gjf_a), dry_run=True, mem="2GB", nproc=2)
        pre = dry["preflight"]
        human = authorize_calculation_as_human(
            gjf_path=self.gjf_a,
            preflight_id=pre["preflight_id"],
            expected_sha256=pre["input_file"]["sha256"],
            job_name="h2_a",
            mem="2GB",
            nproc=2,
            approved_by="v52_pi",
            save_receipt=True,
        )
        receipt = Path(human["receipt_saved"])
        self.assertTrue(receipt.exists())

        os.environ["GAUSSIAN_ALLOW_REAL_EXECUTION"] = "true"
        fake_proc = mock.MagicMock()
        fake_proc.pid = 999991
        fake_proc.poll.return_value = 0

        with mock.patch("subprocess.Popen", return_value=fake_proc) as popen_mock:
            # First execution succeeds cleanly (mocked Popen, g16 never actually spawned)
            ok_res = submit_gaussian_calculation(
                gjf_path=str(self.gjf_a),
                job_name="h2_a",
                mem="2GB",
                nproc=2,
                dry_run=False,
                mock_mode=False,
                integrity_token=pre["integrity_token"],
                human_approval_token=human["human_approval_token"],
            )
            self.assertTrue(ok_res.get("ok"), ok_res)
            self.assertEqual(popen_mock.call_count, 1)
            self.assertFalse(receipt.exists(), "Single-use receipt should be removed after consumption")

            # Clean finished mocked job state so scheduler isn't the reason replay fails
            from backend.job_manager import job_manager
            job_manager.get_job(ok_res["job_id"])

            # Replay 1: reusing exact human_approval_token
            replay_tok = submit_gaussian_calculation(
                gjf_path=str(self.gjf_a),
                job_name="h2_a",
                mem="2GB",
                nproc=2,
                dry_run=False,
                mock_mode=False,
                integrity_token=pre["integrity_token"],
                human_approval_token=human["human_approval_token"],
            )
            self.assertFalse(replay_tok.get("ok"))
            self.assertEqual(replay_tok.get("rejected_layer"), "human_authorization")
            self.assertIn("already been used", replay_tok.get("error", ""))

            # Replay 2: relying on consumed receipt via preflight_id without token
            replay_rcpt = submit_gaussian_calculation(
                gjf_path=str(self.gjf_a),
                job_name="h2_a",
                mem="2GB",
                nproc=2,
                dry_run=False,
                mock_mode=False,
                integrity_token=pre["integrity_token"],
                preflight_id=pre["preflight_id"],
            )
            self.assertFalse(replay_rcpt.get("ok"))
            self.assertEqual(replay_rcpt.get("rejected_layer"), "human_authorization")
            self.assertEqual(popen_mock.call_count, 1)

    def test_06_post_approval_tampering_and_resource_escalation_blocked(self) -> None:
        """Attack 6: Altering .gjf coordinates or escalating mem/nproc/job_name fails verification."""
        dry = submit_gaussian_calculation(gjf_path=str(self.gjf_a), dry_run=True, mem="2GB", nproc=2)
        pre = dry["preflight"]
        human = authorize_calculation_as_human(
            gjf_path=self.gjf_a,
            preflight_id=pre["preflight_id"],
            expected_sha256=pre["input_file"]["sha256"],
            job_name="h2_a",
            mem="2GB",
            nproc=2,
            approved_by="v52_pi",
            save_receipt=False,
        )
        os.environ["GAUSSIAN_ALLOW_REAL_EXECUTION"] = "true"

        with mock.patch("subprocess.Popen") as popen_mock:
            # Resource escalation attempts (mem & nproc) against intact file
            esc_mem = submit_gaussian_calculation(
                gjf_path=str(self.gjf_a),
                job_name="h2_a",
                mem="64GB",
                nproc=2,
                dry_run=False,
                mock_mode=False,
                integrity_token=pre["integrity_token"],
                human_approval_token=human["human_approval_token"],
            )
            self.assertFalse(esc_mem.get("ok"))
            self.assertEqual(esc_mem.get("rejected_layer"), "file_integrity")

            esc_nproc = submit_gaussian_calculation(
                gjf_path=str(self.gjf_a),
                job_name="h2_a",
                mem="2GB",
                nproc=16,
                dry_run=False,
                mock_mode=False,
                integrity_token=pre["integrity_token"],
                human_approval_token=human["human_approval_token"],
            )
            self.assertFalse(esc_nproc.get("ok"))
            self.assertEqual(esc_nproc.get("rejected_layer"), "file_integrity")

            # Tamper file content even if a new integrity_token were re-issued on the mutated file -> Layer 3 blocks!
            self.gjf_a.write_text(H2_A.replace("0.74", "2.50"), encoding="utf-8")
            fresh_pre = submit_gaussian_calculation(gjf_path=str(self.gjf_a), dry_run=True, mem="2GB", nproc=2)["preflight"]
            tampered_with_fresh_int = submit_gaussian_calculation(
                gjf_path=str(self.gjf_a),
                job_name="h2_a",
                mem="2GB",
                nproc=2,
                dry_run=False,
                mock_mode=False,
                integrity_token=fresh_pre["integrity_token"],
                human_approval_token=human["human_approval_token"],
            )
            self.assertFalse(tampered_with_fresh_int.get("ok"))
            self.assertEqual(tampered_with_fresh_int.get("rejected_layer"), "human_authorization")
            popen_mock.assert_not_called()

    def test_07_cross_job_hijack_and_job_id_probing_blocked(self) -> None:
        """Attack 7: Tokens minted for Job A cannot run Job B; bogus/traversal job_ids fail cleanly."""
        dry_a = submit_gaussian_calculation(gjf_path=str(self.gjf_a), dry_run=True, mem="2GB", nproc=2)
        pre_a = dry_a["preflight"]
        human_a = authorize_calculation_as_human(
            gjf_path=self.gjf_a,
            preflight_id=pre_a["preflight_id"],
            expected_sha256=pre_a["input_file"]["sha256"],
            job_name="h2_a",
            mem="2GB",
            nproc=2,
            save_receipt=False,
        )
        dry_b = submit_gaussian_calculation(gjf_path=str(self.gjf_b), dry_run=True, mem="2GB", nproc=2)
        pre_b = dry_b["preflight"]

        os.environ["GAUSSIAN_ALLOW_REAL_EXECUTION"] = "true"
        with mock.patch("subprocess.Popen") as popen_mock:
            # Mix Job B file/integrity token with Job A's human approval token
            cross_job = submit_gaussian_calculation(
                gjf_path=str(self.gjf_b),
                job_name="h2_b",
                mem="2GB",
                nproc=2,
                dry_run=False,
                mock_mode=False,
                integrity_token=pre_b["integrity_token"],
                human_approval_token=human_a["human_approval_token"],
                preflight_id=pre_b["preflight_id"],
            )
            self.assertFalse(cross_job.get("ok"))
            self.assertEqual(cross_job.get("rejected_layer"), "human_authorization")
            popen_mock.assert_not_called()

        # Probe status/stop across forged or traversal job_ids
        for bad_id in ("nonexistent_job", "../../approvals/.human_signing_key", "../config"):
            with self.assertRaises(ValueError):
                get_gaussian_job_status(job_id=bad_id)
            stop_res = stop_gaussian_calculation(job_id=bad_id)
            self.assertFalse(stop_res.get("ok"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
