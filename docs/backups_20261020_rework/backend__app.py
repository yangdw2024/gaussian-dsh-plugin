"""Gaussian DSH 插件后端 — FastAPI 主应用。

提供 REST API：输入生成、输出解析、任务管理、BSE 基组、Sobko 检索、关键词参考、错误诊断。
默认监听 127.0.0.1:8765。
"""
from __future__ import annotations

import os
import platform
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .basis_set import basis_set_client
from .config import settings
from .gaussian_input import GaussianInputRequest, generate_gjf
from .gaussian_output import output_to_dict, parse_gaussian_log
from .job_manager import job_manager
from .keywords import get_all_categories, get_category, search_keywords
from .memory_guard import memory_guard
from .process_utils import kill_process_tree
from .resource_scheduler import chem_scheduler
from .postprocess.manager import postprocess_manager
from .postprocess.models import PostprocessRequest
from .smiles.models import (
    AmbiguousSpinError,
    DisconnectedMoleculeError,
    MMFFParamError,
    Smiles3DRequest,
)
from .smiles.rdkit_builder import smiles_to_3d
from .sobko_client import sobko_client


app = FastAPI(
    title="Gaussian DSH Plugin Backend",
    description="辅助 Gaussian 计算的本地后端：输入生成、输出解析、任务管理、基组获取、知识库检索。",
    version="0.2.0",
)

# 实例 ID（启动时生成，用于 health 端点确认服务身份）
INSTANCE_ID = uuid.uuid4().hex[:12]
STARTED_AT = time.time()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _on_startup():
    """后端启动时 reconcile：接管存活的 Gaussian 进程，清理已死的遗留任务。

    managed 模式热重载关闭后端时，正在跑的 Gaussian 子进程会被保留；
    下次启动时通过 PID 检查决定 adopt 还是标记 failed/completed。
    """
    try:
        stats = job_manager.reconcile()
        if any(stats.values()):
            app.logger.info(f"Reconcile: {stats}")
    except Exception as exc:
        app.logger.warning(f"Reconcile failed: {exc}")

    # M6: 启动内存 RSS 守卫（后台线程，不阻塞）
    try:
        memory_guard.start()
    except Exception as exc:
        app.logger.warning(f"Memory guard start failed: {exc}")

    # M6: 启动时静默回收过期产物（受 GC_ON_STARTUP 开关）
    if settings.gc_on_startup:
        try:
            from .artifact_gc import sweep as gc_sweep
            result = gc_sweep(dry_run=False)
            if result["deleted"]:
                app.logger.info(
                    f"GC startup: deleted {result['deleted']} files, "
                    f"freed {result['freed_bytes']} bytes"
                )
        except Exception as exc:
            app.logger.warning(f"GC startup failed: {exc}")

    # 向 stdout 打印一行 ready record，供 DSH managed 模式 readReady 解析。
    # 格式与 DSH 生态一致：{"event":"ready","service":...,"version":...,"baseUrl":...}
    import json as _json
    ready = {
        "event": "ready",
        "service": "gaussian-dsh-backend",
        "version": "0.2.0",
        "baseUrl": f"http://{settings.host}:{settings.port}",
        "pid": os.getpid(),
    }
    try:
        print(_json.dumps(ready), flush=True)
    except Exception:
        pass


# ============ 请求模型 ============

class GenerateInputRequest(BaseModel):
    job_name: str = "gaussian_job"
    job_type: str = "opt"
    method: str = "B3LYP"
    basis: str = "6-31G(d,p)"
    charge: int = 0
    multiplicity: int = 1
    atoms: List[List[Any]] = Field(default_factory=list, description="[[元素, x, y, z], ...]")
    mem: Optional[str] = None
    nproc: Optional[int] = None
    chk: Optional[str] = None
    extra_keywords: List[str] = Field(default_factory=list)
    title: Optional[str] = None
    custom_route: Optional[str] = None
    append_text: Optional[str] = None


class ParseOutputRequest(BaseModel):
    content: Optional[str] = None
    file_path: Optional[str] = None
    filename: Optional[str] = None


