# Gaussian Error Diagnostics & Recovery Solutions

## 1. Convergence Failure in SCF
- **Symptom**: `Convergence failure -- run terminated.`
- **Remedies**:
  1. Add `scf=xqc` to switch automatically to quadratic convergence when conventional DIIS fails.
  2. Increase iteration limit: `scf=(maxcycle=200,xqc)`.
  3. Read initial guess from smaller basis checkpoint: `guess=read`.
  4. Pre-optimize at lower level of theory (e.g., HF/STO-3G or B3LYP/6-31G).

## 2. Optimization Not Converging / Oscillating
- **Symptom**: `Error termination in l101.exe` or `Maximum number of optimization cycles reached`.
- **Remedies**:
  1. Switch algorithm: `opt=gdiis` (useful for floppy systems).
  2. Recalculate force constants: `opt=calcfc` or `opt=recalc=5`.
  3. Relax convergence criteria: `opt=loose` for preliminary structures.

## 3. Out of Memory / 内存超限
- **Symptom**: `Out-of-memory / allocation failure` or `Erroneous write. Out of disk space`.
- **Remedies**:
  1. Lower `%mem`: Ensure `%mem` is strictly less than available physical RAM (e.g. 70-80% of total RAM).
  2. Reduce `%nprocshared`.
  3. Avoid `opt=calcall` for large systems (>50 atoms).
  4. Specify scratch directory with ample SSD disk space: `%rwf=D:\scratch\temp.rwf`.

## 4. Multiplicity & Charge Inconsistency
- **Symptom**: `The combination of multiplicity and charge is inconsistent with the number of electrons`.
- **Remedies**:
  1. Total electrons = sum(atomic numbers) - charge.
  2. If total electrons is even: multiplicity must be odd (1, 3, 5...).
  3. If total electrons is odd: multiplicity must be even (2, 4, 6...).
