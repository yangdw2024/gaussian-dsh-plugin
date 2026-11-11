---
name: gaussian-output-analysis
description: Parse Gaussian 16 .log/.out calculations (SCF/TD-DFT energies, HOMO-LUMO gap, optimization convergence, imaginary frequencies, ZPE/Gibbs thermochemistry) and diagnose Link errors (l9999, l502, l301, l103, l913). Includes standalone stdlib Python analyzer plus optional local MCP tools.
version: 0.3.0
license: MIT
homepage: https://github.com/yangdw2024/gaussian-dsh-plugin
---

# Gaussian Output Analysis Skill

Inspect Gaussian 16 output files cleanly, verify genuine stationary points and thermochemical data, distinguish multi-step `--Link1--` partial failures from true completions, and turn cryptic Link errors into actionable fixes — **standalone via Python stdlib OR connected to your local MCP server**.

## Execution Modes

### Mode A: Standalone (No MCP Server Required)
Run the zero-dependency analyzer `scripts/log_analyzer.py` on any `.log` / `.out` file and consult `references/error-diagnostics-guide.md`:

- Structured JSON report:
  ```bash
  python scripts/log_analyzer.py molecule_opt.log --format json
  ```
- Human-readable Markdown summary:
  ```bash
  python scripts/log_analyzer.py molecule_opt.log --format markdown
  ```
*(Exit code `0` on Normal termination across all route steps, `2` on abnormal termination or incomplete multi-step job.)*

### Mode B: Local MCP Integration (Optional)
Connect your desktop/CLI client to your local `gaussian-dsh-plugin` MCP server using `templates/mcp-config.json`:
1. `parse_gaussian_output` — Extracts full structured energetics, orbital gaps, frequencies, thermochemistry, and multi-step `--Link1--` health.
2. `diagnose_gaussian_error` — Combines log traceback detection with fix strategies.
3. `gaussian_calc_history` / `extract_structure_from_file` — Inspect prior runs and extract final optimized SMILES/XYZ geometry via OpenBabel.

## Scientific Verification Checklist

1. **Confirm complete termination**: Look for `Normal termination of Gaussian` matching every `--Link1--` step (one `Normal termination` in a 2-step job means step 2 crashed!).
2. **Verify stationary point character**:
   - **Ground-state minimum**: `0` imaginary frequencies.
   - **Transition state (TS)**: Strictly `1` imaginary frequency, visually verified along the reaction bond vector.
3. **Keep KS/HF gap and TD-DFT excitations distinct**: `homo_lumo_gap_ev` is a single-particle ground-state orbital difference, **not** the TD-DFT vertical optical absorption energy (`Excited State ... eV`).
4. **Never report mock/placeholder numbers as real Gaussian outputs**: Verify `energy_source` (`gaussian16_log`) and unit conversions (`1 Hartree = 27.211386 eV = 627.509474 kcal/mol`).

## Bundled Files

- `SKILL.md` — Output verification checklist & standalone/MCP instructions
- `scripts/log_analyzer.py` — Zero-dependency `.log`/`.out` parser & Link-error advisor
- `references/error-diagnostics-guide.md` — Recovery cookbook for `l9999`, `l502`, `l301`, `l103`, `l913`, and disk/memory crashes
- `templates/mcp-config.json` — Local stdio MCP template referencing `<PATH_TO_REPO>/mcp_server.py`
