---
name: gaussian-job-setup
description: Prepare, validate, and optimize Gaussian 16 computational chemistry input files (.gjf) for SP, Opt+Freq, TS, IRC, TD-DFT, NMR, and implicit solvent workflows. Includes standalone stdlib Python tooling plus optional local MCP integration.
version: 0.3.0
license: MIT
homepage: https://github.com/yangdw2024/gaussian-dsh-plugin
---

# Gaussian Job Setup Skill

Build reproducible, syntactically valid, resource-safe Gaussian 16 input (`.gjf`) files from SMILES, `.xyz` geometries, or computational requirements — working **both standalone (no MCP server required)** and **optionally connected to your local `gaussian-dsh-plugin` MCP server**.

## Execution Modes

### Mode A: Standalone (No MCP Server Required)
Use the bundled zero-dependency Python helper `scripts/gjf_helper.py` alongside `references/route-keywords-guide.md`:

- Convert an `.xyz` coordinate file into a formatted `.gjf`:
  ```bash
  python scripts/gjf_helper.py xyz-to-gjf molecule.xyz -o molecule_opt.gjf --method B3LYP --basis "6-31G(d,p)" --dispersion GD3BJ --solvent water --job-type opt_freq --mem 8GB --nproc 4
  ```
- Validate an existing `.gjf` (checks Link0 formatting, path traversal in `%chk`, section blank lines, charge/multiplicity electron parity, and trailing EOF blank line):
  ```bash
  python scripts/gjf_helper.py validate molecule_opt.gjf
  ```
- List built-in presets (`sp`, `opt`, `freq`, `opt_freq`, `ts`, `irc_forward`, `irc_reverse`, `td`, `nmr`):
  ```bash
  python scripts/gjf_helper.py presets
  ```

### Mode B: Local MCP Integration (Optional)
If running inside a desktop/CLI agent (Claude Desktop, Codex CLI, Cursor) with the open-source `gaussian-dsh-plugin` backend installed locally (see `templates/mcp-config.json`):
1. `smiles_to_3d` / `generate_gaussian_input` for RDKit ETKDGv3 3D conformer generation and safe sandboxed `.gjf` creation.
2. `get_basis_set` / `list_basis_sets` for Basis Set Exchange (BSE) `Gen` / `GenECP` pseudopotential blocks (e.g., `SDD` / `Def2-TZVP` on transition metals).
3. `gaussian_keywords` for curated DFT functional, dispersion, solvation, and convergence keyword lookup.

> **Important Security Boundary**: Input generation does **not** invoke Gaussian 16 automatically. Keep `GAUSSIAN_ALLOW_REAL_EXECUTION=false` unless explicitly running an out-of-band human-authorized calculation on your own licensed workstation.

## Core Design Rules for Gaussian Inputs

1. **Always check spin & electron parity**: Closed-shell molecules require singlet (`mult=1`) and even electron count; radicals require open-shell multiplicity matching unpaired electrons (`2S+1`).
2. **Verify Link0 structure**: Place `%mem`, `%nprocshared`, and filename-only `%chk` before `#p`; avoid shared `%chk` directory paths (`../` or `/`).
3. **Include trailing blank line**: Gaussian terminates with an unexpected EOF if the last geometry block lacks a blank trailing line.
4. **Match method to chemical question**:
   - Organic ground-state geometry/thermochemistry: `B3LYP/6-31G(d,p) EmpiricalDispersion=GD3BJ opt freq` (verify zero imaginary frequencies).
   - Transition state search: `opt=(calcfc,ts,noeigen) freq` (verify strictly **1** imaginary frequency along the reaction coordinate, then follow with `irc=(calcfc,forward)` and `reverse`).
   - UV-Vis excitation: `td=(nstates=6..20)` using CAM-B3LYP / wB97XD for charge-transfer states.
   - Heavy transition metals / Lanthanides: Use `Gen` or `GenECP` with ECP basis (`SDD`, `LanL2DZ`, `def2-TZVP`).

## Bundled Files

- `SKILL.md` — Workflow rules and standalone + MCP usage guide
- `scripts/gjf_helper.py` — Zero-dependency `.xyz -> .gjf` builder, safety/parity validator, and keyword preset CLI
- `references/route-keywords-guide.md` — Functional, basis set, dispersion, solvation, and transition-state keyword cheat sheet
- `templates/mcp-config.json` — Local stdio MCP template referencing `<PATH_TO_REPO>/mcp_server.py`
