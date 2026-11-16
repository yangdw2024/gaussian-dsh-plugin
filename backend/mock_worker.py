"""Mock Gaussian 16 Worker Subprocess for safe testing and simulation.

Emulates g16.exe process behavior:
- Reads input GJF.
- Simulates computation latency (default: 0.5s - 2.0s).
- Streams Gaussian-format log output with UNMISTAKABLE [MOCK_GAUSSIAN_SIMULATION]
  banners so simulated energies can NEVER be mistaken for real Gaussian results.
- Emulates normal termination or simulated SCF convergence failure.
- Responds to OS process signals (taskkill/SIGTERM) for cancellation tests.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path

SIMULATION_BANNER = (
    " ==========================================================================\n"
    " [MOCK_GAUSSIAN_SIMULATION] SYNTHETIC OUTPUT FOR AUTOMATED TESTING ONLY\n"
    " Engine: backend.mock_worker (NOT real Gaussian 16 / g16.exe)\n"
    " WARNING: All energies, orbitals, and properties below are synthetic!\n"
    "          MUST NOT be reported as real quantum chemistry results.\n"
    " ==========================================================================\n"
)


def run_mock(
    gjf_path: Path,
    log_path: Path,
    fail_scf: bool = False,
    duration: float = 0.5,
    steps: int = 3,
):
    gjf_text = gjf_path.read_text(encoding="utf-8", errors="ignore")
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Extract method, basis, charge, multiplicity
    route_match = re.search(r"#\s*([^\n]+)", gjf_text)
    route = route_match.group(1).strip() if route_match else "B3LYP/6-31G(d) opt"

    cm_match = re.search(r"(\n\s*(-?\d+)\s+(\d+)\s*\n)", gjf_text)
    charge = cm_match.group(2) if cm_match else "0"
    mult = cm_match.group(3) if cm_match else "1"

    # Start writing log output with prominent simulation markers
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(SIMULATION_BANNER)
        f.write(f" Entering Link 1 = MOCK_WORKER_SIMULATION PID= {os.getpid():>8}.\n")
        f.write(" ******************************************\n")
        f.write(" MOCK_GAUSSIAN_SIMULATION: Synthetic Emulation Mode (NO g16.exe)\n")
        f.write(" ******************************************\n")
        f.write(f" # {route}\n\n")
        f.write(f" Charge = {charge} Multiplicity = {mult}\n\n")
        f.flush()

        step_delay = duration / max(1, steps)
        for s in range(1, steps + 1):
            time.sleep(step_delay)
            energy = -76.4000 - (0.005 * s)
            f.write(f" Optimization cycle   {s} [SIMULATED]\n")
            f.write(f" SCF Done:  E(RB3LYP) =  {energy:.7f}     A.U. after    6 cycles  [MOCK_SIMULATED_ENERGY]\n")
            f.write(" Item               Value     Threshold  Converged?\n")
            f.write(f" Maximum Force            0.0000{max(1, 4-s)}0     0.000450     YES\n")
            f.flush()

        if fail_scf:
            f.write("\n [MOCK_SIMULATED_FAILURE] Convergence failure -- run terminated.\n")
            f.write(" Error termination via Lnk1e in mock_l502.exe (SIMULATED SCF FAILURE)\n")
            f.flush()
            sys.exit(1)

        f.write("\n Stationary point found. [MOCK_SIMULATION]\n")
        f.write(" Alpha  occ. eigenvalues --   -0.50123   -0.45012   -0.34567\n")
        f.write(" Alpha virt. eigenvalues --    0.08920    0.15430\n")
        f.write(" Dipole moment (field-independent basis, Debye) [MOCK_SIMULATED]:\n")
        f.write("    X=     0.0000    Y=     0.0000    Z=     1.8500  Tot=     1.8500\n")
        f.write(f" Job cpu time:       0 days  0 hours  0 minutes  {duration:.1f} seconds.\n")
        f.write(" Normal termination of Gaussian 16 (MOCK_GAUSSIAN_SIMULATION) at simulated clock.\n")
        f.write(SIMULATION_BANNER)
        f.flush()


def main():
    parser = argparse.ArgumentParser(description="Mock Gaussian 16 Subprocess (Simulation Only)")
    parser.add_argument("gjf", type=Path, help="Input GJF file path")
    parser.add_argument("log", type=Path, help="Output LOG file path")
    parser.add_argument("--fail-scf", action="store_true", help="Simulate SCF convergence failure")
    parser.add_argument("--duration", type=float, default=0.5, help="Simulation sleep duration in seconds")
    parser.add_argument("--steps", type=int, default=3, help="Optimization steps to log")
    args = parser.parse_args()

    run_mock(
        gjf_path=args.gjf,
        log_path=args.log,
        fail_scf=args.fail_scf,
        duration=args.duration,
        steps=args.steps,
    )


if __name__ == "__main__":
    main()