class SubmitJobRequest(BaseModel):
    job_name: str = "gaussian_job"
    gjf_content: str
    mem: Optional[str] = None
    nproc: Optional[int] = None


class SobkoSearchRequest(BaseModel):
    query: str
    top_k: int = 8
    source_types: Optional[List[str]] = None
    software: Optional[List[str]] = None
    topics: Optional[List[str]] = None
    authority_at_least: Optional[str] = None
    include_images: bool = True


class SobkoFetchRequest(BaseModel):
    chunk_id: Optional[str] = None
    source_id: Optional[str] = None
    expand_prev_next: int = 1


class DiagnoseRequest(BaseModel):
    error_text: str
    log_tail: Optional[str] = None


# ============ 健康检查 ============

@app.get("/v1/health")
def health():
    """健康检查：DSH 插件 managed 模式用此端点确认后端身份。

    返回 service 名称和 instance_id，避免仅凭 200 状态码误认成其他服务。
    """
    lease = chem_scheduler.current_lease()
    return {
        "ok": True,
        "service": "gaussian-dsh-backend",
        "version": "0.2.0",
        "pid": os.getpid(),
        "instance_id": INSTANCE_ID,
        "uptime_seconds": round(time.time() - STARTED_AT, 1),
        "compute_lease": {
            "held": lease is not None,
            "kind": lease.kind if lease else None,
            "owner_id": lease.owner_id if lease else None,
            "held_seconds": round(time.time() - lease.acquired_at, 1) if lease else 0,
        },
        "memory": memory_guard.snapshot(),
    }


# ============ 状态 ============

@app.get("/v1/status")
def status():
    """服务状态：Gaussian 可执行文件、Sobko、工作目录。"""
    gaussian_exists = Path(settings.gaussian_exe).exists()
    sobko_info = sobko_client.is_available()
    lease = chem_scheduler.current_lease()
    return {
        "status": "ok",
        "version": "0.2.0",
        "gaussian": {
            "exe": settings.gaussian_exe,
            "exists": gaussian_exists,
        },
        "work_dir": str(settings.work_dir),
        "data_dir": str(settings.data_dir),
        "default_mem": settings.default_mem,
        "default_nproc": settings.default_nproc,
        "sobko": sobko_info,
        "running_job": job_manager.has_running(),
        "compute_lease": {
            "held": lease is not None,
            "kind": lease.kind if lease else None,
        },
    }


# ============ Managed 模式关闭 ============

@app.post("/v1/admin/shutdown")
def admin_shutdown(authorization: Optional[str] = Header(None)):
    """Managed 模式下，DSH 插件卸载时关闭后端。

    重要：只关闭 FastAPI 进程和 Sobko 子进程，不杀正在运行的 Gaussian 子进程。
    Gaussian 子进程由 job_manager 的 PID 持久化记录，下次启动时 reconcile。

    需要 Authorization 头匹配 managed_token（若配置了的话）。
    """
    if settings.managed_token:
        if not authorization or authorization != f"Bearer {settings.managed_token}":
            raise HTTPException(status_code=403, detail="无效的 managed token")

    # 记录当前状态
    lease = chem_scheduler.current_lease()
    gaussian_running = job_manager.has_running()

    # 关闭 Sobko 子进程
    sobko_client._kill()

    # 注意：不杀 Gaussian 子进程！它由用户的 stop_gaussian_job 显式停止。
    # 下次后端启动时，job_manager.reconcile() 会扫描 PID 状态。

    # 延迟退出，让响应返回
    import threading
    def _exit():
        time.sleep(0.5)
        os._exit(0)
    threading.Thread(target=_exit, daemon=True).start()

    return {
        "ok": True,
        "message": "后端正在关闭",
        "gaussian_running_preserved": gaussian_running,
        "compute_lease_released": lease is None,
    }


