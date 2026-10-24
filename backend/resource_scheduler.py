"""ChemComputeScheduler — 统一本机计算资源调度层。

在 15.1 GB 内存机器上，Gaussian、Multiwfn、VMD、RDKit 重计算四者必须互斥，
不能同时运行。轻量任务（log 解析、BSE 查询、Sobko、status 查询）不需要 lease。

关键点：Uvicorn 必须单 worker（workers=1），否则每个 worker 各有一份 scheduler，
互斥约束直接失效。
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Literal, Optional


ComputeKind = Literal["gaussian", "multiwfn", "vmd", "rdkit"]


@dataclass(frozen=True)
class ComputeLease:
    """一份计算资源租约。"""
    owner_id: str
    kind: ComputeKind
    acquired_at: float


class ResourceBusyError(Exception):
    """计算资源被占用，无法获取 lease。"""

    def __init__(self, current_lease: Optional[ComputeLease]) -> None:
        self.current_lease = current_lease
        if current_lease:
            super().__init__(
                f"计算资源被占用：{current_lease.kind} (owner={current_lease.owner_id}) "
                f"已占用 {time.time() - current_lease.acquired_at:.0f} 秒"
            )
        else:
            super().__init__("计算资源被占用")


class ChemComputeScheduler:
    """计算资源调度器（单例，线程安全）。

    重型计算任务必须先 acquire() 获取 lease，结束后 release()。
    轻量任务（解析/查询/检索）不需要 lease。
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._lease: Optional[ComputeLease] = None

    def acquire(self, owner_id: str, kind: ComputeKind) -> ComputeLease:
        """获取计算资源 lease。若已被占用则抛 ResourceBusyError。"""
        with self._lock:
            if self._lease is not None:
                raise ResourceBusyError(self._lease)
            lease = ComputeLease(owner_id=owner_id, kind=kind, acquired_at=time.time())
            self._lease = lease
            return lease

    def release(self, owner_id: str) -> None:
        """释放 lease。只有 owner 本人能释放。"""
        with self._lock:
            if self._lease and self._lease.owner_id == owner_id:
                self._lease = None

    def current_lease(self) -> Optional[ComputeLease]:
        """查看当前 lease（不获取）。"""
        with self._lock:
            return self._lease

    def has_lease(self) -> bool:
        """是否有 lease 被占用。"""
        return self.current_lease() is not None


# 全局单例
chem_scheduler = ChemComputeScheduler()
