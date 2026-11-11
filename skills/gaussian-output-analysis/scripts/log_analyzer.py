#!/usr/bin/env python3
"""Standalone Gaussian 16 .log/.out parser & error diagnostics CLI.

Stdlib-only CLI bundled with the gaussian-output-analysis skill so it runs
offline without external dependencies or a hosted MCP server.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

HARTREE_TO_EV = 27.211386245988
HARTREE_TO_KCAL = 627.5094740631

DIAG_RULES = [
    ("l9999", re.compile(r"Error termination via Lnk1e.*l9999|galloc.*not enough|Opt.*exceeded", re.I),
     "Geometry optimization exceeded max steps",
     "Inspect last geometry & Max Force/Disp trend; increase opt=(maxcycles=200), tighten StepSize, or add opt=(calcfc,Cartesian)."),
    ("l502", re.compile(r"Error termination.*l502|Convergence failure -- run terminated", re.I),
     "SCF wavefunction convergence failure",
     "Switch to scf=(xqc,maxcycle=256) or scf=(yqc,vshift=300), verify spin multiplicity/charge, or use stable=opt."),
    ("l301", re.compile(r"Standard basis .* unknown|Basis set data is not available|l301\.exe", re.I),
     "Basis set specification or GenECP block error",
     "Verify Gen/GenECP atom element termination line ('****' after every block and ECP block at end with trailing blank line)."),
    ("l103", re.compile(r"Error termination.*l103|FormBX had a problem|NTrRot", re.I),
     "Internal redundant coordinate transformation failure",
     "Use opt=Cartesian or tweak close/linear bond angles; check overlapping atoms or near-180-deg dihedrals."),
    ("l913", re.compile(r"Error termination.*l913|Insufficient memory.*l913", re.I),
     "Post-SCF / TD-DFT amplitude or memory limit failure",
     "Increase %mem= (below physical RAM), reduce td=(nstates=...), or restart from converged SCF guess=read."),
    ("disk_or_mem", re.compile(r"Erroneous write|Disk quota exceeded|Out of memory|malloc failed", re.I),
     "Disk quota or RAM allocation exceeded",
     "Lower %mem to <=75% physical RAM, prune large .rwf intermediates with %nosave, or check scratch disk space."),
]

SCF_RE = re.compile(r"SCF Done:\s+E\(([^)]+)\)\s*=\s*([-\d.]+)")
ROUTE_LINE_RE = re.compile(r"^\s*(#[pPtTnN]?\s+\S.*)$", re.MULTILINE)
LINK1_RE = re.compile(r"Initial command:.*l1\.exe", re.MULTILINE)
CHARGE_MULT_RE = re.compile(r"Charge\s*=\s*(-?\d+)\s+Multiplicity\s*=\s*(\d+)")
ALPHA_OCC_RE = re.compile(r"^\s*Alpha\s+occ\.\s+eigenvalues\s+--(.*)$", re.MULTILINE)
ALPHA_VIRT_RE = re.compile(r"^\s*Alpha\s+virt\.\s+eigenvalues\s+--(.*)$", re.MULTILINE)
FLOAT_RE = re.compile(r"-?\d+\.\d+")
OPT_CONV_RE = re.compile(r"Optimization completed\.")
TD_RE = re.compile(r"Excited State\s+(\d+):\s+(\S+)\s+([-\d.]+)\s+eV\s+([\d.]+)\s+nm\s+f=([\d.]+)")
FREQ_BLOCK_RE = re.compile(r"Frequencies\s+--\s+(.*)")
ZPE_RE = re.compile(r"Zero-point correction=\s*([-\d.]+)")
THERM_H_RE = re.compile(r"Sum of electronic and thermal Enthalpies=\s*([-\d.]+)")
THERM_G_RE = re.compile(r"Sum of electronic and thermal Free Energies=\s*([-\d.]+)")
DIPOLE_RE = re.compile(r"Tot=\s*([\d.]+)")
CPU_RE = re.compile(r"Job cpu time:\s*(.+)")
WALL_RE = re.compile(r"Elapsed time:\s*(.+)")


def analyze_log(text: str, filename: str = "output.log") -> Dict[str, Any]:
    norm_count = len(re.findall(r"Normal termination of Gaussian", text))
    err_match = re.search(r"Error termination via Lnk1e in .*?(l\d+\.exe)", text)
    routes = ROUTE_LINE_RE.findall(text)
    link1_count = max(len(LINK1_RE.findall(text)), 1 if routes else 0)
    route_steps = max(link1_count, len(routes), 1) if (routes or norm_count) else 1

    # Detect multi-step logs where step 1 passed but step 2 crashed
    incomplete_multistep = False
    if err_match:
        normal_termination = False
    elif route_steps > 1 and norm_count < route_steps:
        normal_termination = False
        incomplete_multistep = True
    else:
        normal_termination = norm_count > 0

    scf_matches = SCF_RE.findall(text)
    energy_method, scf_str = scf_matches[-1] if scf_matches else (None, None)
    scf_energy = float(scf_str) if scf_str is not None else None

    cm = CHARGE_MULT_RE.search(text)
    charge = int(cm.group(1)) if cm else None
    mult = int(cm.group(2)) if cm else None

    occ_vals: List[float] = []
    for m in ALPHA_OCC_RE.finditer(text):
        occ_vals.extend(float(x) for x in FLOAT_RE.findall(m.group(1)))
    virt_vals: List[float] = []
    for m in ALPHA_VIRT_RE.finditer(text):
        virt_vals.extend(float(x) for x in FLOAT_RE.findall(m.group(1)))

    homo = occ_vals[-1] if occ_vals else None
    lumo = virt_vals[0] if virt_vals else None
    gap_au = (lumo - homo) if (homo is not None and lumo is not None) else None
    gap_ev = (gap_au * HARTREE_TO_EV) if gap_au is not None else None

    freqs: List[float] = []
    for m in FREQ_BLOCK_RE.finditer(text):
        freqs.extend(float(x) for x in FLOAT_RE.findall(m.group(1)))
    imag_freqs = [f for f in freqs if f < 0.0]
    if not freqs:
        stat_char = None
    elif len(imag_freqs) == 0:
        stat_char = "minimum (no imaginary frequencies)"
    elif len(imag_freqs) == 1:
        stat_char = "first_order_saddle_point (1 imaginary frequency - verify eigenvector for TS)"
    else:
        stat_char = f"higher_order_saddle_point ({len(imag_freqs)} imaginary frequencies)"

    zpe_m = ZPE_RE.search(text)
    h_m = THERM_H_RE.search(text)
    g_m = THERM_G_RE.search(text)
    dip_matches = DIPOLE_RE.findall(text)
    cpu_m = CPU_RE.search(text)
    wall_m = WALL_RE.search(text)

    td_states = [
        {"state": int(s), "spin_symmetry": sym, "energy_ev": float(ev), "wavelength_nm": float(nm), "oscillator_strength": float(f)}
        for s, sym, ev, nm, f in TD_RE.findall(text)
    ]

    diagnostics: List[Dict[str, str]] = []
    if not normal_termination:
        for code, pat, summary, fix in DIAG_RULES:
            if pat.search(text):
                diagnostics.append({"code": code, "summary": summary, "recommended_fix": fix})

    return {
        "filename": filename,
        "source_type": "gaussian_log_file",
        "is_simulated": False,
        "normal_termination": normal_termination,
        "incomplete_multistep": incomplete_multistep,
        "route_steps": route_steps,
        "normal_termination_count": norm_count,
        "error_link": err_match.group(1) if err_match else None,
        "routes": routes,
        "charge": charge,
        "multiplicity": mult,
        "energy_method": energy_method,
        "scf_energy_hartree": scf_energy,
        "scf_energy_kcal_mol": round(scf_energy * HARTREE_TO_KCAL, 4) if scf_energy is not None else None,
        "opt_converged": bool(OPT_CONV_RE.search(text)),
        "homo_hartree": homo,
        "lumo_hartree": lumo,
        "homo_lumo_gap_hartree": round(gap_au, 6) if gap_au is not None else None,
        "homo_lumo_gap_ev": round(gap_ev, 4) if gap_ev is not None else None,
        "frequency_count": len(freqs),
        "imaginary_frequencies_cm_1": imag_freqs,
        "stationary_point_character": stat_char,
        "zero_point_correction_hartree": float(zpe_m.group(1)) if zpe_m else None,
        "thermal_enthalpy_hartree": float(h_m.group(1)) if h_m else None,
        "thermal_free_energy_hartree": float(g_m.group(1)) if g_m else None,
        "dipole_moment_debye": float(dip_matches[-1]) if dip_matches else None,
        "excited_states": td_states[:10],
        "cpu_time": cpu_m.group(1).strip() if cpu_m else None,
        "wall_time": wall_m.group(1).strip() if wall_m else None,
        "diagnostics": diagnostics,
        "scientific_caveats": [
            "KS/HF HOMO-LUMO orbital gap is a ground-state single-particle gap and does not equal TD-DFT optical excitation energy.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Standalone Gaussian .log/.out scientific parser & error advisor")
    parser.add_argument("log_file", help="Path to Gaussian .log or .out file")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args()

    p = Path(args.log_file)
    data = analyze_log(p.read_text(encoding="utf-8", errors="replace"), filename=p.name)
    if args.format == "json":
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(f"# Gaussian Analysis: {data['filename']}")
        print(f"- **Termination**: {'NORMAL' if data['normal_termination'] else 'ABNORMAL'} (steps={data['route_steps']}, ok={data['normal_termination_count']})")
        if data["scf_energy_hartree"] is not None:
            print(f"- **SCF Energy** ({data['energy_method']}): `{data['scf_energy_hartree']}` Hartree")
        if data["homo_lumo_gap_ev"] is not None:
            print(f"- **KS/HF HOMO-LUMO Gap**: `{data['homo_lumo_gap_ev']}` eV (`{data['homo_lumo_gap_hartree']}` Hartree)")
        if data["stationary_point_character"]:
            print(f"- **Stationary Point**: {data['stationary_point_character']} (freqs={data['frequency_count']})")
        if data["diagnostics"]:
            print("\n## Diagnostics")
            for d in data["diagnostics"]:
                print(f"- `{d['code']}`: {d['summary']} — **Fix**: {d['recommended_fix']}")
    return 0 if data["normal_termination"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
