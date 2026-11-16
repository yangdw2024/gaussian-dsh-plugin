# Gaussian Route Keywords & Job Types Quick Reference

## Standard Calculation Job Types
- `opt`: Geometry optimization using Berny algorithm.
- `freq`: Harmonic vibrational frequency calculation (must be at stationary point).
- `opt freq`: Optimization followed immediately by frequency calculation.
- `sp`: Single point energy calculation (default if no job type specified).
- `td=(nstates=10)`: Time-dependent DFT for electronic excited states and UV-Vis absorption.
- `irc=(rcfc,maxpoints=50)`: Intrinsic Reaction Coordinate path following from transition state.

## Recommended Functionals
- `B3LYP`: Standard hybrid functional for organic molecule ground states.
- `wB97XD`: Range-separated hybrid with empirical dispersion (Grimme D2), superior for non-covalent interactions and charge transfer.
- `M062X`: Minnesota meta-hybrid GGA, recommended for main-group thermochemistry and kinetics. (Requires `int=ultrafine`).
- `PBE0`: Parameter-free hybrid functional, reliable for transition metal complexes and solids.

## Link 0 Directives
- `%mem=12GB`: Total shared physical memory allocated to Gaussian.
- `%nprocshared=8`: Number of CPU cores for shared-memory parallel execution.
- `%chk=filename.chk`: Checkpoint file destination for wavefunctions, densities, and restart.
- `%nosave`: Automatically delete temporary scratch files on normal termination.
