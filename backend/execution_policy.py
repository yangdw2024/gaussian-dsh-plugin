"""Execution policy, file integrity verification, host gate, and out-of-band human authorization.

V5.1 Hardening — Enforces strict separation across three independent trust layers:
1. File & Parameter Integrity (`integrity_token`):
   - Issued by dry-run preflight inspection using an integrity-domain HMAC-SHA256 key.
   - Binds exact `.gjf` SHA-256 digest, `preflight_id`, `job_name`, `mem`, and `nproc`.
   - Proves NO tampering occurred since preflight. Explicitly carries
     `grants_human_approval=False` and NEVER authorizes execution on its own.
2. Host-Level Execution Permission (`GAUSSIAN_ALLOW_REAL_EXECUTION`):
   - Controlled exclusively outside MCP tool calls via host environment configuration.
   - Blocks physical `g16.exe` process launches on workstations/CI where disabled.
3. Task-Specific Human Authorization (`human_approval_token` / Out-of-Band Grant):
   - Signed with a cryptographically separate human-approval secret stored OUTSIDE
     MCP read/write sandbox boundaries (`<data_dir>/approvals/.human_signing_key`).
   - Issued strictly by trusted human-facing interfaces (`authorize_calculation_as_human`,
     `scripts/approve_gaussian_job.py`, or `_require_admin`-guarded `/v1/admin/jobs/approve`).
   - Single-use nonce enforcement blocks token replay attacks.
   - AI Agent boolean flags (`confirmed=True`) or auto-minted preflight tokens are
     explicitly rejected as insufficient for real hardware execution.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("gaussian-dsh-backend")

from .config import settings
from .gaussian_input import validate_gjf
from .resource_scheduler import chem_scheduler
from .security import validate_safe_path

# Ephemeral fallback secrets (domain-separated so integrity and human-approval domains NEVER collide)
_PROCESS_RANDOM_INTEGRITY = secrets.token_hex(32)
_PROCESS_RANDOM_HUMAN = secrets.token_hex(32)


def _data_dir() -> Path:
    env_dir = os.environ.get("GAUSSIAN_DATA_DIR")
    base = Path(env_dir) if env_dir else settings.data_dir
    base.mkdir(parents=True, exist_ok=True)
    return base


def _approvals_dir() -> Path:
    d = _data_dir() / "approvals"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _get_integrity_secret() -> str:
    raw = os.environ.get("GAUSSIAN_POLICY_SECRET") or _PROCESS_RANDOM_INTEGRITY
    return f"GAUSSIAN_INTEGRITY_DOMAIN::{raw}"


def _get_human_approval_secret() -> str:
    """Resolve out-of-band human signing key stored outside MCP read/write roots.

    If GAUSSIAN_HUMAN_APPROVAL_SECRET is set in host env, uses that (domain-separated).
    Otherwise lazily persists a dedicated random key under `<data_dir>/approvals/.human_signing_key`,
    which `validate_safe_path` blocks all MCP tools from reading or writing.
    """
    env_secret = os.environ.get("GAUSSIAN_HUMAN_APPROVAL_SECRET")
    if env_secret:
        return f"GAUSSIAN_HUMAN_APPROVAL_DOMAIN::{env_secret}"

    key_file = _approvals_dir() / ".human_signing_key"
    if key_file.exists():
        try:
            key = key_file.read_text(encoding="utf-8").strip()
            if len(key) >= 32:
                return f"GAUSSIAN_HUMAN_APPROVAL_DOMAIN::{key}"
        except Exception:
            pass

    generated = secrets.token_hex(32)
    try:
        tmp = key_file.with_name(f".human_signing_key.{os.getpid()}.tmp")
        tmp.write_text(generated, encoding="utf-8")
        os.replace(tmp, key_file)
    except Exception:
        generated = _PROCESS_RANDOM_HUMAN
    return f"GAUSSIAN_HUMAN_APPROVAL_DOMAIN::{generated}"


def _hmac_sign(secret: str, payload: Dict[str, Any]) -> str:
    payload_json = json.dumps(payload, sort_keys=True)
    sig = hmac.new(
        secret.encode("utf-8"),
        payload_json.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{payload_json.encode('utf-8').hex()}.{sig}"


def _hmac_verify(secret: str, token: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    if not token or "." not in token:
        return False, "Malformed or empty token.", None
    payload_hex, sig = token.split(".", 1)
    try:
        payload_json = bytes.fromhex(payload_hex).decode("utf-8")
        expected_sig = hmac.new(
            secret.encode("utf-8"),
            payload_json.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return False, "Token HMAC signature verification failed.", None
        payload = json.loads(payload_json)
        return True, "Signature verified.", payload
    except Exception as exc:
        return False, f"Token decoding failed: {exc}", None


def calculate_file_sha256(path: Path) -> str:
    """Calculate hex SHA-256 digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def calculate_content_sha256(content: str) -> str:
    """Calculate hex SHA-256 digest of UTF-8 string content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def issue_integrity_token(
    file_sha256: str,
    job_name: str,
    mem: str,
    nproc: int,
    preflight_id: Optional[str] = None,
    ttl_seconds: int = 900,
) -> str:
    """Issue a preflight file-integrity token (HMAC-SHA256).

    Explicitly marks grants_human_approval=False; proves only preflight snapshot integrity.
    """
    payload = {
        "kind": "file_integrity",
        "grants_human_approval": False,
        "preflight_id": preflight_id or uuid.uuid4().hex[:16],
        "sha256": file_sha256,
        "job_name": job_name,
        "mem": mem,
        "nproc": int(nproc),
        "exp": time.time() + ttl_seconds,
    }
    return _hmac_sign(_get_integrity_secret(), payload)


def issue_execution_token(
    file_sha256: str,
    job_name: str,
    mem: str,
    nproc: int,
    ttl_seconds: int = 900,
) -> str:
    """Backward-compatible wrapper returning a file-integrity token (NOT human approval)."""
    return issue_integrity_token(
        file_sha256=file_sha256,
        job_name=job_name,
        mem=mem,
        nproc=nproc,
        ttl_seconds=ttl_seconds,
    )


def verify_integrity_token(
    token: str,
    current_sha256: str,
    expected_job_name: Optional[str] = None,
    expected_mem: Optional[str] = None,
    expected_nproc: Optional[int] = None,
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """Verify Layer 1 (file integrity & parameter binding)."""
    ok, msg, payload = _hmac_verify(_get_integrity_secret(), token)
    if not ok or payload is None:
        return False, f"Integrity token rejected: {msg}", None
    if payload.get("kind") != "file_integrity":
        return False, "Invalid integrity token type.", None
    if time.time() > float(payload.get("exp", 0)):
        return False, "Preflight integrity token has expired. Please run preflight again.", None
    if payload.get("sha256") != current_sha256:
        return False, "Input file content changed since preflight integrity check.", None
    if expected_job_name is not None and payload.get("job_name") != expected_job_name:
        return False, f"job_name mismatch (preflight={payload.get('job_name')}, submitted={expected_job_name}).", None
    if expected_mem is not None and payload.get("mem") != expected_mem:
        return False, f"mem mismatch (preflight={payload.get('mem')}, submitted={expected_mem}).", None
    if expected_nproc is not None and int(payload.get("nproc", -1)) != int(expected_nproc):
        return False, f"nproc mismatch (preflight={payload.get('nproc')}, submitted={expected_nproc}).", None
    return True, "File integrity and resource bounds verified.", payload


def verify_execution_token(token: str, current_sha256: str) -> Tuple[bool, str]:
    """Backward-compatible Layer 1 integrity verification tuple (ok, reason)."""
    ok, reason, _ = verify_integrity_token(token=token, current_sha256=current_sha256)
    return ok, reason


def is_real_execution_authorized() -> bool:
    """Layer 2: Check whether host environment permits spawning real g16.exe processes."""
    return os.environ.get("GAUSSIAN_ALLOW_REAL_EXECUTION", "").strip().lower() in {"1", "true", "yes"}


def authorize_calculation_as_human(
    gjf_path: Path,
    preflight_id: str,
    expected_sha256: Optional[str] = None,
    job_name: Optional[str] = None,
    mem: Optional[str] = None,
    nproc: Optional[int] = None,
    approved_by: str = "human_operator",
    ttl_seconds: int = 600,
    save_receipt: bool = True,
) -> Dict[str, Any]:
    """Layer 3 Trusted Out-of-Band Human Authorization Provider.

    MUST ONLY be called by human-facing operator scripts (`scripts/approve_gaussian_job.py`)
    or admin-authenticated host UI (`POST /v1/admin/jobs/approve`), NEVER registered as an MCP tool.
    Issues a cryptographically distinct, single-use human approval token bound to exact SHA-256 and limits.
    """
    safe_path = validate_safe_path(gjf_path, must_exist=True, mode="read")
    content = safe_path.read_text(encoding="utf-8", errors="ignore")
    actual_sha256 = calculate_content_sha256(content)
    if expected_sha256 and actual_sha256 != expected_sha256:
        raise ValueError(
            f"Refusing human authorization: GJF SHA-256 mismatch (expected={expected_sha256}, actual={actual_sha256})."
        )

    validate_gjf(content, max_atoms=settings.max_atoms)
    clean_job_name = job_name or safe_path.stem
    chosen_mem = mem or settings.default_mem
    chosen_nproc = int(nproc or settings.default_nproc)
    nonce = secrets.token_hex(16)
    expires_at = time.time() + ttl_seconds

    payload = {
        "kind": "human_approval",
        "grants_human_approval": True,
        "preflight_id": preflight_id,
        "sha256": actual_sha256,
        "job_name": clean_job_name,
        "mem": chosen_mem,
        "nproc": chosen_nproc,
        "approved_by": approved_by,
        "approved_at": time.time(),
        "nonce": nonce,
        "exp": expires_at,
    }
    token = _hmac_sign(_get_human_approval_secret(), payload)

    receipt_path: Optional[Path] = None
    if save_receipt:
        grants_dir = _approvals_dir() / "grants"
        grants_dir.mkdir(parents=True, exist_ok=True)
        receipt_path = grants_dir / f"{re.sub(r'[^\w.-]', '_', preflight_id)}.json"
        tmp = receipt_path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(
                {
                    "preflight_id": preflight_id,
                    "sha256": actual_sha256,
                    "job_name": clean_job_name,
                    "mem": chosen_mem,
                    "nproc": chosen_nproc,
                    "approved_by": approved_by,
                    "exp": expires_at,
                    "human_approval_token": token,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        os.replace(tmp, receipt_path)

    return {
        "ok": True,
        "preflight_id": preflight_id,
        "sha256": actual_sha256,
        "job_name": clean_job_name,
        "mem": chosen_mem,
        "nproc": chosen_nproc,
        "approved_by": approved_by,
        "expires_at": expires_at,
        "human_approval_token": token,
        "receipt_saved": str(receipt_path) if receipt_path else None,
    }


def verify_human_approval(
    human_approval_token: Optional[str],
    current_sha256: str,
    job_name: str,
    mem: str,
    nproc: int,
    preflight_id: Optional[str] = None,
    consume: bool = True,
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """Verify Layer 3 (task-specific, non-agent human authorization) with replay protection."""
    candidate_token = (human_approval_token or "").strip()
    grant_file: Optional[Path] = None

    if not candidate_token and preflight_id:
        safe_pid = re.sub(r"[^\w.-]", "_", preflight_id)
        candidate_grant = _approvals_dir() / "grants" / f"{safe_pid}.json"
        if candidate_grant.exists():
            try:
                grant_data = json.loads(candidate_grant.read_text(encoding="utf-8"))
                candidate_token = grant_data.get("human_approval_token", "").strip()
                grant_file = candidate_grant
            except Exception as exc:
                return False, f"Failed to read host approval grant: {exc}", None

    if not candidate_token:
        return (
            False,
            "Human authorization required: Agent-supplied flags (confirmed=True) and preflight integrity "
            "tokens do NOT grant execution permission. Operator must authorize this exact task via "
            "scripts/approve_gaussian_job.py or host admin UI.",
            None,
        )

    # Explicit detection if an Agent tried passing its preflight integrity token as human approval
    int_ok, _, int_payload = _hmac_verify(_get_integrity_secret(), candidate_token)
    if int_ok and int_payload and int_payload.get("kind") == "file_integrity":
        return (
            False,
            "Authorization rejected: Agent auto-issued preflight integrity_token cannot be substituted "
            "for out-of-band human_approval_token.",
            None,
        )

    ok, msg, payload = _hmac_verify(_get_human_approval_secret(), candidate_token)
    if not ok or payload is None:
        return False, f"Human approval token rejected: {msg}", None

    if payload.get("kind") != "human_approval" or not payload.get("grants_human_approval"):
        return False, "Token does not grant human execution authorization.", None

    if time.time() > float(payload.get("exp", 0)):
        return False, "Human approval token has expired.", None

    if payload.get("sha256") != current_sha256:
        return False, "Input GJF file digest differs from the file approved by human operator.", None

    if payload.get("job_name") != job_name or payload.get("mem") != mem or int(payload.get("nproc", -1)) != int(nproc):
        return (
            False,
            "Calculation parameters (job_name/mem/nproc) deviate from human-approved parameters.",
            None,
        )

    if preflight_id and payload.get("preflight_id") != preflight_id:
        return False, "Human approval token belongs to a different preflight_id.", None

    nonce = payload.get("nonce")
    if not nonce:
        return False, "Malformed human approval token: missing single-use nonce.", None

    consumed_dir = _approvals_dir() / "consumed"
    consumed_dir.mkdir(parents=True, exist_ok=True)
    used_marker = consumed_dir / f"{re.sub(r'[^\w.-]', '_', str(nonce))}.used"

    if used_marker.exists():
        return False, "Human approval token has already been used (replay blocked).", None

    if consume:
        try:
            with open(used_marker, "x", encoding="utf-8") as f:
                f.write(json.dumps({"consumed_at": time.time(), "sha256": current_sha256}))
        except FileExistsError:
            return False, "Human approval token has already been consumed concurrently (replay blocked).", None
        if grant_file and grant_file.exists():
            try:
                grant_file.unlink(missing_ok=True)
            except Exception:
                pass

    return True, f"Authorized by human operator ({payload.get('approved_by', 'unknown')}).", payload


def evaluate_real_execution_authorization(
    gjf_path: Path,
    integrity_token: Optional[str],
    human_approval_token: Optional[str],
    job_name: Optional[str] = None,
    mem: Optional[str] = None,
    nproc: Optional[int] = None,
    preflight_id: Optional[str] = None,
    consume_human_token: bool = True,
) -> Dict[str, Any]:
    """Evaluate all three independent authorization layers before allowing g16.exe execution.

    Order of checks:
      1. Layer 1 — File & parameter integrity (integrity_token vs current .gjf SHA-256)
      2. Layer 3 — Task-specific human authorization (non-agent out-of-band token / receipt)
      3. Layer 2 — Host-level execution permission (GAUSSIAN_ALLOW_REAL_EXECUTION)
    Note: Layer 2 is checked cleanly so host gate blocks physical execution without falsely
    marking human authorization missing when a test provides valid human approval on a locked host!
    Wait: if human authorization FAILS, reject BEFORE or clearly distinguish BOTH in audit output!
    """
    safe_path = validate_safe_path(gjf_path, must_exist=True, mode="read")
    content = safe_path.read_text(encoding="utf-8", errors="ignore")
    current_sha256 = calculate_content_sha256(content)
    clean_job_name = job_name or safe_path.stem
    chosen_mem = mem or settings.default_mem
    chosen_nproc = int(nproc or settings.default_nproc)

    audit = {
        "file_integrity_verified": False,
        "human_task_authorized": False,
        "host_execution_permitted": is_real_execution_authorized(),
        "approved_by": None,
        "sha256": current_sha256,
    }

    # Layer 1: File Integrity Check
    int_ok, int_reason, int_payload = verify_integrity_token(
        token=integrity_token or "",
        current_sha256=current_sha256,
        expected_job_name=clean_job_name,
        expected_mem=chosen_mem,
        expected_nproc=chosen_nproc,
    )
    if not int_ok:
        return {"ok": False, "rejected_layer": "file_integrity", "error": int_reason, "authorization_audit": audit}
    audit["file_integrity_verified"] = True

    effective_preflight_id = preflight_id or (int_payload.get("preflight_id") if int_payload else None)

    # Layer 3: Task-Specific Human Authorization Check (non-consuming probe first if host gate disabled,
    # OR validate strictly — wait: reject human auth failures first so Agent self-approval NEVER reaches host gate!)
    # Consume only if host execution is ALSO permitted, so valid human approval isn't wasted if host is locked,
    # OR consume strictly when valid. Let's check non-consuming first; if invalid -> reject immediately;
    # if host gate disabled -> reject at host_gate; if host gate enabled -> consume atomically!
    human_ok, human_reason, human_payload = verify_human_approval(
        human_approval_token=human_approval_token,
        current_sha256=current_sha256,
        job_name=clean_job_name,
        mem=chosen_mem,
        nproc=chosen_nproc,
        preflight_id=effective_preflight_id,
        consume=False,
    )
    if not human_ok:
        return {"ok": False, "rejected_layer": "human_authorization", "error": human_reason, "authorization_audit": audit}
    audit["human_task_authorized"] = True
    audit["approved_by"] = human_payload.get("approved_by") if human_payload else None

    # Layer 2: Host Execution Gate
    if not audit["host_execution_permitted"]:
        return {
            "ok": False,
            "rejected_layer": "host_execution_gate",
            "error": (
                "Real Gaussian execution (g16.exe) is blocked: host environment has not set "
                "GAUSSIAN_ALLOW_REAL_EXECUTION=true. Set mock_mode=True for simulated verification."
            ),
            "authorization_audit": audit,
        }

    # Consume single-use human approval nonce only when all 3 gates succeed
    if consume_human_token:
        consumed_ok, consume_reason, _ = verify_human_approval(
            human_approval_token=human_approval_token,
            current_sha256=current_sha256,
            job_name=clean_job_name,
            mem=chosen_mem,
            nproc=chosen_nproc,
            preflight_id=effective_preflight_id,
            consume=True,
        )
        if not consumed_ok:
            audit["human_task_authorized"] = False
            return {"ok": False, "rejected_layer": "human_authorization", "error": consume_reason, "authorization_audit": audit}

    return {"ok": True, "authorization_audit": audit}


def run_preflight_check(
    gjf_path: Path,
    job_name: Optional[str] = None,
    mem: Optional[str] = None,
    nproc: Optional[int] = None,
) -> Dict[str, Any]:
    """Conduct preflight inspection and issue a file-integrity token (NOT human approval)."""
    safe_path = validate_safe_path(gjf_path, must_exist=True, mode="read")
    content = safe_path.read_text(encoding="utf-8", errors="ignore")
    file_sha256 = calculate_content_sha256(content)

    charge_val = None
    multiplicity_val = None
    atom_count_val = 0
    seen_cm = False
    cm_re = re.compile(r"^\s*(-?\d+)\s+(\d+)\s*$")
    elem_re = re.compile(r"^[A-Za-z]{1,2}$")
    coord_re = re.compile(r"^\s*(?:[A-Za-z]{1,2}|\d{1,3})\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)")

    for line in content.splitlines():
        line_s = line.strip()
        if not line_s or line_s.startswith("%") or line_s.startswith("#"):
            continue
        if not seen_cm and cm_re.match(line_s) and not elem_re.match(line_s.split()[0]):
            m = cm_re.match(line_s)
            charge_val = int(m.group(1))
            multiplicity_val = int(m.group(2))
            seen_cm = True
            continue
        if seen_cm and coord_re.match(line_s):
            atom_count_val += 1

    try:
        validate_gjf(content, max_atoms=settings.max_atoms)
        gjf_valid = True
        validation_error = None
    except ValueError as exc:
        gjf_valid = False
        validation_error = str(exc)

    try:
        work_dir = Path(os.environ.get("GAUSSIAN_WORK_DIR", str(settings.work_dir)))
        _, _, free = shutil.disk_usage(work_dir)
        free_gb = round(free / (1024**3), 2)
        disk_ok = free_gb >= 2.0
    except Exception:
        free_gb = 0.0
        disk_ok = True

    current_lease = chem_scheduler.current_lease()
    scheduler_ready = current_lease is None

    chosen_mem = mem or settings.default_mem
    chosen_nproc = int(nproc or settings.default_nproc)
    clean_job_name = job_name or safe_path.stem
    preflight_id = uuid.uuid4().hex[:16]

    integrity_token = issue_integrity_token(
        file_sha256=file_sha256,
        job_name=clean_job_name,
        mem=chosen_mem,
        nproc=chosen_nproc,
        preflight_id=preflight_id,
        ttl_seconds=900,
    )

    reasons = []
    if not gjf_valid:
        reasons.append(f"GJF syntax error: {validation_error}")
    if not disk_ok:
        reasons.append(f"Insufficient disk space ({free_gb}GB < 2.0GB required)")
    if not scheduler_ready:
        reasons.append(f"Compute resource is currently busy (held by {current_lease.owner_id} for {current_lease.kind})")

    ready = len(reasons) == 0

    return {
        "status": "ready" if ready else "blocked",
        "preflight_passed": ready,
        "preflight_id": preflight_id,
        "failure_reason": "; ".join(reasons) if reasons else None,
        "charge": charge_val,
        "multiplicity": multiplicity_val,
        "atom_count": atom_count_val,
        "input_file": {
            "name": safe_path.name,
            "path": str(safe_path),
            "size_bytes": safe_path.stat().st_size,
            "sha256": file_sha256,
            "syntax_valid": gjf_valid,
            "validation_error": validation_error,
        },
        "resources_requested": {
            "job_name": clean_job_name,
            "mem": chosen_mem,
            "nproc": chosen_nproc,
            "work_dir": str(os.environ.get("GAUSSIAN_WORK_DIR", str(settings.work_dir))),
            "free_disk_gb": free_gb,
        },
        "scheduler_status": {
            "active_lease_held": current_lease is not None,
            "held_by": current_lease.owner_id if current_lease else None,
            "lease_kind": current_lease.kind if current_lease else None,
            "holder_pid": current_lease.holder_pid if current_lease else None,
            "host_client": current_lease.host_client if current_lease else None,
        },
        "authorization_model": {
            "layer_1_file_integrity_token_issued": True,
            "layer_2_host_real_execution_permitted": is_real_execution_authorized(),
            "layer_3_human_task_authorization_granted": False,
            "grants_human_approval": False,
        },
        "real_execution_authorized_on_host": is_real_execution_authorized(),
        "integrity_token": integrity_token,
        # Retained alias for integrity verification backward compatibility (strictly NOT human approval)
        "execution_token": integrity_token,
        "auth_token": integrity_token,
        "instructions": (
            "Preflight integrity check complete. Note: integrity_token verifies file/parameter integrity ONLY "
            "and does NOT grant human approval. To execute: "
            "1. For safe simulated testing: set dry_run=False and mock_mode=True. "
            "2. For real g16.exe hardware execution: host must enable GAUSSIAN_ALLOW_REAL_EXECUTION=true AND "
            "a human operator must issue an out-of-band human_approval_token via scripts/approve_gaussian_job.py "
            "or host admin UI."
        ),
    }