@app.post("/v1/admin/gc")
def admin_gc(dry_run: bool = False, authorization: Optional[str] = Header(None)):
    """手动触发 artifact GC。managed 模式下同样校验 managed_token。

    只删 data_dir 下过期的 cube/图片/日志，绝不删 chk/fchk/gjf/json。
    """
    if settings.managed_token:
        if not authorization or authorization != f"Bearer {settings.managed_token}":
            raise HTTPException(status_code=403, detail="无效的 managed token")
    from .artifact_gc import sweep
    return {"ok": True, "result": sweep(dry_run=dry_run)}


# ============ 输入生成 ============

def _check_atom_count(n: int) -> None:
    """M6c: 原子数提前预检，超过 max_atoms 直接 422 拒绝，避免大体系占满 15GB 内存。"""
    if n > settings.max_atoms:
        raise HTTPException(
            status_code=422,
            detail=(
                f"体系含 {n} 个原子，超过本机上限 {settings.max_atoms}；"
                "在 15GB 物理内存与 12GB Gaussian 预算下请勿提交此规模，"
                "如需放宽请设置 GAUSSIAN_MAX_ATOMS 环境变量。"
            ),
        )


@app.post("/v1/gaussian-inputs")
def api_generate_input(req: GenerateInputRequest):
    """生成 Gaussian .gjf 输入文件。"""
    atoms = [(a[0], float(a[1]), float(a[2]), float(a[3])) for a in req.atoms if len(a) >= 4]
    _check_atom_count(len(atoms))
    ginput = GaussianInputRequest(
        job_name=req.job_name,
        job_type=req.job_type,
        method=req.method,
        basis=req.basis,
        charge=req.charge,
        multiplicity=req.multiplicity,
        atoms=atoms,
        mem=req.mem or settings.default_mem,
        nproc=req.nproc or settings.default_nproc,
        chk=req.chk,
        extra_keywords=req.extra_keywords,
        title=req.title,
        custom_route=req.custom_route,
        append_text=req.append_text,
    )
    result = generate_gjf(ginput)
    # 同时写入工作目录
    out_path = settings.work_dir / result["filename"]
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(result["content"])
    result["saved_path"] = str(out_path)
    return result


# ============ SMILES → 3D → Gaussian ============

@app.post("/v1/molecules/from-smiles")
def api_smiles_to_3d(req: Smiles3DRequest):
    """从 SMILES 生成 3D 结构（RDKit ETKDGv3 + MMFF94s 优化）。

    返回规范化 SMILES、电荷、自旋多重度、原子坐标、构象统计。
    多片段体系（盐）默认拒绝，需 allow_disconnected=true。
    过渡金属/多自由基不自动推断自旋，需显式指定 multiplicity。
    """
    try:
        result = smiles_to_3d(req)
        return {"ok": True, "result": result.model_dump()}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except DisconnectedMoleculeError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except AmbiguousSpinError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except MMFFParamError as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.post("/v1/gaussian-inputs/from-smiles")
def api_gaussian_input_from_smiles(req: Smiles3DRequest):
    """从 SMILES 直接生成 Gaussian .gjf 输入文件。

    流程：SMILES → RDKit 3D 优化 → Gaussian 输入生成。
    默认任务类型 opt，方法 B3LYP，基组 6-31G(d,p)。
    """
    try:
        mol3d = smiles_to_3d(req)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except DisconnectedMoleculeError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except AmbiguousSpinError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except MMFFParamError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # 转换坐标格式
    atoms = [(a.element, a.x, a.y, a.z) for a in mol3d.atoms]
    _check_atom_count(len(atoms))

    ginput = GaussianInputRequest(
        job_name=req.smiles[:20].replace("/", "_").replace("\\", "_") or "smiles_mol",
        job_type="opt",
        method="B3LYP",
        basis="6-31G(d,p)",
        charge=mol3d.charge,
        multiplicity=mol3d.multiplicity,
        atoms=atoms,
    )
    result = generate_gjf(ginput)
    result["smiles_info"] = {
        "canonical_smiles": mol3d.canonical_smiles,
        "charge": mol3d.charge,
        "multiplicity": mol3d.multiplicity,
        "spin_inference": mol3d.spin_inference,
        "converged_conformers": mol3d.converged_conformers,
        "mmff_energy": mol3d.mmff_energy,
        "warnings": mol3d.warnings,
    }
    # 写入工作目录
    out_path = settings.work_dir / result["filename"]
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(result["content"])
    result["saved_path"] = str(out_path)
    return result


