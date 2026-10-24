"""后端内存 RSS 守卫（M6 加固）。

用 psutil 周期采样本进程常驻内存（RSS）：
- soft_mb：超过只告警、在 status 中暴露 pressure，不拒绝请求；
- hard_mb：拒绝新的重计算任务（Gaussian/Multiwfn/VMD/RDKit 重算），
  但【绝不主动杀进程】，保护正在运行的 Gaussian 子进程，由 managed
  端点 / reconcile 回收。

设计前提：物理内存仅约 15GB，Gaussian 已占 12GB，后端自身不能无界膨胀。
"""
from __future__ import annotations

import os
import threading
import time
from typing import Dict, Optional

import psutil

from .config import settings


class MemoryGuard:
    """单例 RSS 守卫。"""

    def __init__(self, soft_mb: int, hard_mb: int, sample_interval_s: float = 5.0) -> None:
        self.soft_mb = soft_mb
        self.hard_mb = hard_mb
        self.sample_interval_s = sample_interval_s
        self._process = psutil.Process(os.getpid())
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.rss_mb: float = 0.0
        self.level: str = "normal"   # normal / soft / hard
        self.soft_notified: bool = False
        self.peak_mb: float = 0.0
        self.last_sample_at: float = 0.0

    # ---------- 采样 ----------
    def _sample(self) -> None:
        try:
            rss = self._process.memory_info().rss
        except Exception:
            return
        mb = rss / (1024 * 1024)
        with self._lock:
            self.rss_mb = round(mb, 1)
            self.peak_mb = round(max(self.peak_mb, mb), 1)
            self.last_sample_at = time.time()
            if mb >= self.hard_mb:
                self.level = "hard"
            elif mb >= self.soft_mb:
                self.level = "soft"
            else:
                self.level = "normal"
                self.soft_notified = False

    def _loop(self) -> None:
        while not self._stop.wait(self.sample_interval_s):
            self._sample()

    # ---------- 生命周期 ----------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._sample()
        self._thread = threading.Thread(
            target=self._loop, name="memory-guard", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    # ---------- 决策 ----------
    def over_hard(self) -> bool:
        """是否已超过 hard 阈值（用于拒绝新重计算）。"""
        self._sample()
        return self.level == "hard"

    def can_accept_compute(self) -> bool:
        """新的重计算是否可被接受：hard 时拒绝，soft/normal 放行。"""
        return not self.over_hard()

    def snapshot(self) -> Dict:
        self._sample()
        with self._lock:
            return {
                "rss_mb": self.rss_mb,
                "peak_mb": self.peak_mb,
                "soft_mb": self.soft_mb,
                "hard_mb": self.hard_mb,
                "level": self.level,
                "can_accept_compute": self.level != "hard",
            }


memory_guard = MemoryGuard(
    soft_mb=settings.backend_rss_soft_mb,
    hard_mb=settings.backend_rss_hard_mb,
)
