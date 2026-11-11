---
name: gaussian-output-analysis
description: Scientific analysis skill for parsing Gaussian 16 calculation logs (.log/.out), extracting electronic energies, thermochemistry, HOMO-LUMO band gaps, dipole moments, and diagnosing calculation errors with actionable remedies.
version: 1.0.0
author: yangdw
tags:
  - computational-chemistry
  - gaussian
  - log-parser
  - error-diagnosis
  - mcp
---

# Gaussian Output Analysis Skill

This skill enables AI Agents to parse raw Gaussian 16 calculation outputs (`.log` or `.out`), verify convergence criteria, extract critical physical and chemical metrics, and diagnose termination failures.

## Capabilities

1. **Output Parsing**:
   - Extract electronic energy in atomic units (Hartree / a.u.) across DFT, HF, MP2, and CCSD(T) methods.
   - Verify geometry optimization convergence (`Maximum Force`, `RMS Force`, `Maximum Displacement`, `RMS Displacement`).
   - Extract frontier molecular orbitals: HOMO energy, LUMO energy, and band gap (eV / a.u.).
   - Extract dipole moments (Debye), vibrational frequencies, and imaginary frequencies count.
   - Extract thermochemical corrections: Zero-Point Vibrational Energy (ZPE), thermal enthalpy (H), and Gibbs free energy (G).
2. **Error Diagnosis**:
   - Identify common failure modes: SCF convergence failure, optimization oscillations, memory exhaustion (`Out-of-memory`), missing basis definitions, and linear coordinate angles.
   - Suggest concrete input remedies (e.g. `scf=xqc`, `opt=gdiis`, `%rwf` redirection, `guess=read`).

---

## MCP Server Connection

Ensure your agent is connected to the **Gaussian Computational Chemistry MCP Server** as described in `templates/mcp-config.json`.

---

## Software License & Compliance Notice

> **Gaussian Software License Compliance**:
> This skill and its companion MCP server are automation wrappers and log parsers. They **DO NOT** bundle, distribute, or license Gaussian 16 binaries (`g16.exe`, `formchk.exe`). Users must possess a valid, legal commercial/academic license from **Gaussian, Inc.** to execute calculations.

---

## Fallback Workflow (When MCP Server is Unavailable)

If the MCP Server is not connected or tools are unavailable:
1. The Agent should refer directly to the bundled reference guides (`references/error-diagnostics-guide.md`).
2. Perform manual pattern-matching on the user's uploaded log snippet to identify SCF convergence errors, force oscillations, or link failures.
3. Recommend cloning `https://github.com/yangdw2024/gaussian-dsh-plugin` to enable full automated log parsing.

---

## Agent Workflow Instructions

When the user asks to analyze a Gaussian calculation:

1. **Parse the Calculation Log**:
   - Call `parse_gaussian_output(file_path="...")` or pass the raw log text via `content="..."`.
2. **Evaluate Termination**:
   - If `normal_termination` is `True`, summarize the energy, convergence, HOMO-LUMO gap, and thermochemical corrections into a clean markdown table.
   - If `normal_termination` is `False`, note the reported error message.
3. **Diagnose Failures (if not normal)**:
   - Call `diagnose_gaussian_error(error_text="...", log_tail="...")` to look up root causes and keyword remedies.
   - Present the recommended fix and provide a modified route card for resubmission.
