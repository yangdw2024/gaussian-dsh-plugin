"""V5.2 True Cross-Process Tests: Compiled gaussian-backend.exe + Independent mcp_server.py.

Proves end-to-end runtime parity across two genuinely separate OS processes:
  Process A: Compiled PyInstaller runtime (`runtimes/win32-x64/gaussian-backend/gaussian-backend.exe`)
  Process B: Independent MCP Server over stdio (`mcp_server.py`)

Both processes operate against isolated temporary directories and high loopback ports,
never modifying the developer's live DSH installation or `~/.gaussian-dsh` directory,
and NEVER spawning real `g16.exe` (`GAUSSIAN_ALLOW_REAL_EXECUTION=false`).
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

import psutil

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPILED_EXE = REPO_ROOT / "runtimes" / "win32-x64" / "gaussian-backend" / "gaussian-backend.exe"

H2_GJF = (
    "%mem=2GB\n"
    "%nprocshared=2\n"
    "#p B3LYP/6-31G(d) sp\n\n"
    "H2 compiled runtime cross-process test\n\n"
    "0 1\n"
    "H  0.0  0.0  0.0\n"
    "H  0.0  0.0  0.74\n\n"
)


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _http_json(
    method: str,
    url: str,
    body: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 10.0,
) -> tuple[int, Dict[str, Any]]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = {"raw": raw}
        return exc.code, parsed


class _McpStdioClient:
    """Minimal JSON-RPC 2.0 MCP client over stdio for `mcp_server.py`."""

    def __init__(self, env: Dict[str, str]) -> None:
        self.proc = subprocess.Popen(
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
        self._req_id = 0
        self._io_lock = threading.Lock()
        self._initialize()

    def _rpc(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        with self._io_lock:
            self._req_id += 1
            msg: Dict[str, Any] = {"jsonrpc": "2.0", "id": self._req_id, "method": method}
            if params is not None:
                msg["params"] = params
            assert self.proc.stdin is not None and self.proc.stdout is not None
            self.proc.stdin.write(json.dumps(msg) + "\n")
            self.proc.stdin.flush()
            line = self.proc.stdout.readline()
            if not line:
                err = self.proc.stderr.read() if self.proc.stderr else ""
                raise RuntimeError(f"MCP stdio closed early: {err}")
            return json.loads(line)

    def _notify(self, method: str, params: Optional[Dict[str, Any]] = None) -> None:
        with self._io_lock:
            msg: Dict[str, Any] = {"jsonrpc": "2.0", "method": method}
            if params is not None:
                msg["params"] = params
            assert self.proc.stdin is not None
            self.proc.stdin.write(json.dumps(msg) + "\n")
            self.proc.stdin.flush()

    def _initialize(self) -> None:
        resp = self._rpc(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "v52-xproc-test", "version": "1.0.0"},
            },
        )
        if "result" not in resp:
            raise RuntimeError(f"MCP initialize failed: {resp}")
        self._notify("notifications/initialized", {})

    def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        resp = self._rpc("tools/call", {"name": name, "arguments": arguments or {}})
        if "error" in resp:
            raise RuntimeError(f"MCP tools/call {name} error: {resp['error']}")
        content = resp["result"]["content"]
        return json.loads(content[0]["text"])

    def close(self) -> None:
        try:
            if self.proc.poll() is None:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
        finally:
            for stream in (self.proc.stdin, self.proc.stdout, self.proc.stderr):
                if stream:
                    try:
                        stream.close()
                    except Exception:
                        pass


def _kill_pid_tree(pid: Optional[int]) -> None:
    if not pid or pid <= 0:
        return
    try:
        if not psutil.pid_exists(pid):
            return
        proc = psutil.Process(pid)
        for ch in proc.children(recursive=True):
            try:
                ch.kill()
            except Exception:
                pass
        proc.kill()
    except Exception:
        pass


@unittest.skipUnless(COMPILED_EXE.exists(), f"Compiled backend exe not found: {COMPILED_EXE}")
class TestCompiledBackendCrossProcess(unittest.TestCase):
    """Cross-process integration tests pairing compiled gaussian-backend.exe and mcp_server.py."""

    def setUp(self) -> None:
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="gaussian_v52_xproc_"))
        self.data_dir = self.tmp_dir / "data"
        self.work_dir = self.tmp_dir / "work"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.gjf_file = self.work_dir / "h2_v52.gjf"
        self.gjf_file.write_text(H2_GJF, encoding="utf-8")
        self.token = "v52_xproc_managed_token"
        self._procs: List[subprocess.Popen] = []
        self._pids: List[int] = []
        self._mcp_clients: List[_McpStdioClient] = []

    def tearDown(self) -> None:
        for client in self._mcp_clients:
            client.close()
        for p in self._procs:
            try:
                if p.poll() is None:
                    _kill_pid_tree(p.pid)
                    p.wait(timeout=3)
            except Exception:
                pass
            for stream in (p.stdout, p.stderr):
                if stream:
                    try:
                        stream.close()
                    except Exception:
                        pass
        for pid in self._pids:
            _kill_pid_tree(pid)
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _base_env(
        self,
        *,
        data_dir: Optional[Path] = None,
        work_dir: Optional[Path] = None,
        role: str,
        port: Optional[int] = None,
    ) -> Dict[str, str]:
        env = os.environ.copy()
        dd = data_dir or self.data_dir
        wd = work_dir or self.work_dir
        env["GAUSSIAN_DATA_DIR"] = str(dd)
        env["GAUSSIAN_WORK_DIR"] = str(wd)
        env["GAUSSIAN_ALLOWED_READ_ROOTS"] = str(wd)
        env["GAUSSIAN_ALLOWED_WRITE_ROOTS"] = str(wd)
        env["GAUSSIAN_ALLOW_REAL_EXECUTION"] = "false"
        env["GAUSSIAN_CLIENT_ROLE"] = role
        env["GC_ON_STARTUP"] = "0"
        if port is not None:
            env["GAUSSIAN_BACKEND_HOST"] = "127.0.0.1"
            env["GAUSSIAN_BACKEND_PORT"] = str(port)
            env["GAUSSIAN_MANAGED_TOKEN"] = self.token
        return env

    def _start_compiled_backend(
        self,
        *,
        data_dir: Optional[Path] = None,
        work_dir: Optional[Path] = None,
    ) -> tuple[subprocess.Popen, str]:
        port = _find_free_port()
        env = self._base_env(data_dir=data_dir, work_dir=work_dir, role="dsh_compiled_exe", port=port)
        proc = subprocess.Popen(
            [str(COMPILED_EXE)],
            cwd=str(self.data_dir),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self._procs.append(proc)
        self._pids.append(proc.pid)
        base_url = f"http://127.0.0.1:{port}"
        deadline = time.time() + 25.0
        last_err = None
        while time.time() < deadline:
            if proc.poll() is not None:
                out = proc.stdout.read() if proc.stdout else ""
                err = proc.stderr.read() if proc.stderr else ""
                self.fail(f"Compiled exe exited early ({proc.returncode}): stdout={out}\nstderr={err}")
            try:
                status, body = _http_json("GET", f"{base_url}/v1/health", timeout=2.0)
                if status == 200 and body.get("ok") is True and body.get("service") == "gaussian-dsh-backend":
                    return proc, base_url
            except Exception as exc:
                last_err = exc
            time.sleep(0.25)
        self.fail(f"Compiled exe failed health readiness within 25s: {last_err}")

    def _start_mcp(
        self,
        *,
        data_dir: Optional[Path] = None,
        work_dir: Optional[Path] = None,
    ) -> _McpStdioClient:
        env = self._base_env(data_dir=data_dir, work_dir=work_dir, role="mcp_stdio_server")
        client = _McpStdioClient(env)
        self._mcp_clients.append(client)
        return client

    def _wait_job_done(self, base_url: str, job_id: str, timeout: float = 12.0) -> Dict[str, Any]:
        deadline = time.time() + timeout
        while time.time() < deadline:
            _, data = _http_json("GET", f"{base_url}/v1/jobs/{job_id}")
            if data.get("status") in {"completed", "failed", "stopped"}:
                return data
            time.sleep(0.15)
        self.fail(f"Job {job_id} did not finish within {timeout}s")

    def test_01_compiled_exe_mock_job_shares_lease_with_mcp_stdio(self) -> None:
        """Compiled exe mock submission creates shared lease/files visible to independent mcp_server.py."""
        _, base_url = self._start_compiled_backend()
        mcp = self._start_mcp()

        # Submit mock job via compiled DSH HTTP endpoint
        code, sub = _http_json(
            "POST",
            f"{base_url}/v1/jobs",
            {
                "job_name": "compiled_h2_mock",
                "gjf_content": H2_GJF,
                "mock_mode": True,
                "mock_duration": 2.5,
            },
        )
        self.assertEqual(code, 200)
        self.assertTrue(sub.get("ok"), sub)
        job = sub["job"]
        job_id = job["job_id"]
        worker_pid = job["pid"]
        self._pids.append(worker_pid)
        self.assertTrue(job.get("is_simulated"))
        self.assertEqual(job.get("execution_mode"), "mock_simulation")

        # Verify shared lease files exist on disk in GAUSSIAN_DATA_DIR
        lease_file = self.data_dir / "compute_lease.json"
        lock_file = self.data_dir / "compute_lease.lock"
        self.assertTrue(lock_file.exists())
        self.assertTrue(lease_file.exists())
        lease_meta = json.loads(lease_file.read_text(encoding="utf-8"))
        self.assertEqual(lease_meta.get("owner_id"), job_id)
        self.assertEqual(lease_meta.get("kind"), "gaussian")

        # MCP Process B inspects status and attempts concurrent mock submit -> MUST see busy lease & reject
        mcp_status = mcp.call_tool("gaussian_status")
        self.assertTrue(mcp_status["active_compute_lease"]["held"])
        self.assertEqual(mcp_status["active_compute_lease"]["owner_id"], job_id)
        mcp_job = mcp.call_tool("get_gaussian_job_status", {"job_id": job_id})
        self.assertEqual(mcp_job.get("status"), "running")
        self.assertTrue(mcp_job.get("is_simulated"))

        mcp_busy = mcp.call_tool(
            "submit_gaussian_calculation",
            {
                "gjf_path": str(self.gjf_file),
                "job_name": "mcp_intruder",
                "dry_run": False,
                "mock_mode": True,
                "mock_duration": 0.4,
            },
        )
        self.assertFalse(mcp_busy.get("ok"))
        self.assertTrue(
            "运行" in mcp_busy.get("error", "")
            or "占用" in mcp_busy.get("error", "")
            or "Preflight" in mcp_busy.get("error", "")
        )

        # Wait for compiled mock worker to finish -> lease released automatically
        done = self._wait_job_done(base_url, job_id, timeout=12.0)
        self.assertEqual(done.get("status"), "completed")
        self.assertTrue(done.get("is_simulated"))
        self.assertIn("[MOCK_GAUSSIAN_SIMULATION]", done.get("log_tail", ""))

        # Poll MCP status again -> lease cleared and MCP can now submit cleanly
        mcp_after = mcp.call_tool("gaussian_status")
        self.assertFalse(mcp_after["active_compute_lease"]["held"])
        self.assertIsNone(mcp_after["active_compute_lease"]["owner_id"])
        mcp_next = mcp.call_tool(
            "submit_gaussian_calculation",
            {
                "gjf_path": str(self.gjf_file),
                "job_name": "mcp_followup",
                "dry_run": False,
                "mock_mode": True,
                "mock_duration": 0.3,
            },
        )
        self.assertTrue(mcp_next.get("ok"), mcp_next)
        if mcp_next.get("pid"):
            self._pids.append(mcp_next["pid"])
        self._wait_job_done(base_url, mcp_next["job_id"], timeout=10.0)

    def test_02_simultaneous_burst_compiled_exe_vs_mcp_stdio(self) -> None:
        """Concurrent burst from compiled DSH /v1/jobs and MCP stdio lets strictly 1 job pass."""
        _, base_url = self._start_compiled_backend()
        mcp = self._start_mcp()

        barrier = threading.Barrier(2)
        results: Dict[str, Dict[str, Any]] = {}

        def hit_compiled() -> None:
            barrier.wait(timeout=10.0)
            _, body = _http_json(
                "POST",
                f"{base_url}/v1/jobs",
                {
                    "job_name": "burst_compiled",
                    "gjf_content": H2_GJF,
                    "mock_mode": True,
                    "mock_duration": 1.2,
                },
            )
            results["compiled"] = body

        def hit_mcp() -> None:
            barrier.wait(timeout=10.0)
            results["mcp"] = mcp.call_tool(
                "submit_gaussian_calculation",
                {
                    "gjf_path": str(self.gjf_file),
                    "job_name": "burst_mcp",
                    "dry_run": False,
                    "mock_mode": True,
                    "mock_duration": 1.2,
                },
            )

        t1 = threading.Thread(target=hit_compiled)
        t2 = threading.Thread(target=hit_mcp)
        t1.start()
        t2.start()
        t1.join(timeout=15.0)
        t2.join(timeout=15.0)

        ok_flags = [bool(results["compiled"].get("ok")), bool(results["mcp"].get("ok"))]
        self.assertEqual(ok_flags.count(True), 1, f"Expected strictly 1 winner, got: {results}")

        winner_job_id = (
            results["compiled"]["job"]["job_id"]
            if results["compiled"].get("ok")
            else results["mcp"]["job_id"]
        )
        winner_pid = (
            results["compiled"]["job"].get("pid")
            if results["compiled"].get("ok")
            else results["mcp"].get("pid")
        )
        self._pids.append(winner_pid)
        self._wait_job_done(base_url, winner_job_id, timeout=12.0)

    def test_03_compiled_shutdown_preserves_mock_child_and_lease_for_mcp(self) -> None:
        """Graceful /v1/admin/shutdown stops FastAPI exe while preserving running worker & shared lease."""
        proc, base_url = self._start_compiled_backend()
        mcp = self._start_mcp()

        _, sub = _http_json(
            "POST",
            f"{base_url}/v1/jobs",
            {
                "job_name": "hot_reload_preserve",
                "gjf_content": H2_GJF,
                "mock_mode": True,
                "mock_duration": 4.0,
            },
        )
        self.assertTrue(sub.get("ok"), sub)
        job_id = sub["job"]["job_id"]
        worker_pid = sub["job"]["pid"]
        self._pids.append(worker_pid)

        # Shutdown compiled backend via authenticated admin endpoint
        code, shut = _http_json(
            "POST",
            f"{base_url}/v1/admin/shutdown",
            headers={"Authorization": f"Bearer {self.token}"},
        )
        self.assertEqual(code, 200)
        self.assertTrue(shut.get("ok"))
        self.assertTrue(shut.get("gaussian_running_preserved"))
        self.assertFalse(shut.get("compute_lease_released"))

        # Wait for backend exe to exit, verify mock worker child & lease remain intact
        proc.wait(timeout=8)
        self.assertTrue(psutil.pid_exists(worker_pid), "Mock worker died on backend shutdown")
        self.assertTrue((self.data_dir / "compute_lease.json").exists())

        # MCP Process B still sees running status and cannot start another job yet
        status_b = mcp.call_tool("get_gaussian_job_status", {"job_id": job_id})
        self.assertEqual(status_b.get("status"), "running")
        blocked_b = mcp.call_tool(
            "submit_gaussian_calculation",
            {
                "gjf_path": str(self.gjf_file),
                "job_name": "blocked_during_preserved_worker",
                "dry_run": False,
                "mock_mode": True,
                "mock_duration": 0.3,
            },
        )
        self.assertFalse(blocked_b.get("ok"))

        # Stop preserved worker via MCP, verify lease released cleanly
        stop_b = mcp.call_tool("stop_gaussian_calculation", {"job_id": job_id})
        self.assertTrue(stop_b.get("ok"), stop_b)
        after_stop = mcp.call_tool("gaussian_status")
        self.assertFalse(after_stop["active_compute_lease"]["held"])

    def test_04_simultaneous_cancel_race_compiled_exe_and_mcp(self) -> None:
        """Simultaneous stop from compiled DSH /stop and MCP stop_gaussian_calculation leaves stopped state."""
        _, base_url = self._start_compiled_backend()
        mcp = self._start_mcp()

        _, sub = _http_json(
            "POST",
            f"{base_url}/v1/jobs",
            {
                "job_name": "cancel_race_v52",
                "gjf_content": H2_GJF,
                "mock_mode": True,
                "mock_duration": 5.0,
            },
        )
        self.assertTrue(sub.get("ok"), sub)
        job_id = sub["job"]["job_id"]
        worker_pid = sub["job"]["pid"]
        self._pids.append(worker_pid)

        barrier = threading.Barrier(2)
        out: Dict[str, Any] = {}

        def stop_dsh() -> None:
            barrier.wait(timeout=10.0)
            _, body = _http_json("POST", f"{base_url}/v1/jobs/{job_id}/stop", {})
            out["dsh"] = body

        def stop_mcp() -> None:
            barrier.wait(timeout=10.0)
            out["mcp"] = mcp.call_tool("stop_gaussian_calculation", {"job_id": job_id})

        t1 = threading.Thread(target=stop_dsh)
        t2 = threading.Thread(target=stop_mcp)
        t1.start()
        t2.start()
        t1.join(timeout=15.0)
        t2.join(timeout=15.0)

        self.assertTrue(out["dsh"].get("ok") or out["mcp"].get("ok"), out)
        time.sleep(0.25)
        self.assertFalse(psutil.pid_exists(worker_pid), "Worker PID should be terminated after stop race")

        _, final_dsh = _http_json("GET", f"{base_url}/v1/jobs/{job_id}")
        final_mcp = mcp.call_tool("get_gaussian_job_status", {"job_id": job_id})
        self.assertEqual(final_dsh.get("status"), "stopped")
        self.assertEqual(final_mcp.get("status"), "stopped")
        self.assertFalse((self.data_dir / "compute_lease.json").exists())

    def test_05_shared_data_dir_with_divergent_work_dirs_still_locks_vs_split_data_dir_risk(self) -> None:
        """Lock binds on shared GAUSSIAN_DATA_DIR even if work_dir differs; split DATA_DIR isolates locks."""
        work_a = self.tmp_dir / "work_a"
        work_b = self.tmp_dir / "work_b"
        work_a.mkdir(parents=True, exist_ok=True)
        work_b.mkdir(parents=True, exist_ok=True)
        gjf_b = work_b / "h2_b.gjf"
        gjf_b.write_text(H2_GJF, encoding="utf-8")

        _, base_url = self._start_compiled_backend(data_dir=self.data_dir, work_dir=work_a)
        mcp_shared_data = self._start_mcp(data_dir=self.data_dir, work_dir=work_b)

        _, sub = _http_json(
            "POST",
            f"{base_url}/v1/jobs",
            {
                "job_name": "shared_data_diff_work",
                "gjf_content": H2_GJF,
                "mock_mode": True,
                "mock_duration": 2.0,
            },
        )
        self.assertTrue(sub.get("ok"), sub)
        self._pids.append(sub["job"]["pid"])

        # Shared DATA_DIR -> divergent WORK_DIR STILL sees busy lease and refuses concurrent job!
        blocked = mcp_shared_data.call_tool(
            "submit_gaussian_calculation",
            {
                "gjf_path": str(gjf_b),
                "job_name": "other_work_dir_job",
                "dry_run": False,
                "mock_mode": True,
                "mock_duration": 0.3,
            },
        )
        self.assertFalse(blocked.get("ok"))

        # Split GAUSSIAN_DATA_DIR -> independent coordination roots (expected boundary condition)
        split_data = self.tmp_dir / "data_isolated"
        split_data.mkdir(parents=True, exist_ok=True)
        mcp_split = self._start_mcp(data_dir=split_data, work_dir=work_b)
        split_res = mcp_split.call_tool("gaussian_status")
        self.assertFalse(split_res["active_compute_lease"]["held"])

        self._wait_job_done(base_url, sub["job"]["job_id"], timeout=10.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
