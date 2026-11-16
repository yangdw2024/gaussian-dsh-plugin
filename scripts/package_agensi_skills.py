#!/usr/bin/env python3
"""Package standalone Agensi Agent Skills under skills/* into validated ZIP archives.

Agensi requirement:
  - Each ZIP must place `SKILL.md` directly at the archive root with valid YAML frontmatter.
  - Bundled `scripts/`, `references/`, and `templates/` live at root alongside `SKILL.md`.
  - No host secrets, tokens, or personal absolute paths may be shipped inside the ZIP.
"""
from __future__ import annotations

import argparse
import re
import shutil
import zipfile
from pathlib import Path
from typing import Dict, List

FORBIDDEN_PATTERNS = [
    ("github_token", re.compile(r"ghp_[A-Za-z0-9]{20,}")),
    ("openai_key", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("npm_token", re.compile(r"npm_[A-Za-z0-9]{20,}")),
    ("google_key", re.compile(r"AIza[0-9A-Za-z\-_]{20,}")),
    ("personal_path_users", re.compile(r"[A-Za-z]:[/\\]Users[/\\]Administrator", re.I)),
    ("personal_path_ydw", re.compile(r"E:[/\\]YDW|D:[/\\]G16W|D:[/\\]Multiwfn|D:[/\\]VMD", re.I)),
]

SKIP_DIR_NAMES = {"__pycache__", ".pytest_cache", ".git", "node_modules"}
SKIP_SUFFIXES = {".pyc", ".pyo", ".zip"}


def parse_frontmatter(md_text: str) -> Dict[str, str]:
    m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", md_text, re.DOTALL)
    if not m:
        raise ValueError("Missing YAML frontmatter delimited by '---' at top of SKILL.md")
    meta: Dict[str, str] = {}
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        k, v = line.split(":", 1)
        meta[k.strip()] = v.strip().strip('"').strip("'")
    for req in ("name", "description", "version"):
        if not meta.get(req):
            raise ValueError(f"SKILL.md frontmatter missing required field: {req}")
    return meta


def scan_sanitization(rel_path: str, content: bytes) -> None:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return
    for label, pat in FORBIDDEN_PATTERNS:
        hit = pat.search(text)
        if hit:
            raise ValueError(f"Sanitization failed ({label}) in {rel_path}: matched {hit.group(0)!r}")


def package_skill(skill_dir: Path, out_dir: Path, expected_version: str | None = None) -> Path:
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        raise FileNotFoundError(f"Missing SKILL.md in {skill_dir}")

    meta = parse_frontmatter(skill_md.read_text(encoding="utf-8"))
    if expected_version and meta["version"] != expected_version:
        raise ValueError(
            f"Skill {skill_dir.name} version {meta['version']!r} != expected {expected_version!r}"
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / f"{meta['name']}-v{meta['version']}.zip"

    archived: List[str] = []
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(skill_dir.rglob("*")):
            if not file_path.is_file():
                continue
            if any(part in SKIP_DIR_NAMES for part in file_path.parts):
                continue
            if file_path.suffix.lower() in SKIP_SUFFIXES or file_path.name == ".DS_Store":
                continue
            rel = file_path.relative_to(skill_dir).as_posix()
            raw = file_path.read_bytes()
            scan_sanitization(f"{skill_dir.name}/{rel}", raw)
            zf.writestr(rel, raw)
            archived.append(rel)

    # Read back and verify ZIP integrity cleanly
    with zipfile.ZipFile(zip_path, "r") as zf:
        bad = zf.testzip()
        if bad is not None:
            raise RuntimeError(f"Corrupted ZIP entry {bad} in {zip_path}")
        names = set(zf.namelist())
        if "SKILL.md" not in names:
            raise RuntimeError(f"'SKILL.md' missing at ZIP root of {zip_path}")
        # Verify internal path references mentioned in SKILL.md exist inside ZIP
        md_body = zf.read("SKILL.md").decode("utf-8")
        for ref in re.findall(r"`((?:scripts|references|templates)/[^`\s]+)`", md_body):
            if ref not in names:
                raise RuntimeError(f"SKILL.md references missing archive member {ref!r} in {zip_path}")

    return zip_path


def package_all(skills_root: Path, out_dir: Path, expected_version: str | None = None) -> List[Path]:
    built: List[Path] = []
    for candidate in sorted(skills_root.iterdir()):
        if candidate.is_dir() and (candidate / "SKILL.md").exists():
            built.append(package_skill(candidate, out_dir, expected_version=expected_version))
    if not built:
        raise RuntimeError(f"No valid skills discovered under {skills_root}")
    return built


def main() -> int:
    parser = argparse.ArgumentParser(description="Build & verify Agensi standalone skill ZIPs")
    repo_root = Path(__file__).resolve().parent.parent
    parser.add_argument("--skills-dir", type=Path, default=repo_root / "skills")
    parser.add_argument("--out-dir", type=Path, default=repo_root / "dist" / "agensi")
    parser.add_argument("--mirror-dir", type=Path, default=repo_root / "dist" / "release-candidate" / "agensi")
    parser.add_argument("--version", default="0.3.0")
    args = parser.parse_args()

    built = package_all(args.skills_dir, args.out_dir, expected_version=args.version)
    if args.mirror_dir:
        args.mirror_dir.mkdir(parents=True, exist_ok=True)
    for zp in built:
        if args.mirror_dir:
            shutil.copy2(zp, args.mirror_dir / zp.name)
        print(f"OK: {zp} ({zp.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
