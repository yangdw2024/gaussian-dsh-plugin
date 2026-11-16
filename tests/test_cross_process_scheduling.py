"""V5.1 Cross-process resource scheduling & concurrency tests.

Verifies that DSH Backend and MCP Server running in separate OS processes share
the kernel-locked ChemComputeScheduler lease state (`compute_lease.lock` +
`compute_lease.json`) and cannot bypass the global single-heavy-job limit.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

import psutil

REPO_ROOT = Path(__file__).resolve().parent.parent


def _python_env(data_dir: Path, work_dir: Path, role: str) -> dict[str, str]:
    env = os.environ.copy()
    env["GAUSSIAN_DATA_DIR"] = str(data_dir)
    env["GAUSSIAN_WORK_DIR"] = str(work_dir)
    env["GAUSSIAN_ALLOWED_READ_ROOTS"] = str(work_dir)
    env["GAUSSIAN_ALLOWED_WRITE_ROOTS"] = str(work_dir)
    env["GAUSSIAN_ALLOW_REAL_EXECUTION"] = "false"
    env["GAUSSIAN_CLIENT_ROLE"] = role
    pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{REPO_ROOT}{os.pathsep}{pp}" if pp else str(REPO_ROOT)
    return env


class TestCrossProcessScheduling(unittest.TestCase):
    """Subprocess-level dual-client concurrency tests."""

    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="gaussian_xproc_"))
        self.data_dir = self.tmp_dir / "data"
        self.work_dir = self.tmp_dir / "work"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.gjf_file = self.work_dir / "h2_xproc.gjf"
        self.gjf_content = (
            "%mem=2GB\n"
            "%nprocshared=2\n"
            "#p B3LYP/6-31G(d) sp\n\n"
            "H2 cross-process test\n\n"
            "0 1\n"
            "H  0.0  0.0  0.0\n"
            "H  0.0  0.0  0.74\n\n"
        )
        self.gjf_file.write_text(self.gjf_content, encoding="utf-8")
        self._pids_to_cleanup: list[int] = []

    def tearDown(self):
        for pid in self._pids_to_cleanup:
            try:
                if pid and psutil.pid_exists(pid):
                    p = psutil.Process(pid)
                    for child in p.children(recursive=True):
                        child.kill()
                    p.kill()
            except Exception:
                pass
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _run_py(self, code: str, role: str, timeout: float = 20.0) -> dict:
        proc = subprocess.run(
            [sys.executable, "-c", textwrap.dedent(code)],
            cwd=str(REPO_ROOT),
            env=_python_env(self.data_dir, self.work_dir, role),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        self.assertEqual(
            proc.returncode,
            0,
            f"Subprocess failed ({role}): stdout={proc.stdout}\nstderr={proc.stderr}",
        )
        last_line = [ln for ln in proc.stdout.splitlines() if ln.strip()][-1]
        return json.loads(last_line)

    def test_01_scheduler_mutual_exclusion_across_processes(self):
        """Process A holding rdkit lease blocks Process B acquiring gaussian lease or submitting."""
        release_flag = self.tmp_dir / "release_a.flag"
        holder_code = textwrap.dedent(
            f"""
            import json, time
            from pathlib import Path
            from backend.resource_scheduler import chem_scheduler
            chem_scheduler.acquire("dsh_rdkit_1", "rdkit")
            print(json.dumps({{"acquired": True}}), flush=True)
            flag = Path(r"{release_flag}")
            deadline = time.time() + 15.0
            while not flag.exists() and time.time() < deadline:
                time.sleep(0.05)
            chem_scheduler.release("dsh_rdkit_1")
            """
        )
        proc_a = subprocess.Popen(
            [sys.executable, "-c", holder_code],
            cwd=str(REPO_ROOT),
            env=_python_env(self.data_dir, self.work_dir, "dsh_backend"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self._pids_to_cleanup.append(proc_a.pid)
        try:
            ready_line = proc_a.stdout.readline().strip()
            self.assertEqual(json.loads(ready_line)["acquired"], True)

            probe_b = self._run_py(
                f"""
                import json
                from pathlib import Path
                from backend.resource_scheduler import chem_scheduler, ResourceBusyError
                from backend.mcp_server import submit_gaussian_calculation

                lease = chem_scheduler.current_lease()
                busy_raised = False
                try:
                    chem_scheduler.acquire("mcp_g_1", "gaussian")
                except ResourceBusyError as exc:
                    busy_raised = True
                    busy_msg = str(exc)

                sub = submit_gaussian_calculation(
                    gjf_path=r"{self.gjf_file}",
                    job_name="blocked_by_dsh",
                    dry_run=False,
                    mock_mode=True,
                    mock_duration=0.5,
                )
                print(json.dumps({{
                    "holder_pid": lease.holder_pid if lease else None,
                    "host_client": lease.host_client if lease else None,
                    "busy_raised": busy_raised,
                    "sub_ok": sub.get("ok"),
                    "sub_err": sub.get("error"),
                }}))
                """,
                role="mcp_server",
            )
            self.assertEqual(probe_b["holder_pid"], proc_a.pid)
            self.assertEqual(probe_b["host_client"], "dsh_backend")
            self.assertTrue(probe_b["busy_raised"])
            self.assertFalse(probe_b["sub_ok"])
        finally:
            release_flag.write_text("go", encoding="utf-8")
            proc_a.wait(timeout=10)
            if proc_a.stdout:
                proc_a.stdout.close()
            if proc_a.stderr:
                proc_a.stderr.close()

        # After Process A releases lease, Process B must acquire cleanly
        after_b = self._run_py(
            """
            import json
            from backend.resource_scheduler import chem_scheduler
            lease = chem_scheduler.acquire("mcp_after_release", "gaussian")
            chem_scheduler.release("mcp_after_release")
            print(json.dumps({"owner": lease.owner_id, "client": lease.host_client}))
            """,
            role="mcp_server",
        )
        self.assertEqual(after_b["owner"], "mcp_after_release")
        self.assertEqual(after_b["client"], "mcp_server")

    def test_02_concurrent_burst_submission_race(self):
        """Synchronized burst from DSH Backend and MCP Server allows strictly 1 mock job."""
        barrier_a = self.tmp_dir / "ready_a"
        barrier_b = self.tmp_dir / "ready_b"
        go_flag = self.tmp_dir / "go.flag"

        def spawn_racer(role: str, my_ready: Path) -> subprocess.Popen:
            code = textwrap.dedent(
                f"""
                import json, time
                from pathlib import Path
                from backend.job_manager import job_manager

                Path(r"{my_ready}").write_text("1", encoding="utf-8")
                go = Path(r"{go_flag}")
                deadline = time.time() + 15.0
                while not go.exists() and time.time() < deadline:
                    time.sleep(0.005)
                gjf_text = Path(r"{self.gjf_file}").read_text(encoding="utf-8")
                res = job_manager.submit(
                    job_name="race_{role}",
                    gjf_content=gjf_text,
                    mock_mode=True,
                    mock_duration=1.5,
                )
                print(json.dumps({{
                    "role": "{role}",
                    "ok": res.get("ok"),
                    "job_id": res.get("job", {{}}).get("job_id"),
                    "pid": res.get("job", {{}}).get("pid"),
                    "error": res.get("error"),
                }}), flush=True)
                """
            )
            return subprocess.Popen(
                [sys.executable, "-c", code],
                cwd=str(REPO_ROOT),
                env=_python_env(self.data_dir, self.work_dir, role),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

        p_a = spawn_racer("dsh_backend", barrier_a)
        p_b = spawn_racer("mcp_server", barrier_b)
        self._pids_to_cleanup.extend([p_a.pid, p_b.pid])

        try:
            deadline = time.time() + 10.0
            while (not barrier_a.exists() or not barrier_b.exists()) and time.time() < deadline:
                time.sleep(0.02)
            self.assertTrue(barrier_a.exists() and barrier_b.exists())
            go_flag.write_text("GO", encoding="utf-8")

            out_a, err_a = p_a.communicate(timeout=15)
            out_b, err_b = p_b.communicate(timeout=15)
            self.assertEqual(p_a.returncode, 0, err_a)
            self.assertEqual(p_b.returncode, 0, err_b)

            res_a = json.loads([ln for ln in out_a.splitlines() if ln.strip()][-1])
            res_b = json.loads([ln for ln in out_b.splitlines() if ln.strip()][-1])
            successes = [r for r in (res_a, res_b) if r["ok"]]
            failures = [r for r in (res_a, res_b) if not r["ok"]]

            self.assertEqual(len(successes), 1, f"Expected strictly 1 winner, got: {res_a} vs {res_b}")
            self.assertEqual(len(failures), 1, f"Expected strictly 1 rejected, got: {res_a} vs {res_b}")
            if successes[0].get("pid"):
                self._pids_to_cleanup.append(int(successes[0]["pid"]))

            # Clean up winning mock job from a third client call
            winner_id = successes[0]["job_id"]
            stop_res = self._run_py(
                f"""
                import json
                from backend.job_manager import job_manager
                print(json.dumps(job_manager.stop_job("{winner_id}")))
                """,
                role="mcp_server",
            )
            self.assertTrue(stop_res.get("ok"), str(stop_res))
        finally:
            go_flag.write_text("GO", encoding="utf-8")

    def test_03_cross_process_cancellation_preserves_stopped_status(self):
        """Process B stops job launched by Process A; Process A cannot overwrite stopped."""
        check_flag = self.tmp_dir / "check_after_stop.flag"
        launcher_code = textwrap.dedent(
            f"""
            import json, time
            from pathlib import Path
            from backend.job_manager import job_manager

            gjf_text = Path(r"{self.gjf_file}").read_text(encoding="utf-8")
            res = job_manager.submit(
                job_name="xproc_cancel_job",
                gjf_content=gjf_text,
                mock_mode=True,
                mock_duration=10.0,
            )
            job_id = res["job"]["job_id"]
            pid = res["job"]["pid"]
            print(json.dumps({{"job_id": job_id, "pid": pid}}), flush=True)

            flag = Path(r"{check_flag}")
            deadline = time.time() + 15.0
            while not flag.exists() and time.time() < deadline:
                time.sleep(0.05)

            has_run = job_manager.has_running()
            seen = job_manager.get_job(job_id, log_tail_lines=5)
            print(json.dumps({{
                "has_running_after_stop": has_run,
                "status_seen_by_launcher": seen.get("status") if seen else None,
            }}), flush=True)
            """
        )
        proc_a = subprocess.Popen(
            [sys.executable, "-c", launcher_code],
            cwd=str(REPO_ROOT),
            env=_python_env(self.data_dir, self.work_dir, "dsh_backend"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self._pids_to_cleanup.append(proc_a.pid)
        try:
            first_line = proc_a.stdout.readline().strip()
            submitted = json.loads(first_line)
            job_id = submitted["job_id"]
            mock_pid = int(submitted["pid"])
            self._pids_to_cleanup.append(mock_pid)
            self.assertTrue(psutil.pid_exists(mock_pid))

            stop_b = self._run_py(
                f"""
                import json
                from backend.mcp_server import stop_gaussian_calculation, get_gaussian_job_status
                from backend.resource_scheduler import chem_scheduler
                st = get_gaussian_job_status("{job_id}", log_tail_lines=5)
                stopped = stop_gaussian_calculation("{job_id}")
                lease_after = chem_scheduler.current_lease()
                print(json.dumps({{
                    "status_before": st.get("status"),
                    "stop_ok": stopped.get("ok"),
                    "stop_status": stopped.get("status"),
                    "lease_cleared": lease_after is None,
                }}))
                """,
                role="mcp_server",
            )
            self.assertEqual(stop_b["status_before"], "running")
            self.assertTrue(stop_b["stop_ok"])
            self.assertEqual(stop_b["stop_status"], "stopped")
            self.assertTrue(stop_b["lease_cleared"])
            self.assertFalse(psutil.pid_exists(mock_pid))

            check_flag.write_text("go", encoding="utf-8")
            second_line = proc_a.stdout.readline().strip()
            launcher_after = json.loads(second_line)
            self.assertFalse(launcher_after["has_running_after_stop"])
            self.assertEqual(launcher_after["status_seen_by_launcher"], "stopped")
        finally:
            check_flag.write_text("go", encoding="utf-8")
            proc_a.wait(timeout=10)
            if proc_a.stdout:
                proc_a.stdout.close()
            if proc_a.stderr:
                proc_a.stderr.close()

    def test_04_stale_lease_eviction_vs_live_gaussian_preservation(self):
        """Dead non-gaussian holder lease is auto-evicted; dead launcher with live child preserves lease."""
        # Part A: abrupt crash of rdkit holder (os._exit(1) without release)
        crash_proc = subprocess.run(
            [
                sys.executable,
                "-c",
                "import os; from backend.resource_scheduler import chem_scheduler; "
                "chem_scheduler.acquire('crashed_rdkit', 'rdkit'); os._exit(1)",
            ],
            cwd=str(REPO_ROOT),
            env=_python_env(self.data_dir, self.work_dir, "mcp_server"),
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(crash_proc.returncode, 1)

        evict_check = self._run_py(
            """
            import json
            from backend.resource_scheduler import chem_scheduler
            cur = chem_scheduler.current_lease()
            new_lease = chem_scheduler.acquire("recovered_gaussian", "gaussian")
            chem_scheduler.release("recovered_gaussian")
            print(json.dumps({"stale_evicted": cur is None, "acquired": new_lease.owner_id}))
            """,
            role="dsh_backend",
        )
        self.assertTrue(evict_check["stale_evicted"])
        self.assertEqual(evict_check["acquired"], "recovered_gaussian")

        # Part B: launcher submits mock Gaussian job and exits cleanly leaving child alive
        orphan_launch = self._run_py(
            f"""
            import json, os
            from pathlib import Path
            from backend.job_manager import job_manager
            gjf_text = Path(r"{self.gjf_file}").read_text(encoding="utf-8")
            res = job_manager.submit(job_name="preserved_child", gjf_content=gjf_text, mock_mode=True, mock_duration=5.0)
            print(json.dumps({{"job_id": res["job"]["job_id"], "pid": res["job"]["pid"]}}), flush=True)
            os._exit(0)
            """,
            role="dsh_backend",
        )
        child_pid = int(orphan_launch["pid"])
        child_job_id = orphan_launch["job_id"]
        self._pids_to_cleanup.append(child_pid)

        preserve_check = self._run_py(
            f"""
            import json
            from backend.resource_scheduler import chem_scheduler, ResourceBusyError
            from backend.job_manager import job_manager

            cur = chem_scheduler.current_lease()
            blocked = False
            try:
                chem_scheduler.acquire("rdkit_blocked", "rdkit")
            except ResourceBusyError:
                blocked = True
            stop_res = job_manager.stop_job("{child_job_id}")
            cur_after = chem_scheduler.current_lease()
            print(json.dumps({{
                "preserved_owner": cur.owner_id if cur else None,
                "blocked": blocked,
                "stop_ok": stop_res.get("ok"),
                "released_after_stop": cur_after is None,
            }}))
            """,
            role="mcp_server",
        )
        self.assertEqual(preserve_check["preserved_owner"], child_job_id)
        self.assertTrue(preserve_check["blocked"])
        self.assertTrue(preserve_check["stop_ok"])
        self.assertTrue(preserve_check["released_after_stop"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
