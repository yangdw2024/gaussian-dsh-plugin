"""Gaussian DSH 插件后端 — FastAPI 主应用。

提供 REST API：输入生成、输出解析、任务管理、BSE 基组、Sobko 检索、关键词参考、错误诊断。
默认监听 127.0.0.1:8765。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .basis_set import basis_set_client
from .config import settings
from .gaussian_input import GaussianInputRequest, generate_gjf
from .gaussian_output import output_to_dict, parse_gaussian_log
from .job_manager import job_manager
from .keywords import get_all_categories, get_category, search_keywords
from .sobko_client import sobko_client


app = FastAPI(
    title="Gaussian DSH Plugin Backend",
    description="辅助 Gaussian 计算的本地后端：输入生成、输出解析、任务管理、基组获取、知识库检索。",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


# ============ 状态 ============

@app.get("/v1/status")
def status():
    """服务状态：Gaussian 可执行文件、Sobko、工作目录。"""
    gaussian_exists = Path(settings.gaussian_exe).exists()
    sobko_info = sobko_client.is_available()
    return {
        "status": "ok",
        "version": "0.1.0",
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
    }


# ============ 输入生成 ============

@app.post("/v1/gaussian-inputs")
def api_generate_input(req: GenerateInputRequest):
    """生成 Gaussian .gjf 输入文件。"""
    atoms = [(a[0], float(a[1]), float(a[2]), float(a[3])) for a in req.atoms if len(a) >= 4]
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
    import uvicorn
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="info")


if __name__ == "__main__":
    main()
