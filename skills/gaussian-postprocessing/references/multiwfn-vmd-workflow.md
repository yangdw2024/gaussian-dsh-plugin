# Multiwfn 3.8 + VMD Wavefunction & Visualization Workflow

## 1. End-to-End Pipeline

```text
job.chk ─▶ formchk job.chk job.fchk ─▶ Multiwfn job.fchk < multiwfn_input.txt ─▶ .cub files ─▶ vmd -dispdev text -e render.tcl ─▶ .tga ─▶ .png
```

1. **Always include `%chk=<basename>.chk`** in the `.gjf` input so Gaussian preserves molecular orbitals and density matrices.
2. **Convert `.chk` to formatted `.fchk`** using the matching `formchk` binary from the same Gaussian installation (`formchk job.chk job.fchk`).
3. **Budget grid resolution before writing `.cub` files**:
   - `coarse` (Multiwfn grid `1`, ~80^3 ≈ 0.5M pts): Rapid checks (< 5 seconds).
   - `medium` (Multiwfn grid `2`, ~150^3 ≈ 3.4M pts): Balanced interactive analysis.
   - `fine` (Multiwfn grid `3`, ~240^3 ≈ 13.8M pts): Publication quality, close to `16,000,000` grid-point cap.
   - **Never exceed `16,000,000` total grid points** (`nx * ny * nz <= 16000000`) to prevent multi-GB ASCII `.cub` exhaustion and VMD freezes.

## 2. Property Recipes

- **Molecular Orbitals (`orbitals`, HOMO/LUMO)**:
  - Positive lobe isovalue `+0.030`, negative lobe `-0.030` in VMD Isosurface representation (`Orthographic` projection, white background).
  - Remember: Ground-state KS/HF HOMO-LUMO gap (`eV`) is **not** equal to TD-DFT vertical optical absorption gap.
- **Electrostatic Potential (`esp`)**:
  - Map `totesp.cub` (`Volume 1`) onto the `0.001 a.u.` electron density isosurface (`density.cub`), typical range `-0.05` to `+0.05 a.u.`.
- **Non-Covalent Interactions / RDG (`rdg`)**:
  - Map `sign(lambda2)*rho` (`func1.cub`) onto RDG = `0.50` isosurface (`func2.cub`) using BGR color scale (`-0.04` to `+0.02 a.u.`):
    - Blue = strongly attractive (hydrogen bond, halogen bond)
    - Green = weak van der Waals dispersion
    - Red = steric repulsion

## 3. Security & Cleanup Rules

- Clean temporary `.tga` intermediates after converting to `.png` so work directories remain compact.
- Multiwfn and VMD are third-party software packages licensed separately by their respective authors; ensure your workstation paths (`MULTIWFN_EXE`, `VMD_EXE`, `FORMCHK_EXE`) are configured cleanly without exposing credentials or local private directory trees in shared configs.
