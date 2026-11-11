---
name: gaussian-job-setup
description: Computational chemistry workflow skill for generating production-grade Gaussian 16 (.gjf) input files from 2D SMILES or 3D Cartesian coordinates, querying standard functionals and basis sets, and validating molecular constraints.
version: 1.0.0
author: yangdw
tags:
  - computational-chemistry
  - gaussian
  - dft
  - rdkit
  - mcp
---

# Gaussian Job Setup Skill

This skill guides AI Agents (such as Claude Code, Codex CLI, Cursor) to prepare, validate, and construct standard **Gaussian 16 (.gjf)** input files for molecular quantum chemical calculations.

## Capabilities

1. **SMILES to 3D Input**: Convert 2D chemical formulas or SMILES (e.g., `CCO`, `c1ccccc1`) into 3D conformers using RDKit ETKDGv3 and MMFF94s energy minimization, then generate `.gjf` input files.
2. **Coordinate Validation**: Ensure correct Cartesian coordinates, charge, spin multiplicity (2S+1), and atom count limits (<= 300).
3. **Route Line Configuration**: Build optimized `# ...` route cards including DFT functionals (`B3LYP`, `wB97XD`, `M062X`), calculation job types (`opt`, `freq`, `sp`, `td`), and memory/processor Link 0 commands (`%mem`, `%nprocshared`, `%chk`).
4. **Basis Set Exchange (BSE)**: Search and retrieve standard basis sets (e.g., Pople `6-31G(d,p)`, Karlsruhe `def2-SVP`, Dunning `cc-pVDZ`, effective core potentials `LANL2DZ`).

---

## MCP Server Connection

This skill connects to the local **Gaussian Computational Chemistry MCP Server**.

### Setup Instructions

1. Ensure Python >= 3.10 is installed with required packages:
   ```bash
   pip install -r requirements-mcp.txt
   ```
2. Configure your Agent's MCP settings using the provided template in `templates/mcp-config.json`.

#### Example Claude Code Configuration (`claude.json`):
```json
{
  "mcpServers": {
    "gaussian": {
      "command": "python",
      "args": ["<PATH_TO_GAUSSIAN_MCP_SERVER>/mcp_server.py"],
      "env": {
        "GAUSSIAN_WORK_DIR": "<PATH_TO_YOUR_CALCULATION_DIRECTORY>"
      }
    }
  }
}
```

#### Example Codex CLI Registration:
```bash
codex mcp add gaussian -- python <PATH_TO_GAUSSIAN_MCP_SERVER>/mcp_server.py
```

---

## Software License & Compliance Notice

> **Gaussian Software License Compliance**:
> This skill and its companion MCP server are automation wrappers and file parsers. They **DO NOT** bundle, distribute, or license Gaussian 16 binaries (`g16.exe`, `formchk.exe`). Users must possess a valid, legal commercial/academic license from **Gaussian, Inc.** to execute calculations.

---

## Fallback Workflow (When MCP Server is Unavailable)

If the MCP Server is not connected or tools are unavailable:
1. The Agent should refer directly to the bundled reference guides (`references/route-keywords-guide.md`).
2. Guide the user through manual assembly of Cartesian coordinates, Link 0 directives, and route cards directly in the chat.
3. Recommend cloning `https://github.com/yangdw2024/gaussian-dsh-plugin` to enable full MCP automation.

---

## Agent Workflow Instructions

When the user asks to prepare a Gaussian calculation:

1. **Check System Readiness**:
   Call `gaussian_status()` to inspect working directories, memory allocation, and CPU quotas.
2. **Search Guidelines or Keywords (if needed)**:
   If the functional or keywords are unfamiliar, invoke `search_gaussian_keywords(query="...")` to verify syntax and best practices.
3. **Generate Structure**:
   - If starting from SMILES, call `generate_gaussian_input_from_smiles(smiles="...", job_type="opt", method="B3LYP", basis="6-31G(d,p)")`.
   - If starting from coordinates, call `generate_gaussian_input(job_name="...", atoms=[[...]], ...)`.
4. **Review & Confirm**:
   Present the resulting `.gjf` route line, molecular charge, multiplicity, and saved file path to the user before submitting for execution.
