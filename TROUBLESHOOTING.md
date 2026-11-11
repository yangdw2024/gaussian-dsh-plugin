# Troubleshooting Guide

## 1. Windows Path Length (`WinError 206` / `MAX_PATH=260`)
- **Symptoms**: Extracting `@yangdw2024/gp` inside DSH `.generations\live\...` fails on deep `.dist-info/licenses/` or `rdkit.libs/` paths, or PyInstaller EXE fails silently at startup when `LongPathsEnabled=0`.
- **v0.3.0 Resolution**: Runtime binaries now reside in `runtimes/win32-x64/b/` with flat PyInstaller layout (`contents_directory="."`), keeping relative paths `<= 96` chars so total installed paths stay `< 250` chars under standard DSH roots.
- **Verification**:
  ```powershell
  node scripts/build_npm_packages.mjs
  node scripts/verify_installed_runtime.mjs "<path_to_node_modules>\@yangdw2024\gp\lib\index.js"
  ```

## 2. Wrong Python Interpreter Selected on Windows (Miniconda / Base vs Python 3.12)
- **Symptoms**: `ModuleNotFoundError: No module named 'mcp'` or missing `fastapi`/`rdkit` when running `mcp_server.py` or `unittest`.
- **Fix**: Explicitly point your MCP client config (`examples/mcp_configs/`) and build scripts (`-PythonPath`) to your Python 3.12 executable that has `requirements.txt` and `requirements-mcp.txt` installed, rather than relying on unpinned `python` on `PATH`.

## 3. Running `backend/mcp_server.py` Outside Repo Root
- **Symptoms** *(older versions `< 0.3.0`)*: `ImportError: attempted relative import with no known parent package`.
- **Fix**: Upgrade to `0.3.0` (includes `__package__ = "backend"` bootstrap in `backend/mcp_server.py`), or point MCP clients to root `mcp_server.py`.

## 4. `codex exec` Hangs or Agent Simulates Results Instead of Calling MCP Tools
- **Symptoms**: Passing a prompt positional argument without piped stdin or running in an untrusted workspace directory without `--approve-for-me` causes `codex exec` to wait on `"Reading additional input from stdin..."` or skip MCP execution.
- **Fix**: Pipe prompts via stdin (`'prompt' | codex exec ... -`), register trust for the repo in your Codex config, or inspect the tool trace for `mcp: gaussian/<tool> (completed)`.

## 5. `submit_gaussian_calculation` Refuses Real `g16.exe` Execution
- **Behavior**: Even with `confirmed=True` or `mock=False`, execution stops at `human_authorization` or `host_execution_gate`.
- **Cause**: Security-by-default blocks autonomous real Gaussian execution. To run a real job intentionally:
  1. Generate `.gjf` and inspect preflight `integrity_token` via dry-run (`dry_run=True`).
  2. Authorize that exact job out-of-band on the host: `python scripts/approve_gaussian_job.py ...`.
  3. Set `GAUSSIAN_ALLOW_REAL_EXECUTION=true` in the host service environment and supply the single-use `human_approval_token`.

## 6. `get_basis_set` Offline Fallback
- **Behavior**: Network requests to Basis Set Exchange fail in offline/air-gapped labs.
- **Expected Fallback**: The client warns once and falls back to the built-in offline basis set catalog plus user cache under `~/.gaussian-dsh/basis_cache/` (explicitly permitted cache directory even when `GAUSSIAN_WORK_DIR` is on another drive).

## 7. Multiwfn / VMD Cube Postprocessing Rejected or Timed Out
- **Cause**: Requested grid resolution exceeds `16,000,000` points (`nx * ny * nz > 16000000`), or `FORMCHK_EXE` / `MULTIWFN_EXE` / `VMD_EXE` points to an unconfigured path.
- **Fix**: Run `postprocess_capabilities` first to verify all three external binaries exist, and use `coarse` or `medium` grids before `fine`.
