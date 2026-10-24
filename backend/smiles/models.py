"""SMILES → 3D 结构请求/响应模型。"""
from __future__ import annotations

from typing import List, Optional, Literal

from pydantic import BaseModel, Field


class AtomCoordinate(BaseModel):
    """单个原子坐标。"""
    element: str
    x: float
    y: float
    z: float


class Smiles3DRequest(BaseModel):
    """从 SMILES 生成 3D 结构的请求。"""
    smiles: str = Field(..., description="SMILES 字符串")
    num_conformers: int = Field(default=24, ge=1, le=64, description="生成构象数")
    max_iterations: int = Field(default=500, ge=50, le=5000, description="MMFF 优化最大迭代次数")
    random_seed: int = Field(default=0xC0FFEE, description="随机种子（可复现）")
    multiplicity: Optional[int] = Field(default=None, ge=1, description="自旋多重度（不填则自动推断）")
    allow_disconnected: bool = Field(default=False, description="是否允许多片段体系（盐等）")


class Smiles3DResponse(BaseModel):
    """SMILES → 3D 结构生成结果。"""
    canonical_smiles: str
    charge: int
    multiplicity: int
    spin_inference: str  # closed_shell_singlet / single_radical_doublet / user_override / ambiguous
    atoms: List[AtomCoordinate]
    generated_conformers: int
    converged_conformers: int
    selected_conformer: int
    mmff_energy: float
    warnings: List[str]


class AmbiguousSpinError(Exception):
    """无法可靠推断自旋多重度。"""
    pass


class DisconnectedMoleculeError(Exception):
    """多片段体系（盐等）需要显式确认。"""
    pass


class MMFFParamError(Exception):
    """MMFF 参数不完整。"""
    pass
