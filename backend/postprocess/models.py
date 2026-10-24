"""后处理任务请求/响应模型。"""
from __future__ import annotations

from typing import List, Optional, Literal

from pydantic import BaseModel, Field


class PostprocessRequest(BaseModel):
    """后处理任务请求。"""
    kind: Literal["orbitals", "esp", "rdg", "mo_levels"]
    job_id: Optional[str] = Field(default=None, description="Gaussian 任务 ID（从已有 chk 后处理）")
    fchk_path: Optional[str] = Field(default=None, description="直接指定 fchk 文件路径")
    chk_path: Optional[str] = Field(default=None, description="直接指定 chk 文件路径（自动 formchk）")

    # orbitals 参数
    orbitals: Optional[List[int]] = Field(default=None, description="轨道编号列表（如 [87, 88]）")
    orbital_labels: Optional[List[Literal["HOMO", "LUMO"]]] = Field(default=None, description="轨道标签（自动解析为编号）")

    # 通用参数
    grid: Literal["coarse", "medium", "fine"] = Field(default="medium", description="网格精度")
    orbital_isovalue: float = Field(default=0.02, description="轨道等值面值")
    density_isovalue: float = Field(default=0.001, description="电子密度等值面值")
    render: bool = Field(default=True, description="是否用 VMD 渲染 PNG")


class ArtifactInfo(BaseModel):
    """产物文件信息。"""
    name: str
    path: str
    kind: str  # image/png / chemical/cube / text/plain / image/svg+xml
    size_bytes: int = 0


class PostprocessTask(BaseModel):
    """后处理任务状态。"""
    task_id: str
    kind: str
    status: str = "pending"  # pending/running/running_multiwfn/rendering_vmd/completed/failed
    source: str = ""  # fchk 文件路径
    created_at: float = 0
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    error: Optional[str] = None
    artifacts: List[ArtifactInfo] = Field(default_factory=list)
    logs: str = ""


class PostprocessCapabilities(BaseModel):
    """后处理能力检测结果。"""
    formchk_exists: bool
    formchk_path: Optional[str]
    multiwfn_exists: bool
    multiwfn_path: Optional[str]
    multiwfn_version: Optional[str]
    vmd_exists: bool
    vmd_path: Optional[str]
    max_grid_points: int
