#!/usr/bin/env python3
"""Trusted out-of-band human operator CLI for approving a real Gaussian calculation.

This script is intentionally separate from the MCP Server so an AI Agent cannot invoke
it automatically via MCP tool calls. An operator inspects the chemical route, resource
requests, and SHA-256 digest of the .gjf file, then issues a single-use, task-bound
human_approval_token (and optional host grant receipt).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.config import settings
from backend.execution_policy import (
    authorize_calculation_as_human,
    calculate_content_sha256,
)
from backend.gaussian_input import validate_gjf
from backend.security import validate_safe_path


def _summarize_gjf(content: str) -> dict:
    """Extract route section, charge/multiplicity, and atom count for operator review."""
    routes = []
    charge = None
    multiplicity = None
    atom_count = 0
    seen_cm = False
    for raw in content.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            routes.append(line)
            continue
        if line.startswith("%"):
            continue
        parts = line.split()
        if not seen_cm and len(parts) == 2:
            try:
                charge = int(parts[0])
                multiplicity = int(parts[1])
                seen_cm = True
                continue
            except ValueError:
                pass
        if seen_cm and len(parts) >= 4:
            try:
                float(parts[1])
                float(parts[2])
                float(parts[3])
                atom_count += 1
            except ValueError:
                pass
    return {
        "routes": routes,
        "charge": charge,
        "multiplicity": multiplicity,
        "atom_count": atom_count,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect a Gaussian .gjf file and issue a single-use human approval token."
    )
    parser.add_argument("gjf_path", help="Path to the .gjf file inside an authorized root.")
    parser.add_argument("--preflight-id", required=True, help="Preflight ID from dry-run report.")
    parser.add_argument(
        "--approve-by",
        "--approved-by",
        dest="approved_by",
        required=True,
        help="Non-empty human operator identifier (e.g. name or user ID).",
    )
    parser.add_argument("--expected-sha256", default=None, help="Optional expected SHA-256 digest.")
    parser.add_argument("--job-name", default=None, help="Approved job name (defaults to file stem).")
    parser.add_argument("--mem", default=None, help="Approved memory limit (defaults to settings.default_mem).")
    parser.add_argument("--nproc", type=int, default=None, help="Approved CPU core count.")
    parser.add_argument("--ttl", type=int, default=600, help="Token TTL in seconds (default: 600).")
    parser.add_argument("--no-receipt", action="store_true", help="Do not write signed host grant receipt.")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip interactive confirmation prompt.")
    parser.add_argument("--json", action="store_true", help="Emit JSON output to stdout.")
    args = parser.parse_args(argv)

    operator = (args.approved_by or "").strip()
    if not operator:
        print("Error: --approve-by must be non-empty.", file=sys.stderr)
        return 2

    try:
        safe_path = validate_safe_path(args.gjf_path, must_exist=True, mode="read")
        content = safe_path.read_text(encoding="utf-8", errors="ignore")
        validate_gjf(content, max_atoms=settings.max_atoms)
    except Exception as exc:
        print(f"Validation failed: {exc}", file=sys.stderr)
        return 1

    actual_sha256 = calculate_content_sha256(content)
    summary = _summarize_gjf(content)
    chosen_job_name = args.job_name or safe_path.stem
    chosen_mem = args.mem or settings.default_mem
    chosen_nproc = int(args.nproc or settings.default_nproc)

    digest_lines = [
        "=== Gaussian Job Human Authorization Review ===",
        f"File:          {safe_path}",
        f"SHA-256:       {actual_sha256}",
        f"Preflight ID:  {args.preflight_id}",
        f"Job Name:      {chosen_job_name}",
        f"Resources:     mem={chosen_mem}, nproc={chosen_nproc}",
        f"Route(s):      {' | '.join(summary['routes']) or '(none)'}",
        f"System:        charge={summary['charge']}, multiplicity={summary['multiplicity']}, atoms={summary['atom_count']}",
        f"Operator:      {operator}",
    ]
    out_stream = sys.stderr if args.json else sys.stdout
    print("\n".join(digest_lines), file=out_stream)

    if args.expected_sha256 and actual_sha256 != args.expected_sha256:
        print(
            f"SHA-256 mismatch: expected={args.expected_sha256}, actual={actual_sha256}",
            file=sys.stderr,
        )
        return 1

    if not args.yes:
        try:
            answer = input("Approve exact calculation above? Type 'yes' to issue token: ").strip().lower()
        except EOFError:
            answer = ""
        if answer != "yes":
            print("Approval aborted by operator.", file=sys.stderr)
            return 1

    try:
        result = authorize_calculation_as_human(
            gjf_path=safe_path,
            preflight_id=args.preflight_id,
            expected_sha256=args.expected_sha256,
            job_name=chosen_job_name,
            mem=chosen_mem,
            nproc=chosen_nproc,
            approved_by=operator,
            ttl_seconds=args.ttl,
            save_receipt=not args.no_receipt,
        )
    except Exception as exc:
        print(f"Failed to issue human approval: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("\n=== Human Approval Issued ===")
        print(f"human_approval_token: {result['human_approval_token']}")
        if result.get("receipt_saved"):
            print(f"receipt_saved:        {result['receipt_saved']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
