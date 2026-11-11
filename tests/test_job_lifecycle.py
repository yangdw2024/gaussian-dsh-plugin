"""V5.0 Gaussian Job Lifecycle and Process Management Unit Tests.

Covers:
1. Dry-run preflight checks and HMAC execution token generation.
2. Rejection of unauthorized raw execution (GAUSSIAN_ALLOW_REAL_EXECUTION=false).
3. Mock process execution, PID tracking, and log output generation.
4. Real-time status polling, optimization step tracking, and log tail retrieval.
5. Mutex queue protection (preventing concurrent overlapping calculations).
6. Controlled process termination (stop_gaussian_calculation) and tree teardown.
7. SCF convergence failure simulation (fail_scf=True) and failure state recording.
8. Job listing, status filtering, and reconciliation.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

import psutil

from backend.config import settings
from backend.execution_policy import (
    authorize_calculation_as_human,
    calculate_content_sha256,
    verify_execution_token,
    verify_integrity_token,
)
from backend.job_manager import GaussianJob, job_manager
from backend.mcp_server import (
    get_gaussian_job_status,
    list_gaussian_jobs,
    stop_gaussian_calculation,
    submit_gaussian_calculation,
)
from backend.process_utils import pid_create_time


class TestJobLifecycle(unittest.TestCase):
    """Test suite for Gaussian job submission, monitoring, and lifecycle control."""

    @classmethod
    def setUpClass(cls):
        cls._saved_env = {
            k: os.environ.get(k)
            for k in (
                "GAUSSIAN_DATA_DIR",
                "GAUSSIAN_WORK_DIR",
                "GAUSSIAN_ALLOWED_WRITE_ROOTS",
                "GAUSSIAN_ALLOWED_READ_ROOTS",
                "GAUSSIAN_ALLOW_REAL_EXECUTION",
            )
        }
        cls.tmp_root = Path(tempfile.mkdtemp(prefix="gaussian_lifecycle_"))
        cls.data_dir = cls.tmp_root / "data"
        cls.test_work_dir = cls.tmp_root / "work"
        cls.data_dir.mkdir(parents=True, exist_ok=True)
        cls.test_work_dir.mkdir(parents=True, exist_ok=True)

        os.environ["GAUSSIAN_DATA_DIR"] = str(cls.data_dir.resolve())
        os.environ["GAUSSIAN_WORK_DIR"] = str(cls.test_work_dir.resolve())
        os.environ["GAUSSIAN_ALLOWED_WRITE_ROOTS"] = str(cls.test_work_dir.resolve())
        os.environ["GAUSSIAN_ALLOWED_READ_ROOTS"] = str(cls.test_work_dir.resolve())
        # Ensure real execution gate is explicitly disabled during tests
        os.environ["GAUSSIAN_ALLOW_REAL_EXECUTION"] = "false"

        # Create a valid test .gjf file
        cls.valid_gjf = cls.test_work_dir / "h2_test_lifecycle.gjf"
        cls.valid_content = (
            "%chk=h2_lifecycle.chk\n"
            "%mem=4GB\n"
            "%nprocshared=4\n"
            "#p B3LYP/6-31G(d) opt\n\n"
            "H2 optimization test for lifecycle\n\n"
            "0 1\n"
            "H  0.0  0.0  0.0\n"
            "H  0.0  0.0  0.74\n\n"
        )
        cls.valid_gjf.write_text(cls.valid_content, encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        for k, v in cls._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(cls.tmp_root, ignore_errors=True)

    def test_01_preflight_dry_run_token_generation(self):
        """Verify dry-run mode returns complete preflight report and file-integrity token."""
        res = submit_gaussian_calculation(
            gjf_path=str(self.valid_gjf),
            job_name="h2_dryrun",
            dry_run=True,
        )

        self.assertTrue(res.get("ok"))
        self.assertTrue(res.get("dry_run"))
        preflight = res.get("preflight", {})
        self.assertTrue(preflight.get("preflight_passed"))
        self.assertEqual(preflight.get("charge"), 0)
        self.assertEqual(preflight.get("multiplicity"), 1)
        self.assertEqual(preflight.get("atom_count"), 2)
        self.assertFalse(preflight["authorization_model"]["grants_human_approval"])

        auth_token = preflight.get("auth_token")
        self.assertIsNotNone(auth_token)
        sha256 = preflight["input_file"]["sha256"]
        self.assertEqual(sha256, calculate_content_sha256(self.valid_content))

        # Verify integrity token validity against SHA256
        valid, msg = verify_execution_token(auth_token, sha256)
        self.assertTrue(valid, msg)
        int_ok, int_msg, _ = verify_integrity_token(auth_token, sha256)
        self.assertTrue(int_ok, int_msg)

    def test_02_real_execution_blocked_by_host_gate(self):
        """Verify 3-layer gate blocks Agent-only bypass first and still stops at host gate."""
        dry_res = submit_gaussian_calculation(
            gjf_path=str(self.valid_gjf),
            dry_run=True,
        )
        pre = dry_res["preflight"]
        token = pre["integrity_token"]

        # Attempt 1: Agent tries confirmed=True + integrity_token without human approval
        no_human = submit_gaussian_calculation(
            gjf_path=str(self.valid_gjf),
            dry_run=False,
            confirmed=True,
            auth_token=token,
            mock_mode=False,
        )
        self.assertFalse(no_human.get("ok"))
        self.assertEqual(no_human.get("rejected_layer"), "human_authorization")

        # Attempt 2: With valid out-of-band human approval, host gate still blocks when false
        human = authorize_calculation_as_human(
            gjf_path=self.valid_gjf,
            preflight_id=pre["preflight_id"],
            expected_sha256=pre["input_file"]["sha256"],
            approved_by="lifecycle_test_pi",
            save_receipt=False,
        )
        res = submit_gaussian_calculation(
            gjf_path=str(self.valid_gjf),
            dry_run=False,
            integrity_token=token,
            human_approval_token=human["human_approval_token"],
            mock_mode=False,
        )
        self.assertFalse(res.get("ok"))
        self.assertEqual(res.get("rejected_layer"), "host_execution_gate")
        self.assertIn("GAUSSIAN_ALLOW_REAL_EXECUTION", res.get("error", ""))

    def test_03_mock_job_submission_and_lifecycle(self):
        """Submit mock calculation, poll real-time status, and verify normal completion."""
        res = submit_gaussian_calculation(
            gjf_path=str(self.valid_gjf),
            job_name="h2_mock_opt",
            dry_run=False,
            mock_mode=True,
            mock_duration=0.8,
        )

        self.assertTrue(res.get("ok"), str(res))
        self.assertTrue(res.get("mock_mode"))
        self.assertTrue(res.get("is_simulated"))
        self.assertFalse(res.get("real_gaussian_result"))
        job_id = res.get("job_id")
        pid = res.get("pid")
        self.assertIsNotNone(job_id)
        self.assertIsInstance(pid, int)

        # Immediate poll: status should be running
        status_info = get_gaussian_job_status(job_id=job_id)
        self.assertTrue(status_info.get("ok"))
        self.assertEqual(status_info.get("job_id"), job_id)
        self.assertEqual(status_info.get("status"), "running")
        self.assertTrue(status_info.get("is_simulated"))
        self.assertFalse(status_info.get("real_gaussian_result"))

        # Wait for mock worker to complete
        time.sleep(1.2)

        # Poll completed status
        comp_info = get_gaussian_job_status(job_id=job_id)
        self.assertTrue(comp_info.get("ok"))
        self.assertEqual(comp_info.get("status"), "completed")
        self.assertIsNotNone(comp_info.get("finished_at"))
        self.assertTrue(comp_info.get("is_simulated"))
        self.assertFalse(comp_info.get("real_gaussian_result"))
        self.assertIsNone(comp_info.get("last_energy"))
        self.assertIsNotNone(comp_info.get("simulated_energy"))
        self.assertTrue(comp_info.get("simulation_warning"))

        # Verify output log file exists and contains unmistakable mock simulation markers
        log_path = Path(comp_info.get("log_path"))
        self.assertTrue(log_path.exists())
        log_content = log_path.read_text(encoding="utf-8")
        self.assertIn("[MOCK_GAUSSIAN_SIMULATION]", log_content)
        self.assertIn("Normal termination of Gaussian 16", log_content)
        self.assertIn("SCF Done:  E(RB3LYP) =", log_content)

    def test_04_mutex_concurrency_protection(self):
        """Verify that submitting a second job while one is running is blocked by the mutex."""
        # Start a longer mock job
        res1 = submit_gaussian_calculation(
            gjf_path=str(self.valid_gjf),
            job_name="h2_mutex_test",
            dry_run=False,
            mock_mode=True,
            mock_duration=3.0,
        )
        self.assertTrue(res1.get("ok"))
        job_id1 = res1.get("job_id")

        try:
            # Attempt to submit second job immediately
            res2 = submit_gaussian_calculation(
                gjf_path=str(self.valid_gjf),
                job_name="h2_mutex_second",
                dry_run=False,
                mock_mode=True,
                mock_duration=1.0,
            )
            self.assertFalse(res2.get("ok"))
            err_msg = res2.get("error", "").lower()
            self.assertTrue(
                "already running" in err_msg or "busy" in err_msg,
                f"Expected concurrency error, got: {err_msg}",
            )
        finally:
            # Stop first job cleanly
            stop_res = stop_gaussian_calculation(job_id=job_id1)
            self.assertTrue(stop_res.get("ok"))

    def test_05_stop_running_calculation(self):
        """Verify explicit cancellation of a running calculation."""
        res = submit_gaussian_calculation(
            gjf_path=str(self.valid_gjf),
            job_name="h2_to_be_stopped",
            dry_run=False,
            mock_mode=True,
            mock_duration=5.0,
        )
        self.assertTrue(res.get("ok"))
        job_id = res.get("job_id")

        # Confirm running
        status_pre = get_gaussian_job_status(job_id=job_id)
        self.assertEqual(status_pre.get("status"), "running")

        # Stop calculation
        stop_res = stop_gaussian_calculation(job_id=job_id)
        self.assertTrue(stop_res.get("ok"))
        self.assertEqual(stop_res.get("status"), "stopped")

        # Verify final status
        status_post = get_gaussian_job_status(job_id=job_id)
        self.assertEqual(status_post.get("status"), "stopped")

    def test_06_mock_scf_failure_simulation(self):
        """Verify simulation of SCF non-convergence error and failure status transition."""
        res = submit_gaussian_calculation(
            gjf_path=str(self.valid_gjf),
            job_name="h2_fail_scf",
            dry_run=False,
            mock_mode=True,
            fail_scf=True,
            mock_duration=0.6,
        )
        self.assertTrue(res.get("ok"))
        job_id = res.get("job_id")

        # Wait for mock to finish failing
        time.sleep(1.0)

        info = get_gaussian_job_status(job_id=job_id)
        self.assertTrue(info.get("ok"))
        self.assertEqual(info.get("status"), "failed")

        log_path = Path(info.get("log_path"))
        self.assertTrue(log_path.exists())
        log_content = log_path.read_text(encoding="utf-8")
        self.assertIn("Convergence failure -- run terminated.", log_content)
        self.assertIn("l502.exe", log_content)

    def test_07_list_gaussian_jobs(self):
        """Verify job listing and status filtering."""
        list_all = list_gaussian_jobs(limit=50)
        self.assertTrue(list_all.get("ok"))
        self.assertGreater(list_all.get("total_jobs"), 0)
        jobs = list_all.get("jobs", [])
        self.assertIsInstance(jobs, list)

        # Test filtering by completed
        completed_list = list_gaussian_jobs(limit=50, status_filter="completed")
        self.assertTrue(completed_list.get("ok"))
        for j in completed_list.get("jobs", []):
            self.assertEqual(j.get("status"), "completed")

        # Test filtering by failed
        failed_list = list_gaussian_jobs(limit=50, status_filter="failed")
        self.assertTrue(failed_list.get("ok"))
        for j in failed_list.get("jobs", []):
            self.assertEqual(j.get("status"), "failed")

    def test_08_stop_kills_live_pid_and_blocks_duplicate_stop(self):
        """Verify stop kills OS PID, blocks repeated stop on stopped/completed/missing jobs."""
        res = submit_gaussian_calculation(
            gjf_path=str(self.valid_gjf),
            job_name="h2_stop_dup_test",
            dry_run=False,
            mock_mode=True,
            mock_duration=10.0,
        )
        self.assertTrue(res.get("ok"), str(res))
        job_id = res["job_id"]
        pid = int(res["pid"])
        self.assertTrue(psutil.pid_exists(pid))

        stop_first = stop_gaussian_calculation(job_id=job_id)
        self.assertTrue(stop_first.get("ok"), str(stop_first))
        self.assertEqual(stop_first.get("status"), "stopped")
        self.assertFalse(psutil.pid_exists(pid))

        # Duplicate stop on already stopped job must fail gracefully
        stop_second = stop_gaussian_calculation(job_id=job_id)
        self.assertFalse(stop_second.get("ok"))
        self.assertEqual(stop_second.get("status"), "stopped")

        # Stop on completed job must fail gracefully
        quick = submit_gaussian_calculation(
            gjf_path=str(self.valid_gjf),
            job_name="h2_quick_done",
            dry_run=False,
            mock_mode=True,
            mock_duration=0.2,
        )
        self.assertTrue(quick.get("ok"), str(quick))
        quick_id = quick["job_id"]
        time.sleep(0.8)
        quick_status = get_gaussian_job_status(job_id=quick_id)
        self.assertEqual(quick_status.get("status"), "completed")

        stop_completed = stop_gaussian_calculation(job_id=quick_id)
        self.assertFalse(stop_completed.get("ok"))
        self.assertEqual(stop_completed.get("status"), "completed")

        # Stop on unknown job_id must return ok=False without crashing
        stop_missing = stop_gaussian_calculation(job_id="nonexistent_job_999999")
        self.assertFalse(stop_missing.get("ok"))

    def test_09_stop_pid_reuse_protection(self):
        """Verify stop_gaussian_calculation refuses to kill an unrelated OS PID with mismatched start time."""
        benign = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            real_start = pid_create_time(benign.pid)
            self.assertIsNotNone(real_start)
            reused_job_id = "pid_reuse_guard_test"
            fake_job = GaussianJob(
                job_id=reused_job_id,
                job_name="pid_reuse_guard",
                status="running",
                gjf_path=str(self.valid_gjf),
                log_path=str(self.test_work_dir / "pid_reuse.log"),
                chk_path=str(self.test_work_dir / "pid_reuse.chk"),
                pid=benign.pid,
                pid_start_time=real_start - 3600.0,  # backdated 1 hour -> simulates reused PID
                started_at=time.time() - 3600.0,
                is_simulated=True,
                execution_mode="mock_simulation",
            )
            job_manager._save(fake_job)

            stop_res = stop_gaussian_calculation(job_id=reused_job_id)
            self.assertFalse(stop_res.get("ok"))
            self.assertIn("复用", stop_res.get("error", ""))
            # Unrelated process MUST remain alive!
            self.assertIsNone(benign.poll())
            self.assertTrue(psutil.pid_exists(benign.pid))
        finally:
            benign.terminate()
            benign.wait(timeout=5)
            fake_path = job_manager.jobs_dir / "pid_reuse_guard_test.json"
            fake_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
