"""Phase 4 Security & Stability Red-Team Regression Suite.

Covers adversarial inputs fixed & verified in Phase 4:
1. Windows NTFS Junction escape detection (`mklink /J` inside allowed work_dir targeting outside root).
2. Windows Alternate Data Streams (`foo.log:hidden`), UNC paths (`\\\\server\\share`), & DOS device names (`NUL.gjf`).
3. Gaussian input generation Link0/Route CRLF injection (`mem`, `chk`, `method`, `title`) & `%chk=../` traversal.
4. HTTP `/v1/gaussian-outputs/parse` & `/v1/structure/extract` protection against approvals key exfiltration (403) & log OOM (>max_log_size_mb -> 413).
5. Artifact GC symlink/junction safety (must never follow symlinks to delete outside `data_dir`).
6. Oversized SMILES DoS guard BEFORE RDKit conformer generation.
7. Process kill safety (`kill_process_tree(0)` / `(-1)` must no-op cleanly without group signals).
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from backend import artifact_gc
from backend.app import app
from backend.config import settings
from backend.gaussian_input import GaussianInputRequest, generate_gjf, validate_gjf
from backend.process_utils import kill_process_tree, pid_alive
from backend.security import validate_safe_path
from backend.smiles.models import Smiles3DRequest
from backend.smiles.rdkit_builder import smiles_to_3d


class TestSecurityPhase4(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.work_dir = self.root / "work"
        self.outside_dir = self.root / "outside_secret"
        self.data_dir = self.root / "data"
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.outside_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self._orig_work = settings.work_dir
        self._orig_data = settings.data_dir
        self._orig_env_w = os.environ.get("GAUSSIAN_ALLOWED_WRITE_ROOTS")
        self._orig_env_r = os.environ.get("GAUSSIAN_ALLOWED_READ_ROOTS")
        self._orig_env_d = os.environ.get("GAUSSIAN_DATA_DIR")

        settings.work_dir = self.work_dir
        settings.data_dir = self.data_dir
        os.environ["GAUSSIAN_ALLOWED_WRITE_ROOTS"] = str(self.work_dir)
        os.environ["GAUSSIAN_ALLOWED_READ_ROOTS"] = str(self.work_dir)
        os.environ["GAUSSIAN_DATA_DIR"] = str(self.data_dir)

    def tearDown(self):
        settings.work_dir = self._orig_work
        settings.data_dir = self._orig_data
        for k, v in (
            ("GAUSSIAN_ALLOWED_WRITE_ROOTS", self._orig_env_w),
            ("GAUSSIAN_ALLOWED_READ_ROOTS", self._orig_env_r),
            ("GAUSSIAN_DATA_DIR", self._orig_env_d),
        ):
            if v is not None:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)
        self._tmp.cleanup()

    def test_01_windows_ntfs_junction_escape_blocked(self):
        """Real Windows directory Junction inside work_dir pointing outside must be blocked."""
        if os.name != "nt":
            self.skipTest("Windows NTFS junction test requires Windows host")

        secret_file = self.outside_dir / "secret.log"
        secret_file.write_text("SECRET_TOKEN=12345", encoding="utf-8")
        junction_path = self.work_dir / "escape_junction"

        proc = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(junction_path), str(self.outside_dir)],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.skipTest(f"mklink /J unavailable: {proc.stderr or proc.stdout}")

        try:
            with self.assertRaises(PermissionError):
                validate_safe_path(junction_path / "secret.log", mode="read")
            with self.assertRaises(PermissionError):
                validate_safe_path(junction_path / "evil.gjf", mode="write")
        finally:
            subprocess.run(["cmd", "/c", "rmdir", str(junction_path)], capture_output=True)

    def test_02_windows_ads_unc_and_reserved_device_blocked(self):
        """Block NTFS Alternate Data Streams (:), UNC SMB paths (\\\\...), and DOS device names."""
        with self.assertRaises(ValueError):
            validate_safe_path(str(self.work_dir / "h2.gjf:hidden"), mode="write")
        with self.assertRaises(PermissionError):
            validate_safe_path(r"\\127.0.0.1\c$\secret.log", mode="read")
        if os.name == "nt":
            with self.assertRaises(ValueError):
                validate_safe_path(str(self.work_dir / "NUL.gjf"), mode="write")
            with self.assertRaises(ValueError):
                validate_safe_path(str(self.work_dir / "COM1"), mode="read")

    def test_03_gaussian_input_link0_crlf_and_chk_traversal_blocked(self):
        """Reject newline/Link0 injection in mem/chk/method/keywords and ../ escape in chk."""
        base_atoms = [("H", 0.0, 0.0, 0.0), ("H", 0.0, 0.0, 0.74)]

        with self.assertRaises(ValueError):
            generate_gjf(GaussianInputRequest(job_name="inj1", mem="2GB\n%kjob l1", atoms=base_atoms))

        with self.assertRaises(ValueError):
            generate_gjf(GaussianInputRequest(job_name="inj2", chk="../../escape.chk", atoms=base_atoms))

        with self.assertRaises(ValueError):
            generate_gjf(GaussianInputRequest(job_name="inj3", method="B3LYP\n#p hf", atoms=base_atoms))

        with self.assertRaises(ValueError):
            generate_gjf(GaussianInputRequest(job_name="inj4", nproc=0, atoms=base_atoms))

        # Newlines in title should be flattened harmlessly rather than injecting Link0/coordinates
        safe_title = generate_gjf(GaussianInputRequest(job_name="t", title="line1\n%kjob l1\n0 1", atoms=base_atoms))
        self.assertEqual(safe_title["content"].count("%kjob"), 1)
        self.assertNotIn("\n%kjob", safe_title["content"])

        # validate_gjf must also reject raw %chk=../../escape.chk
        with self.assertRaises(ValueError):
            validate_gjf("%chk=../../evil.chk\n# HF/STO-3G\n\nt\n\n0 1\nH 0 0 0\n\n")

    def test_04_http_parse_approvals_blocked_and_oom_size_guard(self):
        """HTTP /v1/gaussian-outputs/parse must block approvals dir (403) and huge logs (413)."""
        approvals = self.data_dir / "approvals"
        approvals.mkdir(parents=True, exist_ok=True)
        key_file = approvals / ".human_signing_key"
        key_file.write_text("top-secret-hmac-key", encoding="utf-8")

        client = TestClient(app)

        res_key = client.post("/v1/gaussian-outputs/parse", json={"file_path": str(key_file)})
        self.assertEqual(res_key.status_code, 403)

        res_ext = client.post("/v1/structure/extract", json={"file_path": str(key_file)})
        self.assertEqual(res_ext.status_code, 403)

        # Oversized log protection (413 without reading huge payload into RAM)
        fake_big = self.work_dir / "huge.log"
        fake_big.write_text("small", encoding="utf-8")
        mock_stat = MagicMock()
        mock_stat.st_size = 150 * 1024 * 1024  # Exceeds 100 MB default limit
        with patch("pathlib.Path.stat", return_value=mock_stat):
            res_oom = client.post("/v1/gaussian-outputs/parse", json={"file_path": str(fake_big)})
        self.assertEqual(res_oom.status_code, 413)

    def test_05_artifact_gc_never_touches_work_dir_or_symlinks(self):
        """Artifact GC must protect chk/fchk/gjf/json and ignore outside symlinks/work_dir."""
        jobs_dir = self.data_dir / "jobs" / "j1"
        jobs_dir.mkdir(parents=True, exist_ok=True)
        old_log = jobs_dir / "old.log"
        old_chk = jobs_dir / "keep.chk"
        old_gjf = jobs_dir / "keep.gjf"
        work_log = self.work_dir / "research.log"
        for p in (old_log, old_chk, old_gjf, work_log):
            p.write_text("dummy", encoding="utf-8")
            old_ts = time.time() - (60 * 86400)
            os.utime(p, (old_ts, old_ts))

        outside_log = self.outside_dir / "outside_important.log"
        outside_log.write_text("keep me", encoding="utf-8")
        old_ts = time.time() - (60 * 86400)
        os.utime(outside_log, (old_ts, old_ts))
        link_path = jobs_dir / "sym_escape.log"
        try:
            link_path.symlink_to(outside_log)
        except OSError:
            pass  # Unprivileged Windows may forbid symlinks; containment still tested

        res = artifact_gc.sweep(dry_run=False)
        self.assertGreaterEqual(res["deleted"], 1)
        self.assertFalse(old_log.exists())
        self.assertTrue(old_chk.exists())
        self.assertTrue(old_gjf.exists())
        self.assertTrue(work_log.exists())
        self.assertTrue(outside_log.exists())

    def test_06_oversized_smiles_dos_guard(self):
        """Extremely long SMILES strings must be rejected before RDKit parsing."""
        huge_smiles = "C" * 2500
        with self.assertRaises(ValueError):
            smiles_to_3d(Smiles3DRequest(smiles=huge_smiles))

    def test_07_process_kill_rejects_nonpositive_pids(self):
        """kill_process_tree and pid_alive must safely ignore <=0 PIDs (no group signal -1/0)."""
        kill_process_tree(0)
        kill_process_tree(-1)
        self.assertFalse(pid_alive(0))
        self.assertFalse(pid_alive(-1))


if __name__ == "__main__":
    unittest.main()