# ============ 输出解析 ============

@app.post("/v1/gaussian-outputs/parse")
def api_parse_output(req: ParseOutputRequest):
    """解析 Gaussian .log/.out 输出。"""
    content = req.content
    filename = req.filename or "gaussian.log"

    if not content and req.file_path:
        path = Path(req.file_path)
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"文件不存在：{req.file_path}")
        content = path.read_text(encoding="utf-8", errors="ignore")
        filename = path.name

    if not content:
        raise HTTPException(status_code=400, detail="必须提供 content 或 file_path")

    result = parse_gaussian_log(content, filename=filename)
    return output_to_dict(result)


# ============ 任务管理 ============

@app.post("/v1/jobs")
def api_submit_job(req: SubmitJobRequest):
    """提交 Gaussian 任务（串行，若有运行中任务则拒绝）。"""
    return job_manager.submit(
        job_name=req.job_name,
        gjf_content=req.gjf_content,
        mem=req.mem,
        nproc=req.nproc,
    )


@app.get("/v1/jobs")
def api_list_jobs(limit: int = 50):
    """列出所有任务。"""
    return {"jobs": job_manager.list_jobs(limit=limit)}


@app.get("/v1/jobs/{job_id}")
def api_get_job(job_id: str, log_tail_lines: int = 30):
    """获取任务状态（含实时进度）。"""
    job = job_manager.get_job(job_id, log_tail_lines=log_tail_lines)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    return job


@app.post("/v1/jobs/{job_id}/stop")
def api_stop_job(job_id: str):
    """停止任务。"""
    return job_manager.stop_job(job_id)


# ============ BSE 基组 ============

@app.get("/v1/basis-sets")
def api_list_basis_sets(query: Optional[str] = None, family: Optional[str] = None,
                        elements: Optional[str] = None, limit: int = 50):
    """搜索/列出 BSE 基组。elements 为逗号分隔原子序数，如 6,7,8。"""
    try:
        elem_list = [int(e) for e in elements.split(",")] if elements else None
    except ValueError:
        raise HTTPException(status_code=400, detail="elements 必须为逗号分隔的整数")

    if query:
        results = basis_set_client.search(query, limit=limit)
    else:
        results = basis_set_client.list_basis_sets(family=family, elements=elem_list)
        results = results[:limit]
    return {"count": len(results), "basis_sets": results}


@app.get("/v1/basis-sets/{name}")
def api_get_basis(name: str, elements: str = "1,6,7,8", fmt: str = "gaussian94",
                  version: Optional[str] = None):
    """获取指定基组内容。elements 为逗号分隔原子序数。"""
    try:
        elem_list = [int(e) for e in elements.split(",")]
    except ValueError:
        raise HTTPException(status_code=400, detail="elements 必须为逗号分隔的整数")
    result = basis_set_client.get_basis(name, elem_list, fmt=fmt, version=version)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error", "获取失败"))
    return result


# ============ Sobko 知识库 ============

@app.get("/v1/sobko/status")
def api_sobko_status():
    """Sobko 知识库状态。"""
    return sobko_client.is_available()


@app.post("/v1/sobko/search")
def api_sobko_search(req: SobkoSearchRequest):
    """检索 Sobko 知识库（思想家公社 + Multiwfn 手册 + OPV 论文）。"""
    return sobko_client.search(
        query=req.query,
        top_k=req.top_k,
        source_types=req.source_types,
        software=req.software,
        topics=req.topics,
        authority_at_least=req.authority_at_least,
        include_images=req.include_images,
    )


@app.post("/v1/sobko/fetch")
def api_sobko_fetch(req: SobkoFetchRequest):
    """展开 Sobko source/chunk 上下文。"""
    return sobko_client.fetch(
        chunk_id=req.chunk_id,
        source_id=req.source_id,
        expand_prev_next=req.expand_prev_next,
    )


