"""Unit tests for backend.security path validation, boundary guard and Read/Write permission separation."""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import unittest

from backend.security import (
    get_allowed_read_roots,
    get_allowed_write_roots,
    validate_safe_path,
)
from backend.config import settings


class TestSecurity(unittest.TestCase):
    def test_allowed_roots_contains_work_dir(self):
        write_roots = get_allowed_write_roots()
        read_roots = get_allowed_read_roots()
        self.assertIn(settings.work_dir.resolve(), write_roots)
        self.assertIn(settings.work_dir.resolve(), read_roots)

    def test_write_mode_rejects_project_source_directory(self):
        """Crucial security test: write mode MUST block writing to project source code / repo root."""
        project_root = Path(__file__).resolve().parent.parent
        with self.assertRaises(PermissionError) as ctx:
            validate_safe_path(project_root / "package.json", mode="write")
        self.assertIn("Security Boundary Violation (WRITE mode)", str(ctx.exception))

    def test_safe_relative_path_write(self):
        safe = validate_safe_path("benzene_opt.gjf", mode="write")
        self.assertEqual(safe, (settings.work_dir / "benzene_opt.gjf").resolve())

    def test_safe_relative_path_read(self):
        safe = validate_safe_path("benzene_opt.log", mode="read")
        self.assertEqual(safe, (settings.work_dir / "benzene_opt.log").resolve())

    def test_directory_escape_attempt_write(self):
        with self.assertRaises(PermissionError) as ctx:
            validate_safe_path("../../../../../Windows/System32/calc.exe", mode="write")
        self.assertIn("Security Boundary Violation", str(ctx.exception))

    def test_absolute_unauthorized_path_read(self):
        with self.assertRaises(PermissionError) as ctx:
            validate_safe_path("C:\\Windows\\win.ini", mode="read")
        self.assertIn("Security Boundary Violation", str(ctx.exception))

    def test_null_byte_rejection(self):
        with self.assertRaises(ValueError):
            validate_safe_path("test.gjf\0evil.exe", mode="write")

    def test_must_exist_flag(self):
        with self.assertRaises(FileNotFoundError):
            validate_safe_path("non_existent_chemical_file_987654321.log", must_exist=True, mode="read")

    def test_write_mode_rejects_c_drive_system_and_config(self):
        """Verify write mode strictly rejects writing to C: drive config / user directories."""
        c_config = Path.home() / ".gaussian-dsh" / "unauthorized.gjf"
        with self.assertRaises(PermissionError):
            validate_safe_path(c_config, mode="write")

    def test_parse_gaussian_output_large_file_limit(self):
        """Verify parse_gaussian_output enforces the 100MB safety threshold."""
        from unittest.mock import MagicMock, patch
        from backend.mcp_server import parse_gaussian_output

        fake_large_path = settings.work_dir / "huge_150mb_calc.log"
        mock_stat = MagicMock()
        mock_stat.st_size = 150 * 1024 * 1024  # 150MB

        with patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.stat", return_value=mock_stat):
            with self.assertRaises(ValueError) as ctx:
                parse_gaussian_output(file_path=str(fake_large_path))
            self.assertIn("exceeds safe parsing limit (100MB)", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
