# Changelog

All notable changes to `gaussian-dsh-plugin` are documented in this file.

## [0.3.0] - 2026-11-12

### Added
- **Full MCP Tool Parity**: Expanded MCP `stdio` server to `17` core tools (`gaussian_status`, `generate_gaussian_input`, `parse_gaussian_output`, `diagnose_gaussian_error`, `search_gaussian_keywords`, `search_basis_sets`, `get_basis_set`, `generate_gaussian_input_from_smiles`, `submit_gaussian_calculation`, `get_gaussian_job_status`, `list_gaussian_jobs`, `stop_gaussian_calculation`, `extract_structure_from_file`, `postprocess_capabilities`, `create_postprocess_task`, `get_postprocess_task`, `list_postprocess_tasks`) plus `2` optional Sobko tools (`sobko_search`, `sobko_fetch`) when local knowledge base is detected. *(Total: `17` core + `2` optional Sobko = `19` in local KB environment.)*
- **Standalone Agensi Agent Skills (`dist/agensi/*-v0.3.0.zip`)**:
  - Upgraded `gaussian-job-setup` with stdlib CLI `scripts/gjf_helper.py`.
  - Upgraded `gaussian-output-analysis` with stdlib CLI `scripts/log_analyzer.py`.
  - Added `gaussian-postprocessing` skill (`scripts/multiwfn_recipe.py`, `references/multiwfn-vmd-workflow.md`) for Multiwfn 3.8 / VMD / `formchk` workflows with `16,000,000` grid-point protection.
  - Added automated packager & sanitizer `scripts/package_agensi_skills.py`.
- **Cross-Client Templates (`examples/mcp_configs/`)**: Added sanitized templates for Claude Desktop, Codex CLI, and Cursor IDE.
- **Dual npm Packager (`scripts/build_npm_packages.mjs`)**: Produces `@yangdw2024/gp` (`yangdw2024-gp-0.3.0.tgz`) and backward-compatible `@gd/gp` (`gd-gp-0.3.0.tgz`) with built-in `MAX_PATH < 260` checks.
- **Open-Source Governance & CI**: Added `CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md`, `TROUBLESHOOTING.md`, `THIRD_PARTY_LICENSES.md`, `.github/ISSUE_TEMPLATE/`, and `.github/workflows/`.

### Fixed
- **Windows `MAX_PATH=260` Root-Cause Elimination**: Switched `packaging/gaussian-backend.spec` to `EXE(..., contents_directory=".")`, pruned unused `rdkit/Contrib/`, `.dist-info/{licenses,sboms}/`, `jsonschema_specifications/`, `setuptools/`, `_tcl_data/`, `_tk_data/`, and shortened runtime dir to `runtimes/win32-x64/b/` (`1064` files; max relative path reduced from `135` -> `96` chars; verified under 153-char simulated DSH generation prefix at `249 < 260`).
- **Out-of-Repo MCP Execution**: Added `__package__ = "backend"` and `sys.path` bootstrap in `backend/mcp_server.py` so running directly outside repository root succeeds cleanly.
- **Scientific & Parser Fixes**: Fixed `Alpha occ./virt.` eigenvalue regex spanning across newlines into `Excited State`; fixed `--Link1--` + route count `incomplete_multistep` detection; synced FCHK reader and postprocess cube-limit verification (`verify_cube_within_limit`) & `.tga` cleanup.
- **Security Hardening**: Blocked Windows Alternate Data Streams (`:`), UNC SMB (`\\...`), DOS reserved device names (`CON`/`NUL`/`COM1`..`LPT9`), Link0/CRLF injection, `chk` path traversal, `pid <= 0` kills, artifact GC symlink traversal, oversized SMILES DoS (`> 2000` chars), and HTTP `403`/`413` guards on `/v1/gaussian-outputs/parse` & `/v1/structure/extract`.

### Changed
- Restored canonical npm package identifier `@yangdw2024/gp` across `package.json`, `cordis.patch.yml`, `src/client.js`, and `scripts/verify_*.mjs`.

## [0.2.0] - 2026-10-24
- Initial DSH (DeepSeek Harness) Cordis plugin release with `19` DSH tools, FastAPI compiled Windows runtime (`gaussian-backend.exe`), embedded Open Babel `3.2.1`, and initial UI status tab.
