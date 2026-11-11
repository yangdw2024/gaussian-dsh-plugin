"""Gaussian AI Computational Chemistry — Model Context Protocol (MCP) Server.

Implements the standard MCP interface using the official Python MCP SDK (FastMCP).
Exposes the core computational chemistry capabilities with strict security boundaries,
controlled working directories, and zero stdout pollution for reliable stdio transport.
"""
from __future__ import annotations

import logging
import os
import re
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

# Configure logging strictly to sys.stderr so stdout remains 100% clean for JSON-RPC
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("gaussian-mcp-server")

from mcp.server.fastmcp import FastMCP

from .basis_set import basis_set_client
from .config import SERVICE_VERSION, settings
from .execution_policy import (
    evaluate_real_execution_authorization,
    run_preflight_check,
)
from .gaussian_input import GaussianInputRequest, generate_gjf
from .gaussian_output import output_to_dict, parse_gaussian_log
from .job_manager import job_manager
from .keywords import get_all_categories, get_category, search_keywords
from .memory_guard import memory_guard
from .postprocess.manager import postprocess_manager
from .postprocess.models import PostprocessRequest
from .postprocess.multiwfn import probe_version as mwfn_probe_version
from .resource_scheduler import chem_scheduler
from .security import (
    get_allowed_read_roots,
    get_allowed_write_roots,
    validate_safe_path,
)
from .smiles.models import (
    AmbiguousSpinError,
    DisconnectedMoleculeError,
    MMFFParamError,
    Smiles3DRequest,
)
from .smiles.rdkit_builder import smiles_to_3d
from .sobko_client import sobko_client
from .structure_reader import extract_smiles_from_file

try:
    from .mcp_sobko_ext import register_sobko_tools
except Exception as _sobko_imp_err:
    logger.warning("Failed to import optional Sobko MCP extension: %s", _sobko_imp_err)
    register_sobko_tools = None

# Initialize FastMCP Server instance
mcp = FastMCP(
    name="Gaussian Computational Chemistry Server",
    instructions=(
        "Standard Model Context Protocol server providing Gaussian 16 computational chemistry "
        "workflows: input generation (.gjf), SMILES/structure extraction, output parsing (.log/.out), "
        "error diagnosis, basis sets, serial job control, and Multiwfn/VMD/formchk post-processing."
    ),
)

CORE_TOOL_NAMES = (
    "gaussian_status",
    "generate_gaussian_input",
    "parse_gaussian_output",
    "diagnose_gaussian_error",
    "search_gaussian_keywords",
    "search_basis_sets",
    "get_basis_set",
    "generate_gaussian_input_from_smiles",
    "submit_gaussian_calculation",
    "get_gaussian_job_status",
    "list_gaussian_jobs",
    "stop_gaussian_calculation",
    "extract_structure_from_file",
    "postprocess_capabilities",
    "create_postprocess_task",
    "get_postprocess_task",
    "list_postprocess_tasks",
)

_sobko_ext_state: Dict[str, Any] = {"registered": False, "tools": [], "enabled": False}


# ==============================================================================
# Tool 1: gaussian_status
# ==============================================================================
@mcp.tool()
def gaussian_status() -> Dict[str, Any]:
    """Check Gaussian computational environment, paths, resource budget, and service status.

    Returns:
        Structured JSON dictionary detailing Gaussian 16 executable status, formchk tool,
        working directory, authorized security roots, resource budget (memory and cores),
        knowledge base readiness, and compute scheduler lease status.
    """
    g16_path = Path(settings.gaussian_exe) if settings.gaussian_exe else None
    g16_exists = bool(g16_path and g16_path.exists())

    formchk_path = settings.formchk_exe
    formchk_exists = bool(formchk_path and formchk_path.exists())
    multiwfn_path = settings.multiwfn_exe
    multiwfn_exists = bool(multiwfn_path and Path(multiwfn_path).exists())
    vmd_path = settings.vmd_exe
    vmd_exists = bool(vmd_path and Path(vmd_path).exists())

    sobko_info = sobko_client.is_available()
    lease = chem_scheduler.current_lease()
    read_roots = [str(r) for r in get_allowed_read_roots()]
    write_roots = [str(r) for r in get_allowed_write_roots()]

    return {
        "status": "ok",
        "server_version": SERVICE_VERSION,
        "core_tools_count": len(CORE_TOOL_NAMES),
        "transport": "stdio",
        "gaussian": {
            "exe": str(settings.gaussian_exe),
            "exists": g16_exists,
        },
        "formchk": {
            "exe": str(formchk_path) if formchk_path else None,
            "exists": formchk_exists,
        },
        "postprocess": {
            "formchk_exists": formchk_exists,
            "multiwfn_exists": multiwfn_exists,
            "vmd_exists": vmd_exists,
            "max_grid_points": settings.postprocess_max_grid_points,
        },
        "directories": {
            "work_dir": str(settings.work_dir),
            "data_dir": str(settings.data_dir),
            "allowed_read_roots": read_roots,
            "allowed_write_roots": write_roots,
        },
        "resource_budget": {
            "default_mem": settings.default_mem,
            "default_nproc": settings.default_nproc,
            "max_atoms": settings.max_atoms,
        },
        "sobko_knowledge_base": sobko_info,
        "optional_extensions": {
            "sobko": dict(_sobko_ext_state),
        },
        "active_compute_lease": {
            "held": lease is not None,
            "kind": lease.kind if lease else None,
            "owner_id": lease.owner_id if lease else None,
        },
        "running_job": job_manager.has_running(),
    }


