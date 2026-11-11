"""Security and boundary validation for Gaussian DSH / MCP Server.

Provides strict separation between READ and WRITE permissions, path traversal protection,
symbolic link / junction resolution, and workspace boundary guards.
Ensures AI agents cannot read unauthorized system files or write/overwrite project source code.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

from .config import settings


def get_allowed_write_roots() -> List[Path]:
    """Return canonical list of directories where MCP tools are permitted to WRITE files.

    Strictly restricted to:
    1. settings.work_dir (Gaussian computational working directory, e.g. E:\\YDW\\ChemDatas\\Gjf).
    2. Custom write directory specified via GAUSSIAN_ALLOWED_WRITE_ROOTS (if explicitly set).

    PROJECT ROOT, USER HOME, SYSTEM PARTITIONS (C:\\), AND CONFIG DIRECTORIES ARE EXCLUDED.
    """
    allowed: List[Path] = []

    env_write = os.environ.get("GAUSSIAN_ALLOWED_WRITE_ROOTS")
    if env_write:
        for p in env_write.replace(";", ",").split(","):
            p_strip = p.strip()
            if p_strip:
                allowed.append(Path(p_strip).expanduser().resolve())

    if settings.work_dir:
        allowed.append(settings.work_dir.expanduser().resolve())

    # De-duplicate while preserving order
    unique: List[Path] = []
    seen = set()
    for p in allowed:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return unique


def get_allowed_cache_roots() -> List[Path]:
    """Return canonical list of dedicated cache directories.

    Allows user ~/.gaussian-dsh/basis_cache/ or custom GAUSSIAN_CACHE_DIR.
    Managed separately from Gaussian calculation work_dir.
    """
    allowed: List[Path] = []
    env_cache = os.environ.get("GAUSSIAN_CACHE_DIR")
    if env_cache:
        for p in env_cache.replace(";", ",").split(","):
            p_strip = p.strip()
            if p_strip:
                allowed.append(Path(p_strip).expanduser().resolve())

    if settings.data_dir:
        allowed.append((settings.data_dir / "basis_cache").expanduser().resolve())

    unique: List[Path] = []
    seen = set()
    for p in allowed:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return unique


def get_allowed_read_roots() -> List[Path]:
    """Return canonical list of directories where MCP tools are permitted to READ files.

    Includes:
    1. All allowed write directories (settings.work_dir).
    2. Explicit read-only research data directories specified via GAUSSIAN_ALLOWED_READ_ROOTS.
    3. Dedicated cache directories (get_allowed_cache_roots()).
    """
    allowed = list(get_allowed_write_roots()) + list(get_allowed_cache_roots())

    env_read = os.environ.get("GAUSSIAN_ALLOWED_READ_ROOTS")
    if env_read:
        for p in env_read.replace(";", ",").split(","):
            p_strip = p.strip()
            if p_strip:
                allowed.append(Path(p_strip).expanduser().resolve())

    # De-duplicate while preserving order
    unique: List[Path] = []
    seen = set()
    for p in allowed:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return unique


_RESERVED_WIN_DEVICES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def _check_windows_path_hazards(raw_str: str, parsed: Path) -> None:
    """Reject Windows ADS streams, device/UNC paths (NTLM leak), and reserved DOS device names."""
    if raw_str.startswith("\\\\") or raw_str.startswith("//"):
        raise PermissionError(f"Security Boundary Violation: UNC or device paths are forbidden ('{raw_str}').")
    # Alternate Data Stream check: any ':' after optional C: drive prefix
    colon_check = raw_str[2:] if (len(raw_str) >= 2 and raw_str[1] == ":" and raw_str[0].isalpha()) else raw_str
    if ":" in colon_check:
        raise ValueError(f"Invalid path: Windows Alternate Data Stream (:) detected in '{raw_str}'.")
    if os.name == "nt":
        for part in parsed.parts:
            stem = part.split(".")[0].strip().upper()
            if stem in _RESERVED_WIN_DEVICES:
                raise ValueError(f"Invalid path: Reserved Windows device name '{stem}' is forbidden.")


def validate_safe_path(
    target_path: str | Path,
    must_exist: bool = False,
    mode: str = "read",  # "read", "write", or "cache"
    base_dir: Optional[Path] = None,
) -> Path:
    """Validate and resolve a file/directory path against authorized boundaries.

    Args:
        target_path: Target path string or Path object.
        must_exist: If True, raises FileNotFoundError if path does not exist.
        mode: Access mode: 'read', 'write', or 'cache'.
        base_dir: Base directory if target_path is relative (defaults to settings.work_dir).

    Returns:
        Canonical resolved Path object with all junctions/symlinks expanded.

    Raises:
        ValueError: If target_path contains invalid characters (e.g. null bytes, ADS, DOS device names).
        PermissionError: If resolved path falls outside authorized boundaries or uses UNC paths.
        FileNotFoundError: If must_exist is True and file does not exist.
    """
    raw_str = str(target_path)
    if "\0" in raw_str:
        raise ValueError("Invalid path: null byte detected.")

    p = Path(raw_str).expanduser()
    _check_windows_path_hazards(raw_str, p)

    if not p.is_absolute():
        anchor = (base_dir or settings.work_dir).expanduser().resolve()
        resolved = (anchor / p).resolve()
    else:
        resolved = p.resolve()

    # Defense-in-depth: never expose out-of-band human signing keys or grants to sandboxed tools
    data_base = (Path(os.environ.get("GAUSSIAN_DATA_DIR") or settings.data_dir)).expanduser().resolve()
    for restricted in {(data_base / "approvals").resolve(), (settings.data_dir / "approvals").resolve()}:
        try:
            resolved.relative_to(restricted)
            raise PermissionError(
                f"Security Boundary Violation ({mode.upper()} mode): Access to out-of-band human authorization "
                f"directory '{restricted}' is strictly forbidden."
            )
        except ValueError:
            continue

    # Select root whitelist according to access mode
    mode_lower = mode.lower()
    if mode_lower == "write":
        roots = get_allowed_write_roots()
    elif mode_lower == "cache":
        roots = get_allowed_cache_roots()
    else:
        roots = get_allowed_read_roots()

    # Verify that resolved path starts with at least one allowed root prefix
    allowed = False
    for root in roots:
        try:
            resolved.relative_to(root)
            allowed = True
            break
        except ValueError:
            continue

    if not allowed:
        roots_str = "; ".join(str(r) for r in roots)
        raise PermissionError(
            f"Security Boundary Violation ({mode.upper()} mode): Path '{target_path}' resolves to '{resolved}', "
            f"which is outside authorized {mode.upper()} boundaries ({roots_str})."
        )

    if must_exist and not resolved.exists():
        raise FileNotFoundError(f"Requested file does not exist: '{resolved}'")

    return resolved
