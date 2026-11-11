#!/usr/bin/env python3
"""Standalone Multiwfn 3.8 + VMD headless recipe generator & cube grid memory guard.

Stdlib-only helper bundled with gaussian-postprocessing skill so users can prepare
safe Multiwfn batch inputs and VMD TCL scripts even without a running MCP server.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict

MAX_GRID_POINTS = 16_000_000
GRID_PRESETS: Dict[str, Dict[str, Any]] = {
    "coarse": {"multiwfn_grid_code": 1, "est_points_per_axis": 80, "est_total_points": 512_000, "note": "Fast preview (<1M grid points)"},
    "medium": {"multiwfn_grid_code": 2, "est_points_per_axis": 150, "est_total_points": 3_375_000, "note": "Publication draft balanced resolution"},
    "fine": {"multiwfn_grid_code": 3, "est_points_per_axis": 240, "est_total_points": 13_824_000, "note": "High-resolution cube near 16M cap"},
}


def check_cube_grid(nx: int, ny: int, nz: int, max_points: int = MAX_GRID_POINTS) -> Dict[str, Any]:
    if nx <= 0 or ny <= 0 or nz <= 0:
        raise ValueError(f"Grid dimensions must be positive integers, got ({nx}, {ny}, {nz})")
    total = nx * ny * nz
    est_cube_mb = round((total * 14.0) / (1024 * 1024), 2)
    within = total <= max_points
    return {
        "nx": nx,
        "ny": ny,
        "nz": nz,
        "total_points": total,
        "max_grid_points": max_points,
        "within_limit": within,
        "estimated_ascii_cube_mb": est_cube_mb,
        "recommendation": "Safe to generate cube and render in VMD."
        if within
        else f"Exceeds {max_points:,} grid-point safety budget; switch to medium/coarse grid to avoid OOM/Multiwfn hang.",
    }


def generate_multiwfn_input(kind: str, grid: str = "medium", mo_index: str = "h") -> str:
    g = GRID_PRESETS[grid]["multiwfn_grid_code"]
    if kind == "orbitals":
        return "\n".join(["200", "3", str(mo_index), str(g), "2", "0", "q", ""])
    if kind == "esp":
        return "\n".join(["5", "12", str(g), "2", "1", str(g), "2", "0", "q", ""])
    if kind == "rdg":
        return "\n".join(["20", "1", str(g), "3", "0", "q", ""])
    if kind == "mo_levels":
        return "\n".join(["0", "q", ""])
    raise ValueError(f"Unsupported postprocess kind: {kind!r}")


def generate_vmd_tcl(kind: str, stem: str, out_prefix: str) -> str:
    if kind == "orbitals":
        return f"""# Headless VMD script for MO orbital rendering ({stem})
mol new {stem}.cub type cube waitfor all
mol delrep 0 top
mol representation CPK 0.45 0.15 24 24
mol color Name
mol addrep top
mol representation Isosurface 0.030 0 0 0 1 1
mol color ColorID 0
mol addrep top
mol representation Isosurface -0.030 0 0 0 1 1
mol color ColorID 1
mol addrep top
display projection Orthographic
axes location Off
color Display Background white
render TachyonInternal {out_prefix}.tga
quit
"""
    if kind == "esp":
        return f"""# Headless VMD script for Electrostatic Potential (ESP) mapped density
mol new density.cub type cube waitfor all
mol addfile totesp.cub type cube waitfor all
mol delrep 0 top
mol representation Isosurface 0.001 0 0 0 1 1
mol color Volume 1
mol scaleminmax top 1 -0.05 0.05
mol addrep top
display projection Orthographic
axes location Off
color Display Background white
render TachyonInternal {out_prefix}.tga
quit
"""
    if kind == "rdg":
        return f"""# Headless VMD script for RDG / NCI non-covalent interaction isosurfaces
mol new func1.cub type cube waitfor all
mol addfile func2.cub type cube waitfor all
mol delrep 0 top
mol representation CPK 0.40 0.15 24 24
mol color Name
mol addrep top
mol representation Isosurface 0.500 1 0 0 1 1
mol color Volume 0
mol scaleminmax top 1 -0.04 0.02
color scale method BGR
mol addrep top
display projection Orthographic
axes location Off
color Display Background white
render TachyonInternal {out_prefix}.tga
quit
"""
    raise ValueError(f"No VMD TCL template defined for kind={kind!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Multiwfn 3.8 + VMD workflow generator & grid budget checker")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_grid = sub.add_parser("check-grid", help="Verify cube grid dimensions against 16M point cap")
    p_grid.add_argument("--nx", type=int, required=True)
    p_grid.add_argument("--ny", type=int, required=True)
    p_grid.add_argument("--nz", type=int, required=True)

    p_rec = sub.add_parser("recipe", help="Print Multiwfn batch input & VMD TCL script")
    p_rec.add_argument("--kind", required=True, choices=("orbitals", "esp", "rdg", "mo_levels"))
    p_rec.add_argument("--grid", default="medium", choices=tuple(GRID_PRESETS))
    p_rec.add_argument("--stem", default="molecule")
    p_rec.add_argument("--mo-index", default="h", help="Multiwfn orbital selector (e.g. h, l, or integer)")
    p_rec.add_argument("--out-dir", help="Optional directory to write multiwfn_input.txt and render.tcl")

    args = parser.parse_args()
    if args.cmd == "check-grid":
        res = check_cube_grid(args.nx, args.ny, args.nz)
        print(json.dumps(res, indent=2))
        return 0 if res["within_limit"] else 2

    if args.cmd == "recipe":
        mw_txt = generate_multiwfn_input(args.kind, grid=args.grid, mo_index=args.mo_index)
        tcl_txt = "" if args.kind == "mo_levels" else generate_vmd_tcl(args.kind, args.stem, f"{args.stem}_{args.kind}")
        payload = {
            "kind": args.kind,
            "grid": args.grid,
            "grid_spec": GRID_PRESETS[args.grid],
            "multiwfn_input": mw_txt,
            "vmd_tcl": tcl_txt or None,
        }
        if args.out_dir:
            od = Path(args.out_dir)
            od.mkdir(parents=True, exist_ok=True)
            (od / "multiwfn_input.txt").write_text(mw_txt, encoding="utf-8", newline="\n")
            if tcl_txt:
                (od / "render.tcl").write_text(tcl_txt, encoding="utf-8", newline="\n")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
