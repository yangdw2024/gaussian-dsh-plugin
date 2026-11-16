# Third-Party Licenses & Software Notices

`gaussian-dsh-plugin` source code (JavaScript, Python backend, MCP server, and bundled Agensi Skill scripts/docs) is licensed under the **[MIT License](./LICENSE)**.

## 1. Python Dependencies Audited in `v0.3.0` Build Environment

Verified via `importlib.metadata` against the `Python 3.12` build environment:

| Package | Audited Version | Declared License |
| :--- | :--- | :--- |
| `mcp` | `1.28.1` | `MIT` |
| `fastapi` | `0.162.2` | `MIT` |
| `uvicorn` | `0.49.0` | `BSD-3-Clause` |
| `pydantic` | `2.13.4` | `MIT` |
| `psutil` | `7.2.2` | `BSD-3-Clause` |
| `rdkit` | `2026.9.1` | `BSD-3-Clause` |
| `numpy` | `2.5.0` | `BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0` |
| `requests` | `2.34.2` | `Apache-2.0` |
| `anyio` | `4.14.1` | `MIT` |
| `httpx` | `0.28.1` | `BSD-3-Clause` |
| `starlette` | `1.3.1` | `BSD-3-Clause` |
| `pyinstaller` *(build tool)* | `6.22.3` | `GPLv2-or-later with bootloader exception` |

## 2. Bundled Open Babel Binary Distribution

- **Open Babel `3.2.1`** (`thirdparty/openbabel/` & packaged `runtimes/win32-x64/openbabel/`): Licensed under **GNU General Public License v2.0 (`GPL-2.0-only`)**. Invoked purely via subprocess (`obabel.exe`) for SDF/LOG structure extraction and format conversion without linking its C++ API into the MIT codebase.

## 3. External User-Provided Proprietary / Third-Party Tools

The following tools are **not** bundled, redistributed, or licensed by `gaussian-dsh-plugin`. Users must obtain valid licenses and install them separately on their own machines:

- **Gaussian 16 (`g16.exe`, `formchk.exe`)** — Proprietary commercial software by Gaussian, Inc.
- **Multiwfn (`Multiwfn.exe`, tested with `3.8`)** — Copyright Tian Lu; distributed under Multiwfn license terms.
- **VMD (`vmd.exe`)** — University of Illinois at Urbana-Champaign (UIUC) VMD License.
- **Sobko Local Knowledge Base** *(optional user extension)* — Configured separately if installed locally; not required or bundled.