# ============ 后处理（Multiwfn + VMD） ============

@app.get("/v1/postprocess/capabilities")
def api_postprocess_capabilities():
    """检测后处理能力：formchk / Multiwfn / VMD 是否可用。"""
    formchk_ok = bool(settings.formchk_exe and Path(settings.formchk_exe).exists())
    multiwfn_ok = bool(settings.multiwfn_exe and Path(settings.multiwfn_exe).exists())
    vmd_ok = bool(settings.vmd_exe and Path(settings.vmd_exe).exists())
    return {
        "formchk": {
            "exists": formchk_ok,
            "path": str(settings.formchk_exe) if settings.formchk_exe else None,
        },
        "multiwfn": {
            "exists": multiwfn_ok,
            "path": str(settings.multiwfn_exe) if settings.multiwfn_exe else None,
            "version": "3.8" if multiwfn_ok else None,
        },
        "vmd": {
            "exists": vmd_ok,
            "path": str(settings.vmd_exe) if settings.vmd_exe else None,
        },
        "max_grid_points": settings.postprocess_max_grid_points,
    }


@app.post("/v1/postprocess/tasks")
def api_create_postprocess_task(req: PostprocessRequest):
    """创建后处理任务（orbitals / esp / rdg / mo_levels）。

    输入源三选一：
    - job_id: 从已有 Gaussian 任务的 chk 后处理
    - chk_path: 直接指定 chk 文件
    - fchk_path: 直接指定 fchk 文件
    """
    try:
        task = postprocess_manager.create_task(req)
        # 立即执行（第一版同步执行，后续可改异步）
        result = postprocess_manager.run_task(task.task_id, req)
        return result
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.get("/v1/postprocess/tasks")
def api_list_postprocess_tasks(limit: int = 50):
    """列出后处理任务。"""
    return {"tasks": postprocess_manager.list_tasks(limit=limit)}


@app.get("/v1/postprocess/tasks/{task_id}")
def api_get_postprocess_task(task_id: str):
    """获取后处理任务状态。"""
    task = postprocess_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


# ============ 关键词参考 ============

@app.get("/v1/keywords")
def api_keywords(query: Optional[str] = None, category: Optional[str] = None):
    """Gaussian 关键词参考。query 搜索，category 按分类列出。"""
    if query:
        return {"results": search_keywords(query)}
    if category:
        return {"category": category, "results": get_category(category)}
    return {"categories": get_all_categories()}


# ============ 错误诊断 ============

@app.post("/v1/diagnose")
def api_diagnose(req: DiagnoseRequest):
    """错误诊断：匹配内置错误库 + Sobko 检索解决方案。"""
    error_lower = req.error_text.lower()
    diagnoses = []

    # 匹配内置错误库
    for item in get_category("常见错误与解决方案"):
        if item["keyword"].lower() in error_lower or any(
            kw in error_lower for kw in item["description"].lower().split()
        ):
            diagnoses.append({
                "type": "builtin",
                "error": item["keyword"],
                "description": item["description"],
                "solution": item["usage"],
                "notes": item["notes"],
            })

    # Sobko 检索相关解决方案
    sobko_results = []
    try:
        sobko_resp = sobko_client.search(
            query=f"Gaussian 错误 {req.error_text[:100]} 解决方案",
            top_k=5,
        )
        if sobko_resp.get("ok"):
            sobko_results = sobko_resp.get("results", [])
    except Exception:
        pass

    return {
        "error_text": req.error_text,
        "diagnoses": diagnoses,
        "sobko_evidence": sobko_results,
    }


# ============ 启动 ============

def main():
    """启动 FastAPI 后端。

    必须 workers=1：ChemComputeScheduler 是进程内单例，
    多 worker 会各自有一份 scheduler，互斥约束直接失效。
    """
    import uvicorn
    uvicorn.run(
        "backend.app:app",
        host=settings.host,
        port=settings.port,
        workers=1,
        log_level="info",
    )


if __name__ == "__main__":
    main()
