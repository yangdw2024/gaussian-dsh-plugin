# Security Policy

## 1. Threat Model & Authorization Boundaries

`gaussian-dsh-plugin` executes computational chemistry tooling on a user's workstation and exposes interfaces to AI Agents via DSH Cordis tools and MCP `stdio`. The architecture enforces the following boundaries:

1. **Three-Layer Real Execution Gate**:
   - **File Integrity (`file_integrity`)**: `.gjf` file bytes and resource budgets (`mem`, `nproc`, `job_name`) are hashed cleanly (`SHA-256`) at dry-run preflight.
   - **Out-of-Band Human Authorization (`human_authorization`)**: Real execution requires a single-use HMAC-SHA256 token and grant receipt created by a human running `scripts/approve_gaussian_job.py` outside the Agent tool boundary. Agent-supplied `confirmed=True` or dry-run `integrity_token` values are explicitly rejected.
   - **Host Gate (`host_execution_gate`)**: `GAUSSIAN_ALLOW_REAL_EXECUTION` defaults to `false`. Unless explicitly enabled by the host owner **and** paired with valid single-use human grant artifacts, real `g16.exe` binaries are never invoked.
2. **Path & Input Sandboxing**:
   - Read/write tools enforce canonical `resolve()` containment under `GAUSSIAN_ALLOWED_READ_ROOTS` and `GAUSSIAN_ALLOWED_WRITE_ROOTS`.
   - `<data_dir>/approvals/` (containing `.human_signing_key` and `grants/`) is strictly blocked from MCP path tools and HTTP log/structure readers (`403`).
   - Windows Alternate Data Streams (`:` except valid drive letter), UNC SMB paths (`\\...`), DOS reserved device names (`CON`, `PRN`, `AUX`, `NUL`, `COM1`..`LPT9`), symlinks, and NTFS junctions outside allowed roots are rejected.
   - `.gjf` Link0 directives reject CR/LF control characters, `%chk` directory traversal, and non-positive core counts.
3. **OS Privilege Separation Note**:
   - If a host grants an AI Agent unrestricted OS shell execution (`bash`/`powershell`) under the **same OS user account** that owns `<data_dir>/approvals/.human_signing_key`, OS-level discretionary ACLs/user separation is required to keep `.human_signing_key` unreadable to shell commands.

## 2. Reporting a Vulnerability

Please do **not** open public GitHub issues containing exploit payloads targeting active user environments or secret material.

- Report security issues privately via GitHub Security Advisories (`Security -> Advisories -> Report a vulnerability`) on `https://github.com/yangdw2024/gaussian-dsh-plugin`.
- Please include: affected component (`backend/security.py`, `execution_policy.py`, `mcp_server.py`, `app.py`, or packaging), reproduction steps, and impact assessment.