# ==============================================================================
# Tool 2: generate_gaussian_input
# ==============================================================================
@mcp.tool()
def generate_gaussian_input(
    job_name: str = "gaussian_job",
    job_type: str = "opt",
    method: str = "B3LYP",
    basis: str = "6-31G(d,p)",
    charge: int = 0,
    multiplicity: int = 1,
    atoms: Optional[List[List[Any]]] = None,
    mem: Optional[str] = None,
    nproc: Optional[int] = None,
    chk: Optional[str] = None,
    extra_keywords: Optional[List[str]] = None,
    title: Optional[str] = None,
    custom_route: Optional[str] = None,
    append_text: Optional[str] = None,
    save_to_file: bool = True,
    output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate a validated Gaussian (.gjf) input file from molecular coordinates and parameters.

    Parameters:
        job_name: Name of the job, sanitized for safe file naming (default: "gaussian_job").
        job_type: Calculation type: 'sp', 'opt', 'freq', 'opt+freq', 'td', 'irc', 'scan'.
        method: Functional or theoretical method (e.g. B3LYP, wB97XD, M062X, HF, MP2).
        basis: Basis set (e.g. 6-31G(d,p), def2-SVP, cc-pVDZ, 6-311+G(d,p)).
        charge: Total molecular electric charge (integer).
        multiplicity: Spin multiplicity (2S+1: singlet=1, doublet=2, triplet=3).
        atoms: List of Cartesian coordinates in format [[element, x, y, z], ...].
        mem: Memory allocation string (e.g. '8GB', '12GB'). Defaults to configuration.
        nproc: Number of parallel CPU shared cores (e.g. 8). Defaults to configuration.
        chk: Optional checkpoint filename (e.g. 'job.chk').
        extra_keywords: Optional list of additional route keywords (e.g. ['scf=tight', 'empiricaldispersion=gd3bj']).
        title: Optional title text.
        custom_route: Optional custom route line (bypasses method/basis combination).
        append_text: Optional extra block appended after coordinates (for gen basis/ECP/solvent).
        save_to_file: If True, writes the .gjf file to the authorized working directory.
        output_dir: Optional destination directory (must be within authorized boundaries).

    Returns:
        Dict with gjf content, filename, route line, atom count, warnings, and saved_path.
    """
    raw_atoms = atoms or []
    formatted_atoms: List[tuple] = []
    for item in raw_atoms:
        if len(item) >= 4:
            try:
                formatted_atoms.append((str(item[0]), float(item[1]), float(item[2]), float(item[3])))
            except (ValueError, TypeError) as exc:
                raise ValueError(f"Invalid atom coordinate specification: {item}: {exc}")

    # Enforce maximum atoms safety check
    if len(formatted_atoms) > settings.max_atoms:
        raise ValueError(
            f"Molecular system contains {len(formatted_atoms)} atoms, exceeding authorized "
            f"safety threshold of {settings.max_atoms} atoms."
        )

    req = GaussianInputRequest(
        job_name=job_name,
        job_type=job_type,
        method=method,
        basis=basis,
        charge=charge,
        multiplicity=multiplicity,
        atoms=formatted_atoms,
        mem=mem or settings.default_mem,
        nproc=nproc or settings.default_nproc,
        chk=chk,
        extra_keywords=extra_keywords or [],
        title=title,
        custom_route=custom_route,
        append_text=append_text,
    )

    result = generate_gjf(req)

    # Optional safe file write within authorized boundaries (strictly WRITE mode)
    if save_to_file:
        base = validate_safe_path(output_dir or settings.work_dir, mode="write")
        target_file = validate_safe_path(base / result["filename"], mode="write")
        target_file.parent.mkdir(parents=True, exist_ok=True)
        with open(target_file, "w", encoding="utf-8") as f:
            f.write(result["content"])
        result["saved_path"] = str(target_file)
    else:
        result["saved_path"] = None

    return result


# ==============================================================================
# Tool 3: parse_gaussian_output
# ==============================================================================
@mcp.tool()
def parse_gaussian_output(
    file_path: Optional[str] = None,
    content: Optional[str] = None,
    filename: Optional[str] = None,
) -> Dict[str, Any]:
    """Parse a Gaussian .log or .out output file to extract scientific results and convergence diagnostics.

    Parameters:
        file_path: Path to Gaussian log/out file on disk. Path must reside within authorized boundaries.
        content: Raw text content of the Gaussian log file (used if file_path is omitted).
        filename: Optional filename for display purposes.

    Returns:
        Structured scientific results:
        - normal_termination: bool indicating whether calculation terminated normally.
        - error_message: string description if error termination occurred.
        - final_energy: final electronic energy (in a.u. / Hartree), with post-HF / DFT method discrimination.
        - stationary_point: bool indicating whether geometry optimization found a stationary point.
        - opt_converged: bool indicating full convergence of Force and Displacement criteria.
        - opt_steps: total optimization steps taken.
        - homo_energy, lumo_energy, homo_lumo_gap: frontier orbital energies and band gap in a.u.
        - dipole_moment: total molecular dipole moment in Debye.
        - frequencies: vibrational frequencies (cm^-1) and imaginary frequencies count.
        - zero_point_energy, thermal_enthalpy, thermal_free_energy: thermochemical corrections (Hartree).
        - cpu_time, wall_time: computational runtimes.
    """
    text_content = content
    fname = filename or "gaussian.log"

    if not text_content and file_path:
        safe_path = validate_safe_path(file_path, must_exist=True, mode="read")
        fname = safe_path.name
        file_size = safe_path.stat().st_size
        max_bytes = 100 * 1024 * 1024  # 100MB safety threshold
        if file_size > max_bytes:
            raise ValueError(
                f"Log file '{safe_path.name}' size ({file_size / (1024*1024):.1f}MB) exceeds "
                f"safe parsing limit (100MB) to prevent memory exhaustion."
            )
        with open(safe_path, "r", encoding="utf-8", errors="ignore") as f:
            text_content = f.read()

    if not text_content:
        raise ValueError("Must provide either 'file_path' or non-empty 'content'.")

    parsed = parse_gaussian_log(text_content, filename=fname)
    return output_to_dict(parsed)


# ==============================================================================
# Tool 4: diagnose_gaussian_error
# ==============================================================================
@mcp.tool()
def diagnose_gaussian_error(
    error_text: str,
    log_tail: Optional[str] = None,
    query_knowledge_base: bool = False,
) -> Dict[str, Any]:
    """Diagnose Gaussian computational chemistry errors and provide actionable remedies.

    Parameters:
        error_text: Error message extracted from Gaussian output (e.g. 'Convergence failure',
                    'Out-of-memory', 'Error termination in l101.exe', 'Linear angle in Tors').
        log_tail: Optional trailing lines of the log file for additional context.
        query_knowledge_base: If True and local Sobko knowledge base is actively running,
                              queries literature and manual evidence (defaults to False for fast response).

    Returns:
        Structured diagnostic dictionary containing:
        - error_text: original input error text.
        - diagnoses: list of matching built-in solutions (root cause, keyword recommendations, parameter fixes).
        - sobko_evidence: related literature or manual excerpts if local knowledge base is configured.
    """
    if not error_text or not error_text.strip():
        raise ValueError("Parameter 'error_text' must not be empty.")

    combined_text = f"{error_text}\n{log_tail or ''}".lower()
    diagnoses: List[Dict[str, Any]] = []

    # Search built-in curated computational chemistry error rules
    for item in get_category("常见错误与解决方案"):
        raw_kw = item.get("keyword", "").lower()
        desc = item.get("description", "").lower()
        # Match either exact keyword, slash-separated aliases (e.g. "out-of-memory / 内存不足"),
        # or significant tokens from description
        kw_parts = [p.strip() for p in raw_kw.split("/") if p.strip()]
        matched = any(p in combined_text for p in kw_parts) or any(
            w in combined_text for w in desc.split() if len(w) > 3
        )
        if matched:
            diagnoses.append({
                "source": "builtin",
                "error": item.get("keyword"),
                "description": item.get("description"),
                "solution": item.get("usage"),
                "notes": item.get("notes"),
            })

    # Optional Sobko knowledge base query (only if explicitly requested and running)
    sobko_results: List[Dict[str, Any]] = []
    if query_knowledge_base:
        sobko_status = sobko_client.is_available()
        if sobko_status.get("running"):
            try:
                query = f"Gaussian 错误 {error_text[:100]} 解决方案"
                resp = sobko_client.search(query=query, top_k=3)
                if resp.get("ok"):
                    sobko_results = resp.get("results", [])
            except Exception as exc:
                logger.warning("Sobko search query failed: %s", exc)

    return {
        "error_text": error_text,
        "diagnoses": diagnoses,
        "diagnosis_count": len(diagnoses),
        "sobko_evidence": sobko_results,
    }


# ==============================================================================
# Tool 5: search_gaussian_keywords
# ==============================================================================
@mcp.tool()
def search_gaussian_keywords(
    query: str,
    category: Optional[str] = None,
    limit: int = 20,
) -> Dict[str, Any]:
    """Search curated Gaussian 16 keywords, functionals, job types, SCF controls, and diagnostics.

    Parameters:
        query: Search string (keyword name, description term, or syntax).
        category: Optional category filter (e.g. '任务类型', '方法与泛函', 'SCF 控制', '色散与格点', '溶剂模型', '波函数与布居', '常见错误与解决方案').
        limit: Maximum number of results to return (default: 20, max: 50).

    Returns:
        Structured dictionary containing:
        - query: Original query string.
        - count: Total matching results.
        - results: List of keyword records with keyword, description, usage, notes, category, and score.
        - available_categories: Full list of supported keyword categories.
    """
    limit = min(max(1, limit), 50)
    all_categories = get_all_categories()

    if category and category not in all_categories:
        valid_cats = ", ".join(all_categories)
        raise ValueError(f"Unknown category '{category}'. Available categories: {valid_cats}")

    raw_results = search_keywords(query=query, limit=limit)
    if category:
        raw_results = [r for r in raw_results if r.get("category") == category]

    return {
        "query": query,
        "category_filter": category,
        "count": len(raw_results),
        "results": raw_results,
        "available_categories": all_categories,
    }


# ==============================================================================
# Tool 6: search_basis_sets
# ==============================================================================
@mcp.tool()
def search_basis_sets(
    query: str,
    family: Optional[str] = None,
    elements: Optional[List[int]] = None,
    limit: int = 20,
) -> Dict[str, Any]:
    """Search the Basis Set Exchange (BSE) library for Gaussian-compatible basis sets.

    Features fast local cache and offline fallback. Supports filtering by family (e.g. 'pople',
    'ahlrichs', 'dunning', 'lanl') and supported atomic numbers.

    Parameters:
        query: Search query string (e.g. '6-31g', 'def2-svp', 'cc-pvdz', 'lanl2dz', 'm06').
        family: Optional basis set family filter ('pople', 'ahlrichs', 'dunning', 'lanl').
        elements: Optional list of required atomic numbers that the basis set must support (e.g. [1, 6, 8, 26]).
        limit: Maximum number of results to return (default: 20, max: 50).

    Returns:
        Structured dictionary containing query, count, and basis_sets records.
    """
    limit = min(max(1, limit), 50)
    q = (query or "").strip()

    if q:
        results = basis_set_client.search(q, limit=limit)
        if family:
            results = [b for b in results if b.get("family", "").lower() == family.lower()]
        if elements:
            results = [
                b for b in results
                if all(e in b.get("elements", []) for e in elements)
            ]
    else:
        results = basis_set_client.list_basis_sets(family=family, elements=elements)
        results = results[:limit]

    return {
        "query": query,
        "family_filter": family,
        "elements_filter": elements,
        "count": len(results),
        "basis_sets": results,
    }


# ==============================================================================
# Tool 7: get_basis_set
# ==============================================================================
@mcp.tool()
def get_basis_set(
    name: str,
    elements: List[int],
    format: str = "gaussian94",
    version: Optional[str] = None,
    save_to_file: bool = False,
    output_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Fetch basis set definitions from Basis Set Exchange (BSE) for specified elements.

    Parameters:
        name: Canonical basis set name or slug (e.g. '6-31g*', 'def2-svp', 'cc-pvdz', 'lanl2dz').
        elements: List of element atomic numbers to extract (e.g. [1, 6, 8] for H, C, O).
        format: Format style: 'gaussian94' (default Gaussian format), 'nwchem', 'orca', 'json'.
        version: Optional specific BSE version string (default: latest version).
        save_to_file: If True, saves the downloaded basis set to disk in authorized directory.
        output_path: Optional relative or absolute destination file path (strictly boundary checked).

    Returns:
        Structured dictionary containing ok, name, format, elements, content, and saved_path.
    """
    if not name or not name.strip():
        raise ValueError("Basis set 'name' must not be empty.")
    if not elements:
        raise ValueError("Parameter 'elements' must be a non-empty list of atomic numbers (e.g. [1, 6, 8]).")

    res = basis_set_client.get_basis(name=name.strip(), elements=elements, fmt=format, version=version)
    if not res.get("ok"):
        return res

    saved_file_str: Optional[str] = None
    if save_to_file:
        if output_path:
            target = validate_safe_path(output_path, mode="write")
        else:
            safe_name = name.strip().replace("*", "_st_").replace("/", "_").replace("\\", "_")
            target = validate_safe_path(settings.work_dir / f"{safe_name}.gbs", mode="write")

        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(res["content"])
        saved_file_str = str(target)

    res["saved_path"] = saved_file_str
    return res


# ==============================================================================
# Tool 8: generate_gaussian_input_from_smiles
# ==============================================================================
@mcp.tool()
def generate_gaussian_input_from_smiles(
    smiles: str,
    job_name: str = "smiles_mol",
    job_type: str = "opt",
    method: str = "B3LYP",
    basis: str = "6-31G(d,p)",
    charge: Optional[int] = None,
    multiplicity: Optional[int] = None,
    allow_disconnected: bool = False,
    num_conformers: int = 24,
    max_iterations: int = 500,
    random_seed: int = 42,
    mem: Optional[str] = None,
    nproc: Optional[int] = None,
    chk: Optional[str] = None,
    extra_keywords: Optional[List[str]] = None,
    title: Optional[str] = None,
    save_to_file: bool = True,
    output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate a 3D conformer from a 2D SMILES string and construct a validated Gaussian (.gjf) input file.

    Parameters:
        smiles: Chemical SMILES string (e.g. 'c1ccccc1', 'CCO', 'CC(=O)O').
        job_name: Name of the job, sanitized for filename (default: "smiles_mol").
        job_type: Calculation type: 'opt', 'freq', 'opt+freq', 'sp', 'td'.
        method: Functional or method (e.g. 'B3LYP', 'wB97XD', 'M062X', 'HF').
        basis: Basis set (e.g. '6-31G(d,p)', 'def2-SVP', 'cc-pVDZ').
        charge: Total charge. If omitted, inferred from SMILES formal charge.
        multiplicity: Spin multiplicity (2S+1). If omitted, inferred safely from electron count.
        allow_disconnected: If True, allows multi-fragment molecules (salts, mixtures). Default: False.
        num_conformers: Number of ETKDGv3 conformers to sample (default: 24, max: 50).
        max_iterations: Max MMFF94s optimization iterations per conformer (default: 500).
        random_seed: Random seed for conformer generation reproducibility.
        mem: Memory allocation (e.g. '12GB'). Defaults to configuration.
        nproc: CPU cores (e.g. 8). Defaults to configuration.
        chk: Optional checkpoint filename.
        extra_keywords: Optional extra route keywords (e.g. ['empiricaldispersion=gd3bj']).
        title: Optional title text.
        save_to_file: If True, writes the .gjf file to the authorized working directory.
        output_dir: Optional destination directory within authorized boundaries.

    Returns:
        Dict with gjf content, filename, route line, atom count, atom coordinates, smiles_info, and saved_path.
    """
    if not smiles or not smiles.strip():
        raise ValueError("Parameter 'smiles' must not be empty.")

    # Guard against memory exhaustion
    if not memory_guard.can_accept_compute():
        snap = memory_guard.snapshot()
        raise RuntimeError(
            f"Backend memory threshold reached (RSS {snap['rss_mb']}MB >= {snap['hard_mb']}MB). "
            f"Cannot accept heavy conformer generation at this time."
        )

    # Conformer limit guard
    num_confs = min(max(1, num_conformers), 50)

    # Acquire resource lease for CPU-bound RDKit embedding
    owner = uuid.uuid4().hex[:12]
    chem_scheduler.acquire(owner, "rdkit")
    try:
        req_smiles = Smiles3DRequest(
            smiles=smiles.strip(),
            charge=charge,
            multiplicity=multiplicity,
            allow_disconnected=allow_disconnected,
            num_conformers=num_confs,
            max_iterations=max_iterations,
            random_seed=random_seed,
        )
        mol3d = smiles_to_3d(req_smiles)
    except (ValueError, DisconnectedMoleculeError, AmbiguousSpinError, MMFFParamError) as exc:
        raise ValueError(f"SMILES 3D Conformer Generation Failed: {exc}")
    finally:
        chem_scheduler.release(owner)

    # Format Cartesian coordinates
    formatted_atoms = [(a.element, a.x, a.y, a.z) for a in mol3d.atoms]

    # Atom count boundary check
    if len(formatted_atoms) > settings.max_atoms:
        raise ValueError(
            f"Generated molecule contains {len(formatted_atoms)} atoms (including H), "
            f"exceeding authorized threshold of {settings.max_atoms} atoms."
        )

    clean_job_name = job_name or "smiles_mol"
    ginput = GaussianInputRequest(
        job_name=clean_job_name,
        job_type=job_type,
        method=method,
        basis=basis,
        charge=mol3d.charge,
        multiplicity=mol3d.multiplicity,
        atoms=formatted_atoms,
        mem=mem or settings.default_mem,
        nproc=nproc or settings.default_nproc,
        chk=chk,
        extra_keywords=extra_keywords or [],
        title=title or f"Generated from SMILES: {mol3d.canonical_smiles}",
    )

    result = generate_gjf(ginput)
    if (job_type or "").strip().lower() == "sp":
        result.setdefault("warnings", []).append(
            "该输入直接以 RDKit MMFF94s 初始构象执行单点能计算 (sp)，"
            "力场几何不代表 DFT 平衡结构，能量仅作近似参考。"
        )
    result["atoms"] = [[a.element, a.x, a.y, a.z] for a in mol3d.atoms]
    result["smiles_info"] = {
        "canonical_smiles": mol3d.canonical_smiles,
        "charge": mol3d.charge,
        "multiplicity": mol3d.multiplicity,
        "spin_inference": mol3d.spin_inference,
        "converged_conformers": mol3d.converged_conformers,
        "mmff_energy": mol3d.mmff_energy,
        "mmff_energy_unit": "kcal/mol (MMFF94s force-field energy, NOT quantum electronic Hartree energy)",
        "geometry_disclaimer": (
            "3D coordinates generated by RDKit ETKDGv3 + MMFF94s force field are an initial guess only, "
            "NOT a DFT/ab initio equilibrium geometry."
        ),
        "warnings": mol3d.warnings,
    }

    if save_to_file:
        base = validate_safe_path(output_dir or settings.work_dir, mode="write")
        target_file = validate_safe_path(base / result["filename"], mode="write")
        target_file.parent.mkdir(parents=True, exist_ok=True)
        with open(target_file, "w", encoding="utf-8") as f:
            f.write(result["content"])
        result["saved_path"] = str(target_file)
    else:
        result["saved_path"] = None

    return result


# ==============================================================================
# Tool 9: submit_gaussian_calculation
# ==============================================================================
@mcp.tool()
def submit_gaussian_calculation(
    gjf_path: str,
    job_name: Optional[str] = None,
    dry_run: bool = True,
    confirmed: bool = False,
    auth_token: Optional[str] = None,
    mem: Optional[str] = None,
    nproc: Optional[int] = None,
    mock_mode: bool = False,
    fail_scf: bool = False,
    mock_duration: float = 0.5,
    integrity_token: Optional[str] = None,
    human_approval_token: Optional[str] = None,
    preflight_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Submit a Gaussian calculation job to the shared queue with 3-layer execution authorization.

    By default, executes in safe 'dry_run=True' mode, returning a complete preflight inspection
    report, resource estimates, input file digest (SHA-256), and a file-integrity token.
    Note: integrity_token/auth_token ONLY binds file and resource integrity; real g16.exe execution
    additionally requires an out-of-band human_approval_token (issued by operator CLI or host admin API)
    AND host-level permission (GAUSSIAN_ALLOW_REAL_EXECUTION=true).

    Parameters:
        gjf_path: Path to Gaussian input file (.gjf) in authorized directory.
        job_name: Optional job name identifier.
        dry_run: If True (default), performs validation and returns preflight report without launching processes.
        confirmed: Advisory flag (NOT sufficient for real execution without human_approval_token).
        auth_token: Backward-compatible alias for integrity_token issued during preflight check.
        mem: Optional memory allocation override (e.g. '12GB').
        nproc: Optional CPU core count override (e.g. 8).
        mock_mode: If True, uses the safe mock process runner for lifecycle testing without hardware execution.
        fail_scf: If True and mock_mode=True, simulates an SCF convergence failure for error testing.
        mock_duration: Sleep duration in seconds for mock process simulation.
        integrity_token: Preflight SHA-256 file & parameter integrity token (Layer 1).
        human_approval_token: Out-of-band operator approval token for this exact task (Layer 3).
        preflight_id: Optional preflight_id matching the dry-run inspection approved by the operator.

    Returns:
        Structured dictionary containing job_id, status, simulation flags, preflight report, PID, log_path, or error.
    """
    safe_gjf = validate_safe_path(gjf_path, must_exist=True, mode="read")
    preflight = run_preflight_check(safe_gjf, job_name=job_name, mem=mem, nproc=nproc)

    if not preflight["preflight_passed"]:
        reason = preflight.get("failure_reason") or preflight["input_file"].get("validation_error") or "Unknown preflight failure"
        return {
            "ok": False,
            "dry_run": dry_run,
            "error": f"Preflight validation failed: {reason}",
            "preflight": preflight,
        }

    effective_integrity_token = integrity_token or auth_token

    # Safe default: dry-run inspection only when requested or when no real/mock execution attempt is indicated
    if dry_run or (not mock_mode and not confirmed and not human_approval_token and not effective_integrity_token):
        return {
            "ok": True,
            "dry_run": True,
            "preflight": preflight,
            "message": (
                "Preflight inspection passed. Calculation has NOT been launched. "
                "Note: integrity_token/auth_token verifies file integrity ONLY and does NOT grant human approval. "
                "For simulated testing without hardware impact: set dry_run=False and mock_mode=True. "
                "For real g16.exe execution: set dry_run=False, provide both integrity_token and an out-of-band "
                "human_approval_token (or host approval receipt), and ensure GAUSSIAN_ALLOW_REAL_EXECUTION=true."
            ),
        }

    # Simulation mode for automated testing without hardware execution
    if mock_mode:
        content = safe_gjf.read_text(encoding="utf-8", errors="ignore")
        submit_res = job_manager.submit(
            job_name=job_name or safe_gjf.stem,
            gjf_content=content,
            mem=mem,
            nproc=nproc,
            mock_mode=True,
            fail_scf=fail_scf,
            mock_duration=mock_duration,
        )
        submit_res["mock_mode"] = True
        submit_res["is_simulated"] = True
        submit_res["real_gaussian_result"] = False
        submit_res["execution_mode"] = "mock_simulation"
        submit_res["simulation_warning"] = (
            "MOCK SIMULATION ONLY: Executed via backend.mock_worker (NOT real g16.exe). "
            "Do NOT treat simulated energies as real Gaussian calculation results."
        )
        submit_res["preflight"] = preflight
        if "job" in submit_res and isinstance(submit_res["job"], dict):
            j = submit_res["job"]
            submit_res["job_id"] = j.get("job_id")
            submit_res["status"] = j.get("status")
            submit_res["pid"] = j.get("pid")
            submit_res["log_path"] = j.get("log_path")
            submit_res["is_simulated"] = bool(j.get("is_simulated", True))
            submit_res["real_gaussian_result"] = not submit_res["is_simulated"]
            submit_res["execution_mode"] = j.get("execution_mode", "mock_simulation")
            submit_res["simulation_warning"] = j.get("simulation_warning") or submit_res["simulation_warning"]
        return submit_res

    # Real execution path: enforce 3 independent authorization layers:
    # Layer 1 (file/parameter integrity), Layer 3 (out-of-band human approval), Layer 2 (host gate)
    auth_eval = evaluate_real_execution_authorization(
        gjf_path=safe_gjf,
        integrity_token=effective_integrity_token,
        human_approval_token=human_approval_token,
        job_name=job_name or safe_gjf.stem,
        mem=mem,
        nproc=nproc,
        preflight_id=preflight_id,
        consume_human_token=True,
    )
    if not auth_eval.get("ok"):
        return {
            "ok": False,
            "error": auth_eval.get("error"),
            "rejected_layer": auth_eval.get("rejected_layer"),
            "authorization_audit": auth_eval.get("authorization_audit"),
            "preflight": preflight,
        }

    content = safe_gjf.read_text(encoding="utf-8", errors="ignore")
    submit_res = job_manager.submit(
        job_name=job_name or safe_gjf.stem,
        gjf_content=content,
        mem=mem,
        nproc=nproc,
        mock_mode=False,
        authorization_summary=auth_eval.get("authorization_audit"),
    )
    submit_res["mock_mode"] = False
    submit_res["is_simulated"] = False
    submit_res["real_gaussian_result"] = True
    submit_res["execution_mode"] = "gaussian16"
    submit_res["simulation_warning"] = None
    submit_res["authorization_audit"] = auth_eval.get("authorization_audit")
    submit_res["preflight"] = preflight
    if "job" in submit_res and isinstance(submit_res["job"], dict):
        j = submit_res["job"]
        submit_res["job_id"] = j.get("job_id")
        submit_res["status"] = j.get("status")
        submit_res["pid"] = j.get("pid")
        submit_res["log_path"] = j.get("log_path")
        submit_res["is_simulated"] = bool(j.get("is_simulated", False))
        submit_res["real_gaussian_result"] = not submit_res["is_simulated"]
        submit_res["execution_mode"] = j.get("execution_mode", "gaussian16")
        submit_res["simulation_warning"] = j.get("simulation_warning")
    return submit_res


# ==============================================================================
# Tool 10: get_gaussian_job_status
# ==============================================================================
@mcp.tool()
def get_gaussian_job_status(
    job_id: str,
    log_tail_lines: int = 30,
) -> Dict[str, Any]:
    """Query real-time status, progress, convergence steps, and log tail of a Gaussian calculation.

    Parameters:
        job_id: Unique identifier of the job.
        log_tail_lines: Number of trailing log lines to retrieve (default: 30, max: 100).

    Returns:
        Structured dictionary containing status, simulation markers, PID, timestamps, current_step,
        last_energy (None for simulated runs), simulated_energy, and log_tail.
    """
    if not job_id or not job_id.strip():
        raise ValueError("Parameter 'job_id' must not be empty.")

    bounded_tail = min(max(0, log_tail_lines), 100)
    job_info = job_manager.get_job(job_id=job_id.strip(), log_tail_lines=bounded_tail)
    if not job_info:
        raise ValueError(f"Job '{job_id}' not found in job repository.")

    is_sim = bool(job_info.get("is_simulated", False))
    return {
        "ok": True,
        "job_id": job_info["job_id"],
        "job_name": job_info["job_name"],
        "status": job_info["status"],
        "pid": job_info.get("pid"),
        "created_at": job_info.get("created_at"),
        "started_at": job_info.get("started_at"),
        "finished_at": job_info.get("finished_at"),
        "current_step": job_info.get("current_step"),
        "last_energy": None if is_sim else job_info.get("last_energy"),
        "simulated_energy": job_info.get("simulated_energy"),
        "is_simulated": is_sim,
        "real_gaussian_result": not is_sim,
        "execution_mode": job_info.get("execution_mode") or ("mock_simulation" if is_sim else "gaussian16"),
        "simulation_warning": job_info.get("simulation_warning"),
        "log_path": job_info.get("log_path"),
        "gjf_path": job_info.get("gjf_path"),
        "error": job_info.get("error"),
        "log_tail": job_info.get("log_tail", ""),
    }


# ==============================================================================
# Tool 11: list_gaussian_jobs
# ==============================================================================
@mcp.tool()
def list_gaussian_jobs(
    limit: int = 20,
    status_filter: Optional[str] = None,
) -> Dict[str, Any]:
    """List submitted Gaussian jobs, their statuses, timestamps, and resource allocations.

    Parameters:
        limit: Maximum number of jobs to return (default: 20, max: 100).
        status_filter: Optional status filter ('running', 'completed', 'failed', 'stopped', 'pending').

    Returns:
        Structured dictionary containing total_count, returned_count, active_running_job, and jobs list.
    """
    bounded_limit = min(max(1, limit), 100)
    all_jobs = job_manager.list_jobs(limit=100)

    if status_filter:
        flt = status_filter.strip().lower()
        filtered = [j for j in all_jobs if j.get("status", "").lower() == flt]
    else:
        filtered = all_jobs

    page = filtered[:bounded_limit]
    enriched_page = []
    for j in page:
        item = dict(j)
        is_sim = bool(item.get("is_simulated", False))
        item["is_simulated"] = is_sim
        item["real_gaussian_result"] = not is_sim
        item.setdefault("execution_mode", "mock_simulation" if is_sim else "gaussian16")
        if is_sim:
            item["last_energy"] = None
            if not item.get("simulation_warning"):
                item["simulation_warning"] = (
                    "MOCK SIMULATION ONLY: Simulated energy is isolated in 'simulated_energy'; "
                    "'last_energy' is withheld (None)."
                )
        enriched_page.append(item)

    return {
        "ok": True,
        "total_jobs": len(all_jobs),
        "returned_jobs": len(enriched_page),
        "has_active_running_job": job_manager.has_running(),
        "jobs": enriched_page,
    }


# ==============================================================================
# Tool 12: stop_gaussian_calculation
# ==============================================================================
@mcp.tool()
def stop_gaussian_calculation(
    job_id: str,
) -> Dict[str, Any]:
    """Gracefully terminate a running Gaussian calculation and release compute scheduler locks.

    Verifies PID and process identity before termination to prevent PID recycling false-kills.
    Kills the entire process tree (g16.exe and all active link sub-executables).

    Parameters:
        job_id: Identifier of the job to terminate.

    Returns:
        Structured dictionary containing ok, status, and job state.
    """
    if not job_id or not job_id.strip():
        raise ValueError("Parameter 'job_id' must not be empty.")

    res = job_manager.stop_job(job_id=job_id.strip())
    if "job" in res and isinstance(res["job"], dict):
        res["status"] = res["job"].get("status")
        res["job_id"] = res["job"].get("job_id")
        is_sim = bool(res["job"].get("is_simulated", False))
        res["is_simulated"] = is_sim
        res["real_gaussian_result"] = not is_sim
        res["execution_mode"] = res["job"].get("execution_mode") or ("mock_simulation" if is_sim else "gaussian16")
        res["simulation_warning"] = res["job"].get("simulation_warning")
    return res


# ==============================================================================
# Tool 13: extract_structure_from_file
# ==============================================================================
@mcp.tool()
def extract_structure_from_file(
    file_path: str,
) -> Dict[str, Any]:
    """Extract a canonical SMILES string and atom count guess from a chemical structure or Gaussian file.

    Supported formats inside authorized read boundaries:
    - Molecular files: .mol, .sdf, .sd, .mol2, .pdb, .xyz, .cdxml (OpenBabel with RDKit fallback)
    - Gaussian inputs: .gjf (Cartesian coordinate block)
    - Gaussian outputs: .out, .log (final Standard/Input orientation coordinate block)

    Parameters:
        file_path: Path to the structure/calculation file inside authorized read roots.

    Returns:
        Structured dictionary with ok, file_path, smiles, source_format, source_file,
        natoms_guess, extractor ('openbabel' or 'rdkit_fallback'), and warnings.
    """
    if not file_path or not file_path.strip():
        raise ValueError("Parameter 'file_path' must not be empty.")

    safe_path = validate_safe_path(file_path.strip(), must_exist=True, mode="read")
    result = extract_smiles_from_file(str(safe_path))
    return {
        "ok": True,
        "file_path": str(safe_path),
        **result,
    }


# ==============================================================================
# Tool 14: postprocess_capabilities
# ==============================================================================
@mcp.tool()
def postprocess_capabilities() -> Dict[str, Any]:
    """Probe post-processing tool readiness (formchk, Multiwfn, VMD) and grid safety limits.

    Detects real Multiwfn banner version via probe_version() without hardcoding versions,
    and reports supported post-processing workflows ('orbitals', 'esp', 'rdg', 'mo_levels').
    """
    formchk_ok = bool(settings.formchk_exe and Path(settings.formchk_exe).exists())
    multiwfn_ok = bool(settings.multiwfn_exe and Path(settings.multiwfn_exe).exists())
    vmd_ok = bool(settings.vmd_exe and Path(settings.vmd_exe).exists())

    detected_version = mwfn_probe_version() if multiwfn_ok else None
    expected_main = str(settings.expected_multiwfn_version or "3.8").split(".")[0]
    detected_main = detected_version.split(".")[0] if detected_version else None
    version_matched = detected_main == expected_main if detected_version else False

    return {
        "ok": True,
        "formchk": {
            "exists": formchk_ok,
            "path": str(settings.formchk_exe) if settings.formchk_exe else None,
        },
        "multiwfn": {
            "exists": multiwfn_ok,
            "path": str(settings.multiwfn_exe) if settings.multiwfn_exe else None,
            "version": detected_version,
            "expected_version": settings.expected_multiwfn_version,
            "version_matched": version_matched,
        },
        "vmd": {
            "exists": vmd_ok,
            "path": str(settings.vmd_exe) if settings.vmd_exe else None,
        },
        "max_grid_points": settings.postprocess_max_grid_points,
        "supported_kinds": ["orbitals", "esp", "rdg", "mo_levels"],
        "supported_grids": ["coarse", "medium", "fine"],
    }


# ==============================================================================
# Tool 15: create_postprocess_task
# ==============================================================================
@mcp.tool()
def create_postprocess_task(
    kind: Literal["orbitals", "esp", "rdg", "mo_levels"],
    job_id: Optional[str] = None,
    fchk_path: Optional[str] = None,
    chk_path: Optional[str] = None,
    orbitals: Optional[List[int]] = None,
    orbital_labels: Optional[List[Literal["HOMO", "LUMO"]]] = None,
    grid: Literal["coarse", "medium", "fine"] = "medium",
    orbital_isovalue: float = 0.02,
    density_isovalue: float = 0.001,
    render: bool = True,
    wait: bool = False,
    wait_timeout_seconds: float = 120.0,
) -> Dict[str, Any]:
    """Create and schedule a Multiwfn / VMD / MO-level post-processing task with sandbox & grid guards.

    Provide exactly one input source among job_id, fchk_path, or chk_path.
    - 'orbitals': Multiwfn orbital cube generation + optional VMD isosurface rendering
    - 'esp': Multiwfn density + total ESP cubes + optional VMD electrostatic surface rendering
    - 'rdg': Multiwfn NCI/RDG analysis cubes + optional VMD rendering
    - 'mo_levels': Direct orbital energy level diagram (.svg) via fchk_reader

    Parameters:
        kind: Post-processing task type ('orbitals', 'esp', 'rdg', 'mo_levels').
        job_id: Completed Gaussian job ID whose checkpoint will be converted/read.
        fchk_path: Path to formatted checkpoint (.fchk/.fch) inside authorized read boundaries.
        chk_path: Path to binary checkpoint (.chk) inside authorized read boundaries.
        orbitals: Optional list of positive 1-based orbital indices for 'orbitals' mode.
        orbital_labels: Optional ['HOMO', 'LUMO'] labels auto-resolved from fchk.
        grid: Cube grid resolution ('coarse', 'medium', 'fine').
        orbital_isovalue: Positive isovalue for orbital rendering (default 0.02).
        density_isovalue: Positive isovalue for ESP surface rendering (default 0.001).
        render: Whether to run VMD rendering after cube generation (default True).
        wait: If True, waits up to wait_timeout_seconds for task completion before returning.
        wait_timeout_seconds: Maximum synchronous wait time in seconds when wait=True (max 300s).

    Returns:
        Structured dictionary with ok, task_id, status, artifacts (when ready), or error.
    """
    sources = [bool(job_id and job_id.strip()), bool(fchk_path and fchk_path.strip()), bool(chk_path and chk_path.strip())]
    if sum(sources) != 1:
        raise ValueError("Provide exactly one input source among 'job_id', 'fchk_path', or 'chk_path'.")

    safe_fchk: Optional[str] = None
    safe_chk: Optional[str] = None
    clean_job_id: Optional[str] = None

    if fchk_path:
        safe_fchk = str(validate_safe_path(fchk_path.strip(), must_exist=True, mode="read"))
    if chk_path:
        safe_chk = str(validate_safe_path(chk_path.strip(), must_exist=True, mode="read"))
    if job_id:
        clean_job_id = job_id.strip()
        if not re.fullmatch(r"[\w.-]+", clean_job_id):
            raise ValueError(f"Invalid job_id format: {job_id!r}")
        job_info = job_manager.get_job(clean_job_id, log_tail_lines=0)
        if not job_info:
            raise FileNotFoundError(f"Gaussian job '{clean_job_id}' does not exist.")
        if not job_info.get("normal_termination", False) and job_info.get("status") != "completed":
            raise ValueError(f"Gaussian job '{clean_job_id}' is not completed (status={job_info.get('status')}).")
        chk_candidate = job_info.get("chk_path")
        if not chk_candidate:
            raise ValueError(f"Gaussian job '{clean_job_id}' has no recorded chk_path.")
        validate_safe_path(chk_candidate, must_exist=True, mode="read")

    if orbitals is not None:
        if any(int(o) <= 0 for o in orbitals):
            raise ValueError("All entries in 'orbitals' must be positive 1-based integers.")
    if orbital_isovalue <= 0 or density_isovalue <= 0:
        raise ValueError("'orbital_isovalue' and 'density_isovalue' must be positive.")

    req = PostprocessRequest(
        kind=kind,
        job_id=clean_job_id,
        fchk_path=safe_fchk,
        chk_path=safe_chk,
        orbitals=orbitals,
        orbital_labels=orbital_labels,
        grid=grid,
        orbital_isovalue=orbital_isovalue,
        density_isovalue=density_isovalue,
        render=render,
    )

    if kind in ("orbitals", "esp", "rdg"):
        postprocess_manager._check_grid_points(req)

    if not memory_guard.can_accept_compute():
        snap = memory_guard.snapshot()
        return {
            "ok": False,
            "error": (
                f"Backend memory reached hard limit (RSS {snap['rss_mb']}MB >= {snap['hard_mb']}MB); "
                "refusing new post-processing task."
            ),
        }

    lease = chem_scheduler.current_lease()
    if lease is not None:
        return {
            "ok": False,
            "error": f"Compute resource is currently busy (held by {lease.owner_id} for {lease.kind}).",
        }

    task = postprocess_manager.create_task(req)

    def _runner(tid: str, request: PostprocessRequest) -> None:
        try:
            postprocess_manager.run_task(tid, request, enforce_sandbox=True)
        except Exception as exc:
            try:
                loaded = postprocess_manager._load(tid)
                if loaded and loaded.status not in ("completed", "failed"):
                    loaded.status = "failed"
                    loaded.error = f"Unhandled background error: {exc}"
                    loaded.finished_at = time.time()
                    postprocess_manager._save(loaded)
            except Exception:
                pass

    worker = threading.Thread(
        target=_runner,
        args=(task.task_id, req),
        daemon=True,
        name=f"mcp-pp-{task.task_id}",
    )
    worker.start()

    if wait:
        bounded_wait = min(max(0.5, float(wait_timeout_seconds)), 300.0)
        worker.join(timeout=bounded_wait)
        latest = postprocess_manager.get_task(task.task_id) or task.model_dump()
        return {
            "ok": latest.get("status") != "failed",
            "completed": latest.get("status") == "completed",
            "timed_out": worker.is_alive() and latest.get("status") not in ("completed", "failed"),
            "task_id": task.task_id,
            "task": latest,
        }

    return {
        "ok": True,
        "task_id": task.task_id,
        "status": task.status,
        "kind": task.kind,
        "poll_tool": "get_postprocess_task",
        "message": "Post-processing task scheduled; poll get_postprocess_task for completion and artifacts.",
    }


# ==============================================================================
# Tool 16: get_postprocess_task
# ==============================================================================
@mcp.tool()
def get_postprocess_task(
    task_id: str,
) -> Dict[str, Any]:
    """Query status, error details, logs, and generated artifact files of a post-processing task.

    Parameters:
        task_id: Identifier of the post-processing task.

    Returns:
        Structured dictionary with ok and task details (status, artifacts, logs, error).
    """
    clean_id = (task_id or "").strip()
    if not clean_id or not re.fullmatch(r"[\w.-]+", clean_id):
        raise ValueError(f"Invalid parameter 'task_id': {task_id!r}")

    task = postprocess_manager.get_task(clean_id)
    if not task:
        return {
            "ok": False,
            "task_id": clean_id,
            "error": f"Post-processing task '{clean_id}' not found.",
        }
    return {
        "ok": True,
        "task_id": clean_id,
        "status": task.get("status"),
        "kind": task.get("kind"),
        "task": task,
    }


# ==============================================================================
# Tool 17: list_postprocess_tasks
# ==============================================================================
@mcp.tool()
def list_postprocess_tasks(
    limit: int = 50,
    kind_filter: Optional[str] = None,
    status_filter: Optional[str] = None,
) -> Dict[str, Any]:
    """List recent post-processing tasks with optional filtering by kind or status.

    Parameters:
        limit: Maximum number of tasks to return (default: 50, max: 100).
        kind_filter: Optional kind filter ('orbitals', 'esp', 'rdg', 'mo_levels').
        status_filter: Optional status filter ('pending', 'running', 'completed', 'failed').

    Returns:
        Structured dictionary containing total_tasks, returned_tasks, and tasks list.
    """
    bounded_limit = min(max(1, int(limit)), 100)
    all_tasks = postprocess_manager.list_tasks(limit=100)
    filtered = all_tasks
    if kind_filter and kind_filter.strip():
        kf = kind_filter.strip().lower()
        filtered = [t for t in filtered if (t.get("kind") or "").lower() == kf]
    if status_filter and status_filter.strip():
        sf = status_filter.strip().lower()
        filtered = [t for t in filtered if (t.get("status") or "").lower() == sf]

    page = filtered[:bounded_limit]
    return {
        "ok": True,
        "total_tasks": len(all_tasks),
        "returned_tasks": len(page),
        "tasks": page,
    }


# Optional Sobko knowledge base extension (never breaks startup if Sobko is absent)
try:
    if register_sobko_tools is not None:
        _sobko_ext_state.update(register_sobko_tools(mcp))
except Exception as _ext_err:
    logger.warning("Optional Sobko MCP extension initialization skipped: %s", _ext_err)
    _sobko_ext_state = {"registered": False, "tools": [], "enabled": False, "error": str(_ext_err)}


def main():
    """Main entrypoint for MCP stdio transport."""
    logger.info("Starting Gaussian MCP Server via stdio transport...")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
