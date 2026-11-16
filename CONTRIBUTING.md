# Contributing to `gaussian-dsh-plugin`

Thank you for helping improve `gaussian-dsh-plugin`! This guide covers local development setup, testing expectations, and build workflows.

## 1. Prerequisites

- **Python**: `3.12+` (`python -m pip install -r requirements.txt -r requirements-mcp.txt`)
  - *Windows note*: Ensure you invoke Python 3.12 with all required packages (`fastapi`, `uvicorn`, `pydantic`, `psutil`, `rdkit`, `requests`, `mcp`) rather than an unrelated base Conda interpreter.
- **Node.js**: `>= 20` (`npm ci` / `npm install` when updating JS tooling)
- **Optional proprietary tools** (never required for unit tests):
  - Gaussian 16 (`g16.exe`, `formchk.exe`)
  - Multiwfn 3.8 (`Multiwfn.exe`)
  - VMD (`vmd.exe`)

## 2. Running Automated Tests

All tests use Python's standard `unittest` framework and are safe to run offline without executing real `g16.exe` jobs:

```bash
python -m unittest discover -s tests -v
```

Security and engineering invariants that PRs must preserve:
1. **No real Gaussian execution in tests**: Never set `GAUSSIAN_ALLOW_REAL_EXECUTION=true` in automated suites without strict mocking; real calculations require all 3 authorization layers.
2. **Never fabricate scientific energies**: Simulated mock outputs must always stay explicitly flagged (`is_simulated=True`, `energy_source="mock_simulation"`).
3. **Preserve path sandboxing & Windows `MAX_PATH < 260`**: Any new PyInstaller dependencies must pass `node scripts/build_npm_packages.mjs` without exceeding the `260`-char Windows path limit under deep DSH installation roots.

## 3. Rebuilding Components

- **Rebuild DSH JS plugin (`lib/`)**:
  ```bash
  node scripts/build.mjs
  ```
- **Rebuild Windows PyInstaller Backend (`runtimes/win32-x64/`)** *(maintainers on Windows)*:
  ```powershell
  .\scripts\build_backend.ps1 -PythonPath "<PATH_TO_PYTHON312>\python.exe" -SitePackages "<PATH_TO_PYTHON312>\Lib\site-packages"
  .\scripts\deploy_runtime.ps1 -Version 0.3.0
  .\scripts\smoke_test_backend.ps1
  ```
- **Package Agensi Skills ZIPs**:
  ```bash
  python scripts/package_agensi_skills.py
  ```

## 4. Pull Request Guidelines

- Keep diffs focused, well-tested, and free of hardcoded host paths (`C:\Users\...`, `D:\G16W\...`) or credentials.
- Document any changes to MCP tool schemas, DSH tool contracts, or environment variables in `README.md` and `CHANGELOG.md`.
