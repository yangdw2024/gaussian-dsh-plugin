"""V5.1 Execution authorization hardening & out-of-band human approval tests.

Verifies strict separation between:
1. File & parameter integrity (preflight integrity_token)
2. Host-level execution gate (GAUSSIAN_ALLOW_REAL_EXECUTION)
3. Out-of-band task-specific human authorization (authorize_calculation_as_human,
   scripts/approve_gaussian_job.py, and _require_admin-protected /v1/admin/jobs/approve)
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

import backend.app as app_module
from backend.app import app
from backend.execution_policy import (
    authorize_calculation_as_human,
    evaluate_real_execution_authorization,
    verify_integrity_token,
)
from backend.mcp_server import submit_gaussian_calculation
from backend.security import validate_safe_path

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestExecutionAuthorization(unittest.TestCase):
    """Adversarial authorization and trust-boundary tests."""

    def setUp(self):
        self._saved_env = {
            k: os.environ.get(k)
            for k in (
                "GAUSSIAN_DATA_DIR",
                "GAUSSIAN_WORK_DIR",
                "GAUSSIAN_ALLOWED_READ_ROOTS",
                "GAUSSIAN_ALLOWED_WRITE_ROOTS",
                "GAUSSIAN_ALLOW_REAL_EXECUTION",
                "GAUSSIAN_MANAGED_TOKEN",
            )
        }
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="gaussian_authz_"))
        self.data_dir = self.tmp_dir / "data"
        self.work_dir = self.tmp_dir / "work"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.work_dir.mkdir(parents=True, exist_ok=True)

        os.environ["GAUSSIAN_DATA_DIR"] = str(self.data_dir)
        os.environ["GAUSSIAN_WORK_DIR"] = str(self.work_dir)
        os.environ["GAUSSIAN_ALLOWED_READ_ROOTS"] = str(self.work_dir)
        os.environ["GAUSSIAN_ALLOWED_WRITE_ROOTS"] = str(self.work_dir)
        os.environ["GAUSSIAN_ALLOW_REAL_EXECUTION"] = "false"

        self.gjf_file = self.work_dir / "h2_authz.gjf"
        self.gjf_content = (
            "%mem=4GB\n"
            "%nprocshared=4\n"
            "#p B3LYP/6-31G(d) opt\n\n"
            "H2 authz test\n\n"
            "0 1\n"
            "H  0.0  0.0  0.0\n"
            "H  0.0  0.0  0.74\n\n"
        )
        self.gjf_file.write_text(self.gjf_content, encoding="utf-8")

    def tearDown(self):
        for k, v in self._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_01_dry_run_never_grants_human_approval(self):
        """Dry-run issues integrity_token with grants_human_approval=False and no human token."""
        res = submit_gaussian_calculation(
            gjf_path=str(self.gjf_file),
            job_name="h2_authz_job",
            mem="4GB",
            nproc=4,
            dry_run=True,
        )
        self.assertTrue(res.get("ok"))
        self.assertTrue(res.get("dry_run"))
        pre = res["preflight"]
        self.assertFalse(pre["authorization_model"]["grants_human_approval"])
        self.assertFalse(pre["authorization_model"]["layer_3_human_task_authorization_granted"])
        self.assertNotIn("human_approval_token", res)
        self.assertNotIn("human_approval_token", pre)

        tok = pre["integrity_token"]
        self.assertEqual(tok, pre["auth_token"])
        ok, msg, payload = verify_integrity_token(
            token=tok,
            current_sha256=pre["input_file"]["sha256"],
            expected_job_name="h2_authz_job",
            expected_mem="4GB",
            expected_nproc=4,
        )
        self.assertTrue(ok, msg)
        self.assertFalse(payload["grants_human_approval"])
        self.assertEqual(payload["kind"], "file_integrity")

    def test_02_confirmed_and_integrity_token_rejected_even_when_host_enabled(self):
        """confirmed=True + integrity_token cannot authorize real execution even with host flag on."""
        os.environ["GAUSSIAN_ALLOW_REAL_EXECUTION"] = "true"
        dry = submit_gaussian_calculation(gjf_path=str(self.gjf_file), job_name="bypass1", mem="4GB", nproc=4, dry_run=True)
        tok = dry["preflight"]["integrity_token"]

        res = submit_gaussian_calculation(
            gjf_path=str(self.gjf_file),
            job_name="bypass1",
            mem="4GB",
            nproc=4,
            dry_run=False,
            confirmed=True,
            integrity_token=tok,
            mock_mode=False,
        )
        self.assertFalse(res.get("ok"))
        self.assertEqual(res.get("rejected_layer"), "human_authorization")
        audit = res.get("authorization_audit", {})
        self.assertTrue(audit.get("file_integrity_verified"))
        self.assertFalse(audit.get("human_task_authorized"))

    def test_03_substituting_integrity_token_as_human_token_rejected(self):
        """Passing Agent integrity_token into human_approval_token is explicitly rejected."""
        os.environ["GAUSSIAN_ALLOW_REAL_EXECUTION"] = "true"
        dry = submit_gaussian_calculation(gjf_path=str(self.gjf_file), job_name="sub_test", dry_run=True)
        tok = dry["preflight"]["integrity_token"]

        res = submit_gaussian_calculation(
            gjf_path=str(self.gjf_file),
            job_name="sub_test",
            dry_run=False,
            confirmed=True,
            integrity_token=tok,
            human_approval_token=tok,
            mock_mode=False,
        )
        self.assertFalse(res.get("ok"))
        self.assertEqual(res.get("rejected_layer"), "human_authorization")
        self.assertIn("substituted", res.get("error", "").lower())

    def test_04_tampered_gjf_or_resource_escalation_rejected(self):
        """Any GJF modification or mem/nproc escalation invalidates preflight & human approval."""
        os.environ["GAUSSIAN_ALLOW_REAL_EXECUTION"] = "true"
        dry = submit_gaussian_calculation(
            gjf_path=str(self.gjf_file),
            job_name="tamper_test",
            mem="4GB",
            nproc=4,
            dry_run=True,
        )
        pre = dry["preflight"]
        int_tok = pre["integrity_token"]
        human = authorize_calculation_as_human(
            gjf_path=self.gjf_file,
            preflight_id=pre["preflight_id"],
            expected_sha256=pre["input_file"]["sha256"],
            job_name="tamper_test",
            mem="4GB",
            nproc=4,
            approved_by="pi_operator",
            save_receipt=False,
        )

        # Case A: Resource escalation on submission (mem="32GB")
        esc = evaluate_real_execution_authorization(
            gjf_path=self.gjf_file,
            integrity_token=int_tok,
            human_approval_token=human["human_approval_token"],
            job_name="tamper_test",
            mem="32GB",
            nproc=4,
            consume_human_token=False,
        )
        self.assertFalse(esc["ok"])
        self.assertEqual(esc["rejected_layer"], "file_integrity")

        # Case B: Escalation bypassing Layer 1 by passing wrong human approval limits directly
        esc_cpu = evaluate_real_execution_authorization(
            gjf_path=self.gjf_file,
            integrity_token=int_tok,
            human_approval_token=human["human_approval_token"],
            job_name="tamper_test",
            mem="4GB",
            nproc=16,
            consume_human_token=False,
        )
        self.assertFalse(esc_cpu["ok"])

        # Case C: File content tampered on disk after preflight
        self.gjf_file.write_text(
            self.gjf_content.replace("0.74", "0.95"),
            encoding="utf-8",
        )
        tampered = evaluate_real_execution_authorization(
            gjf_path=self.gjf_file,
            integrity_token=int_tok,
            human_approval_token=human["human_approval_token"],
            job_name="tamper_test",
            mem="4GB",
            nproc=4,
            consume_human_token=False,
        )
        self.assertFalse(tampered["ok"])
        self.assertEqual(tampered["rejected_layer"], "file_integrity")

    def test_05_mcp_path_sandbox_blocks_approval_secrets_and_grants(self):
        """validate_safe_path blocks MCP reads/writes targeting <data_dir>/approvals."""
        # Trigger key creation
        authorize_calculation_as_human(
            gjf_path=self.gjf_file,
            preflight_id="probe_key_gen",
            approved_by="sec_test",
            save_receipt=True,
        )
        key_file = self.data_dir / "approvals" / ".human_signing_key"
        grant_file = self.data_dir / "approvals" / "grants" / "probe_key_gen.json"
        self.assertTrue(key_file.exists())
        self.assertTrue(grant_file.exists())

        # Even outside read/write roots AND specifically against approvals dir
        with self.assertRaises(PermissionError):
            validate_safe_path(str(key_file), must_exist=True, mode="read")
        with self.assertRaises(PermissionError):
            validate_safe_path(str(grant_file), must_exist=True, mode="write")

        # Even if misconfigured to include data_dir, approvals/ stays blocked by explicit guard
        os.environ["GAUSSIAN_ALLOWED_READ_ROOTS"] = str(self.tmp_dir)
        os.environ["GAUSSIAN_ALLOWED_WRITE_ROOTS"] = str(self.tmp_dir)
        with self.assertRaises(PermissionError):
            validate_safe_path(str(key_file), must_exist=True, mode="read")
        with self.assertRaises(PermissionError):
            validate_safe_path(str(grant_file), must_exist=False, mode="write")

    def test_06_human_approved_task_still_stops_at_host_gate_when_disabled(self):
        """With Layer 1 + Layer 3 satisfied and host gate false, rejection must occur at host_execution_gate."""
        os.environ["GAUSSIAN_ALLOW_REAL_EXECUTION"] = "false"
        dry = submit_gaussian_calculation(
            gjf_path=str(self.gjf_file),
            job_name="host_gate_test",
            mem="4GB",
            nproc=4,
            dry_run=True,
        )
        pre = dry["preflight"]
        human = authorize_calculation_as_human(
            gjf_path=self.gjf_file,
            preflight_id=pre["preflight_id"],
            expected_sha256=pre["input_file"]["sha256"],
            job_name="host_gate_test",
            mem="4GB",
            nproc=4,
            approved_by="alice_pi",
            save_receipt=False,
        )
        res = submit_gaussian_calculation(
            gjf_path=str(self.gjf_file),
            job_name="host_gate_test",
            mem="4GB",
            nproc=4,
            dry_run=False,
            integrity_token=pre["integrity_token"],
            human_approval_token=human["human_approval_token"],
            mock_mode=False,
        )
        self.assertFalse(res.get("ok"))
        self.assertEqual(res.get("rejected_layer"), "host_execution_gate")
        self.assertIn("GAUSSIAN_ALLOW_REAL_EXECUTION", res.get("error", ""))
        audit = res.get("authorization_audit", {})
        self.assertTrue(audit.get("file_integrity_verified"))
        self.assertTrue(audit.get("human_task_authorized"))
        self.assertFalse(audit.get("host_execution_permitted"))
        self.assertEqual(audit.get("approved_by"), "alice_pi")

    def test_07_single_use_replay_blocked_and_all_layers_pass_without_spawning_g16(self):
        """All 3 layers pass once, then single-use nonce blocks replay (g16.exe never invoked)."""
        os.environ["GAUSSIAN_ALLOW_REAL_EXECUTION"] = "true"
        dry = submit_gaussian_calculation(
            gjf_path=str(self.gjf_file),
            job_name="replay_test",
            mem="4GB",
            nproc=4,
            dry_run=True,
        )
        pre = dry["preflight"]
        human = authorize_calculation_as_human(
            gjf_path=self.gjf_file,
            preflight_id=pre["preflight_id"],
            expected_sha256=pre["input_file"]["sha256"],
            job_name="replay_test",
            mem="4GB",
            nproc=4,
            approved_by="bob_pi",
            save_receipt=False,
        )
        first = evaluate_real_execution_authorization(
            gjf_path=self.gjf_file,
            integrity_token=pre["integrity_token"],
            human_approval_token=human["human_approval_token"],
            job_name="replay_test",
            mem="4GB",
            nproc=4,
            consume_human_token=True,
        )
        self.assertTrue(first["ok"], str(first))
        self.assertTrue(first["authorization_audit"]["host_execution_permitted"])

        # Replay with the exact same human_approval_token must be blocked
        second = evaluate_real_execution_authorization(
            gjf_path=self.gjf_file,
            integrity_token=pre["integrity_token"],
            human_approval_token=human["human_approval_token"],
            job_name="replay_test",
            mem="4GB",
            nproc=4,
            consume_human_token=True,
        )
        self.assertFalse(second["ok"])
        self.assertEqual(second["rejected_layer"], "human_authorization")
        self.assertIn("replay", second.get("error", "").lower())

    def test_08_host_admin_endpoint_and_operator_cli(self):
        """Test _require_admin-guarded /v1/admin/jobs/approve and scripts/approve_gaussian_job.py CLI."""
        os.environ["GAUSSIAN_MANAGED_TOKEN"] = "super-secret-host-admin-token"
        os.environ["GAUSSIAN_ALLOW_REAL_EXECUTION"] = "true"
        dry = submit_gaussian_calculation(
            gjf_path=str(self.gjf_file),
            job_name="admin_cli_test",
            mem="4GB",
            nproc=4,
            dry_run=True,
        )
        pre = dry["preflight"]

        client = TestClient(app)
        with mock.patch.object(app_module.settings, "managed_token", "super-secret-host-admin-token"):
            # Missing/wrong admin bearer token must fail
            unauth = client.post(
                "/v1/admin/jobs/approve",
                json={
                    "gjf_path": str(self.gjf_file),
                    "preflight_id": pre["preflight_id"],
                    "expected_sha256": pre["input_file"]["sha256"],
                    "job_name": "admin_cli_test",
                    "mem": "4GB",
                    "nproc": 4,
                },
            )
            self.assertIn(unauth.status_code, (401, 403))

            # Valid admin bearer token succeeds and issues host receipt + token
            auth_resp = client.post(
                "/v1/admin/jobs/approve",
                headers={"Authorization": "Bearer super-secret-host-admin-token"},
                json={
                    "gjf_path": str(self.gjf_file),
                    "preflight_id": pre["preflight_id"],
                    "expected_sha256": pre["input_file"]["sha256"],
                    "job_name": "admin_cli_test",
                    "mem": "4GB",
                    "nproc": 4,
                    "approved_by": "host_admin_ui",
                },
            )
            self.assertEqual(auth_resp.status_code, 200, auth_resp.text)
            body = auth_resp.json()
            self.assertTrue(body.get("ok"))
            self.assertTrue(body.get("human_approval_token"))

        # Verify grant receipt consumption via preflight_id works cleanly without passing token explicitly
        eval_res = evaluate_real_execution_authorization(
            gjf_path=self.gjf_file,
            integrity_token=pre["integrity_token"],
            human_approval_token=None,
            job_name="admin_cli_test",
            mem="4GB",
            nproc=4,
            preflight_id=pre["preflight_id"],
            consume_human_token=True,
        )
        self.assertTrue(eval_res["ok"], str(eval_res))

        # Now test standalone operator CLI script
        dry2 = submit_gaussian_calculation(
            gjf_path=str(self.gjf_file),
            job_name="cli_test_job",
            mem="4GB",
            nproc=4,
            dry_run=True,
        )
        pre2 = dry2["preflight"]
        env = os.environ.copy()
        cli_proc = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "approve_gaussian_job.py"),
                str(self.gjf_file),
                "--preflight-id",
                pre2["preflight_id"],
                "--expected-sha256",
                pre2["input_file"]["sha256"],
                "--job-name",
                "cli_test_job",
                "--mem",
                "4GB",
                "--nproc",
                "4",
                "--approve-by",
                "cli_operator",
                "--yes",
                "--json",
            ],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(cli_proc.returncode, 0, f"stderr={cli_proc.stderr}\nstdout={cli_proc.stdout}")
        cli_json = json.loads(cli_proc.stdout)
        self.assertTrue(cli_json.get("ok"))
        eval_cli = evaluate_real_execution_authorization(
            gjf_path=self.gjf_file,
            integrity_token=pre2["integrity_token"],
            human_approval_token=cli_json["human_approval_token"],
            job_name="cli_test_job",
            mem="4GB",
            nproc=4,
            consume_human_token=True,
        )
        self.assertTrue(eval_cli["ok"], str(eval_cli))


if __name__ == "__main__":
    unittest.main(verbosity=2)
