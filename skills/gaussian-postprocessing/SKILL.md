---
name: gaussian-postprocessing
description: Generate safe Multiwfn 3.8 + VMD visualization workflows for Gaussian .chk/.fchk outputs (HOMO/LUMO orbitals, ESP electrostatic potential surfaces, RDG/NCI non-covalent interactions, MO energy levels) with 16M-point cube grid safety limits.
version: 0.3.0
license: MIT
homepage: https://github.com/yangdw2024/gaussian-dsh-plugin
---

# Gaussian Wavefunction & Visualization Postprocessing Skill

Automate reproducible `formchk -> Multiwfn 3.8 -> .cub -> VMD Tachyon -> .png` workflows with strict cube-grid memory protection — working **both standalone (no MCP server required)** and **via your local `gaussian-dsh-plugin` MCP server**.

## Execution Modes

### Mode A: Standalone (No MCP Server Required)
Use the bundled stdlib script `scripts/multiwfn_recipe.py` together with `references/multiwfn-vmd-workflow.md`:

- Validate cube dimensions against the `16,000,000` grid-point safety cap before running Multiwfn or VMD:
  ```bash
  python scripts/multiwfn_recipe.py check-grid --nx 180 --ny 180 --nz 180
  ```
- Generate ready-to-run Multiwfn batch commands (`multiwfn_input.txt`) and headless VMD script (`render.tcl`) for `orbitals`, `esp`, `rdg`, or `mo_levels`:
  ```bash
  python scripts/multiwfn_recipe.py recipe --kind rdg --grid medium --stem complex_opt --out-dir ./post_rdg
  ```

### Mode B: Local MCP Integration (Optional)
With `gaussian-dsh-plugin` MCP running locally (see `templates/mcp-config.json`):
1. `postprocess_capabilities` — Inspect whether `formchk`, `Multiwfn` (`3.8`), and `VMD` binaries are detected and ready.
2. `run_postprocess` — End-to-end automated execution (converts `.chk -> .fchk`, enforces cube `<= 16,000,000` point cap before launching VMD, renders `.png` via Tachyon, and cleans up intermediate `.tga` files).
3. `get_postprocess_task` / `parse_fchk_file` — Inspect task artifacts or read FCHK energies, dipole moments, Mulliken charges, and orbital eigenvalues directly.

## Key Visualization & Safety Rules

1. **Cap Cube Grids at `16,000,000` Points**: Oversized `.cub` grids stall VMD and exhaust host memory; always check `(nx * ny * nz) <= 16,000,000`.
2. **Use `medium` Before `fine`**: Verify orbital phases, ESP scaling (`-0.05` to `+0.05`), or RDG BGR isovalues on `medium` grid first.
3. **Distinguish Third-Party Licenses**: Gaussian/`formchk`, Multiwfn, and VMD are separate third-party tools installed by the user.

## Bundled Files

- `SKILL.md` — Pipeline rules, standalone CLI usage, and MCP workflow
- `scripts/multiwfn_recipe.py` — Zero-dependency Multiwfn/VMD script generator & grid-limit checker
- `references/multiwfn-vmd-workflow.md` — Color scale, isovalue, and grid resolution specifications
- `templates/mcp-config.json` — Local stdio MCP template referencing `<PATH_TO_REPO>/mcp_server.py`
