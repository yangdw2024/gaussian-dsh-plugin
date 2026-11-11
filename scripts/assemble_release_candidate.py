#!/usr/bin/env python3
"""Assemble & audit complete v0.3.0 release candidate bundle under dist/release-candidate/."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import List, Tuple

SECRET_PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
    ("github_pat", re.compile(r"ghp_[A-Za-z0-9]{20,}")),
    ("openai_api_key", re.compile(r"sk-(?!ant-|test)[A-Za-z0-9]{20,}")),
    ("npm_token", re.compile(r"npm_[A-Za-z0-9]{20,}")),
    ("google_api_key", re.compile(r"AIza[0-9A-Za-z\-_]{20,}")),
    ("private_key_block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
]

MCP_SRC_TOP = [
    "mcp_server.py",
    "requirements.txt",
    "requirements-mcp.txt",
    "LICENSE",
    "README.md",
    "SECURITY.md",
    "TROUBLESHOOTING.md",
    "THIRD_PARTY_LICENSES.md",
    "scripts/approve_gaussian_job.py",
]

SKIP_DIRS = {"__pycache__", ".pytest_cache", ".git", "node_modules"}
SKIP_EXTS = {".pyc", ".pyo"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def scan_repo_secrets(repo_root: Path) -> List[str]:
    findings: List[str] = []
    tracked = subprocess.check_output(["git", "ls-files"], cwd=repo_root, text=True).splitlines()
    for rel in tracked:
        fp = repo_root / rel
        if not fp.is_file():
            continue
        try:
            text = fp.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for label, pat in SECRET_PATTERNS:
            m = pat.search(text)
            if m:
                findings.append(f"{rel}: matched {label} ({m.group(0)[:12]}...)")
    return findings


def build_win32_runtime_zip(repo_root: Path, out_zip: Path, version: str) -> None:
    rt_root = repo_root / "runtimes" / "win32-x64"
    rj = rt_root / "runtime.json"
    if not rj.exists():
        raise FileNotFoundError(f"Missing {rj}")
    meta = json.loads(rj.read_text(encoding="utf-8-sig"))
    if meta.get("version") != version:
        raise ValueError(f"runtime.json version {meta.get('version')!r} != {version!r}")

    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for fp in sorted(rt_root.rglob("*")):
            if not fp.is_file() or any(p in SKIP_DIRS for p in fp.parts) or fp.suffix.lower() in SKIP_EXTS:
                continue
            rel = fp.relative_to(rt_root).as_posix()
            zf.write(fp, arcname=f"win32-x64/{rel}")


def build_mcp_src_zip(repo_root: Path, out_zip: Path) -> None:
    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel in MCP_SRC_TOP:
            src = repo_root / rel
            if not src.exists():
                raise FileNotFoundError(f"Missing MCP source member: {src}")
            zf.write(src, arcname=rel)
        for tree_name in ("backend", "examples/mcp_configs"):
            tree_root = repo_root / tree_name
            for fp in sorted(tree_root.rglob("*")):
                if not fp.is_file() or any(p in SKIP_DIRS for p in fp.parts) or fp.suffix.lower() in SKIP_EXTS:
                    continue
                zf.write(fp, arcname=fp.relative_to(repo_root).as_posix())


def write_release_notes(out_path: Path, version: str) -> None:
    out_path.write_text(
        f"""# Gaussian DSH Plugin & MCP Server v{version} (Release Candidate)

> **Human Release Gate**: This bundle is a locally verified Release Candidate (`v{version}`). No automated `npm publish`, `git push`, `gh release create`, or live Agensi submission has been triggered.

## Included Artifacts

1. `yangdw2024-gp-{version}.tgz` — Primary public npm package (`@yangdw2024/gp`, `19` DSH tools + `1` prompt, Windows `MAX_PATH < 260` fixed).
2. `gd-gp-{version}.tgz` — Backward-compatible short-scope npm tarball (`@gd/gp`).
3. `gaussian-backend-{version}-win32-x64.zip` — Compiled Windows x64 runtime (`b/gaussian-backend.exe` + embedded Open Babel `3.2.1` + `runtime.json`).
4. `gaussian-mcp-server-{version}-src.zip` & `requirements-mcp.txt` — Portable standalone Python MCP `stdio` server bundle (`17` core tools + `2` optional Sobko tools).
5. `agensi/gaussian-job-setup-v{version}.zip`, `agensi/gaussian-output-analysis-v{version}.zip`, `agensi/gaussian-postprocessing-v{version}.zip` — Standalone Agensi Agent Skills (`SKILL.md` at ZIP root, bundled zero-dependency stdlib Python CLIs + optional MCP templates).
6. `SHA256SUMS.txt` — Cryptographic SHA-256 manifest for all files in this directory.
""",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Assemble complete release-candidate directory and SHA256SUMS")
    repo_root = Path(__file__).resolve().parent.parent
    parser.add_argument("--version", default="0.3.0")
    parser.add_argument("--rc-dir", type=Path, default=repo_root / "dist" / "release-candidate")
    args = parser.parse_args()

    # 1. Clean staging output so stale artifacts cannot survive
    if args.rc_dir.exists():
        shutil.rmtree(args.rc_dir)
    args.rc_dir.mkdir(parents=True, exist_ok=True)

    # 2. Build dual npm tarballs (includes node scripts/build.mjs & MAX_PATH check)
    subprocess.run(
        ["node", str(repo_root / "scripts" / "build_npm_packages.mjs"), "--out", str(args.rc_dir)],
        cwd=repo_root,
        check=True,
    )

    # 3. Package & verify all 3 Agensi skill ZIPs (writes to dist/agensi and mirrors to rc-dir/agensi)
    subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "package_agensi_skills.py"),
            "--version",
            args.version,
            "--mirror-dir",
            str(args.rc_dir / "agensi"),
        ],
        cwd=repo_root,
        check=True,
    )

    # 4. Build standalone win32-x64 runtime ZIP, MCP source ZIP, requirements-mcp.txt & release notes
    build_win32_runtime_zip(repo_root, args.rc_dir / f"gaussian-backend-{args.version}-win32-x64.zip", args.version)
    build_mcp_src_zip(repo_root, args.rc_dir / f"gaussian-mcp-server-{args.version}-src.zip")
    shutil.copy2(repo_root / "requirements-mcp.txt", args.rc_dir / "requirements-mcp.txt")
    write_release_notes(args.rc_dir / "RELEASE_NOTES.md", args.version)

    # 5. Scan git-tracked repo files for secret leaks
    secret_hits = scan_repo_secrets(repo_root)
    if secret_hits:
        raise RuntimeError("Secret scan detected issues:\n" + "\n".join(secret_hits))

    # 6. Write SHA256SUMS.txt over all files in rc-dir
    sums_path = args.rc_dir / "SHA256SUMS.txt"
    entries: List[str] = []
    for fp in sorted(args.rc_dir.rglob("*")):
        if not fp.is_file() or fp == sums_path:
            continue
        rel = fp.relative_to(args.rc_dir).as_posix()
        entries.append(f"{sha256_file(fp)}  {rel}")
    sums_path.write_text("\n".join(entries) + "\n", encoding="utf-8")

    print(f"Release candidate assembled at: {args.rc_dir}")
    print(f"Files checksummed: {len(entries)}")
    print("Secret scan: 0 hits")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
