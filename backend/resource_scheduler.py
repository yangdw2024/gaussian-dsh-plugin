"""ChemComputeScheduler — 跨进程统一计算资源调度层。

在 15.1 GB 内存机器上，Gaussian、Multiwfn、VMD、RDKit 重计算四者必须互斥，
不能同时运行。轻量任务（log 解析、BSE 查询、Sobko、status 查询）不需要 lease。

V5.1 加固：DSH Backend (FastAPI) 与 MCP Server (stdio) 分别运行在独立 OS 进程中，
仅靠内存 threading.Lock 无法阻止双客户端并发越界。本模块采用：
  1. 进程内 threading.Lock() + 跨进程 OS 文件锁 (compute_lease.lock)
  2. 持久化共享租约状态文件 (compute_lease.json)
  3. 持有进程存活与 PID 实例复用校验 + 孤儿/崩溃租约自动安全回收
实现 DSH Backend 与多个 MCP Client 之间的严格跨进程资源互斥。
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Literal, Optional

import psutil

from .config import settings
from .process_utils import pid_create_time, pid_is_same_instance

if os.name == "nt":
    import msvcrt
else:
    import fcntl

logger = logging.getLogger("gaussian-dsh-backend")

ComputeKind = Literal["gaussian", "multiwfn", "vmd", "rdkit"]


@dataclass(frozen=True)
class ComputeLease:
    """一份计算资源租约（支持跨进程共享）。"""
    owner_id: str
    kind: ComputeKind
    acquired_at: float
    holder_pid: Optional[int] = None
    holder_pid_start_time: Optional[float] = None
    host_client: Optional[str] = None


class ResourceBusyError(Exception):
    """计算资源被占用，无法获取 lease。"""

    def __init__(self, current_lease: Optional[ComputeLease]) -> None:
        self.current_lease = current_lease
        if current_lease:
            pid_note = f", pid={current_lease.holder_pid}" if current_lease.holder_pid else ""
            client_note = f", client={current_lease.host_client}" if current_lease.host_client else ""
            super().__init__(
                f"计算资源被占用：{current_lease.kind} (owner={current_lease.owner_id}"
                f"{pid_note}{client_note}) 已占用 {max(0.0, time.time() - current_lease.acquired_at):.0f} 秒"
            )
        else:
            super().__init__("计算资源被占用")


def _fast_pid_alive(pid: Optional[int]) -> bool:
    """快速校验 PID 是否存活（优先使用 psutil，避免在文件锁内启动 tasklist 子进程）。"""
    if not pid or pid <= 0:
        return False
    try:
        if not psutil.pid_exists(pid):
            return False
        proc = psutil.Process(pid)
        return proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False
    except Exception:
        return False


class ChemComputeScheduler:
    """跨进程线程安全计算资源调度器（单例）。

    重型计算任务必须先 acquire() 获取全局跨进程 lease，结束后 release()。
    轻量任务（解析/查询/检索）不需要 lease。
    """

    def __init__(self, state_dir: Optional[Path] = None) -> None:
        self._thread_lock = threading.Lock()
        self._explicit_state_dir = state_dir

    def _state_dir(self) -> Path:
        if self._explicit_state_dir is not None:
            base = self._explicit_state_dir
        else:
            env_dir = os.environ.get("GAUSSIAN_DATA_DIR")
            base = Path(env_dir) if env_dir else settings.data_dir
        base.mkdir(parents=True, exist_ok=True)
        return base

    def _lease_file(self) -> Path:
        return self._state_dir() / "compute_lease.json"

    def _lock_file(self) -> Path:
        return self._state_dir() / "compute_lease.lock"

    @contextmanager
    def _cross_process_lock(self, timeout: float = 10.0) -> Iterator[None]:
        """进程内线程锁 + 内核级文件排他锁。"""
        with self._thread_lock:
            lock_path = self._lock_file()
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            f = open(lock_path, "a+b")
            locked = False
            try:
                if os.name == "nt":
                    f.seek(0, os.SEEK_END)
                    if f.tell() == 0:
                        f.write(b"0")
                        f.flush()
                    deadline = time.monotonic() + timeout
                    while True:
                        try:
                            f.seek(0)
                            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                            locked = True
                            break
                        except OSError:
                            if time.monotonic() >= deadline:
                                raise TimeoutError(f"等待跨进程计算资源锁超时 ({timeout}s)")
                            time.sleep(0.01)
                else:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                    locked = True
                yield
            finally:
                if locked:
                    try:
                        if os.name == "nt":
                            f.seek(0)
                            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
                        else:
                            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                    except Exception:
                        pass
                try:
                    f.close()
                except Exception:
                    pass

    def _is_lease_alive_locked(self, data: dict) -> bool:
        """判断当前持久化 lease 是否仍有效（支持崩溃/孤儿持有者自动识别回收）。"""
        holder_pid = data.get("holder_pid")
        holder_start = data.get("holder_pid_start_time")
        owner_id = data.get("owner_id", "")
        kind = data.get("kind", "")

        # 1. 若持有进程仍存活且非 PID 复用 → lease 仍然有效
        if holder_pid:
            alive = _fast_pid_alive(holder_pid)
            same = pid_is_same_instance(holder_pid, holder_start) if alive else False
            if alive and same is not False:
                return True

        # 2. 若 holder_pid 已死亡（例如 DSH admin_shutdown 有意保留了运行中的 g16.exe）：
        #    仅当 kind=="gaussian" 且 jobs/<owner_id>.json 中子进程仍存活时才视为有效。
        if kind == "gaussian" and owner_id:
            job_file = self._state_dir() / "jobs" / f"{owner_id}.json"
            if job_file.exists():
                try:
                    jdata = json.loads(job_file.read_text(encoding="utf-8"))
                    if jdata.get("status") == "running" and jdata.get("pid"):
                        jpid = int(jdata["pid"])
                        jstart = jdata.get("pid_start_time")
                        jalive = _fast_pid_alive(jpid)
                        jsame = pid_is_same_instance(jpid, jstart) if jalive else False
                        if jalive and jsame is not False:
                            return True
                except Exception:
                    pass

        return False

    def _read_lease_locked(self) -> Optional[ComputeLease]:
        """在锁内读取并校验共享租约；若发现持有进程已崩溃则自动清理失效租约。"""
        lease_path = self._lease_file()
        if not lease_path.exists():
            return None
        try:
            raw = lease_path.read_text(encoding="utf-8").strip()
            if not raw:
                return None
            data = json.loads(raw)
        except Exception as exc:
            logger.warning("读取跨进程计算租约文件失败，将清理损坏锁文件 %s: %s", lease_path, exc)
            try:
                lease_path.unlink(missing_ok=True)
            except Exception:
                pass
            return None

        if not self._is_lease_alive_locked(data):
            logger.warning(
                "检测到失效计算资源租约 (owner=%s, kind=%s, holder_pid=%s) 已失去存活进程，自动回收锁",
                data.get("owner_id"),
                data.get("kind"),
                data.get("holder_pid"),
            )
            try:
                lease_path.unlink(missing_ok=True)
            except Exception:
                pass
            return None

        return ComputeLease(
            owner_id=str(data["owner_id"]),
            kind=data["kind"],
            acquired_at=float(data["acquired_at"]),
            holder_pid=data.get("holder_pid"),
            holder_pid_start_time=data.get("holder_pid_start_time"),
            host_client=data.get("host_client"),
        )

    def _write_lease_locked(self, lease: ComputeLease) -> None:
        """原子替换写入跨进程租约 JSON，防止并发读取半截文件。"""
        lease_path = self._lease_file()
        lease_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = lease_path.with_name(f".compute_lease.{os.getpid()}.{threading.get_ident()}.tmp")
        payload = {
            "owner_id": lease.owner_id,
            "kind": lease.kind,
            "acquired_at": lease.acquired_at,
            "holder_pid": lease.holder_pid,
            "holder_pid_start_time": lease.holder_pid_start_time,
            "host_client": lease.host_client,
        }
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp_path, lease_path)

    def acquire(
        self,
        owner_id: str,
        kind: ComputeKind,
        client_tag: Optional[str] = None,
    ) -> ComputeLease:
        """获取全局跨进程计算资源 lease。若已被任何进程占用则抛 ResourceBusyError。"""
        my_pid = os.getpid()
        my_start = pid_create_time(my_pid)
        tag = client_tag or os.environ.get("GAUSSIAN_CLIENT_ROLE", "backend")

        with self._cross_process_lock():
            existing = self._read_lease_locked()
            if existing is not None:
                raise ResourceBusyError(existing)
            lease = ComputeLease(
                owner_id=owner_id,
                kind=kind,
                acquired_at=time.time(),
                holder_pid=my_pid,
                holder_pid_start_time=my_start,
                host_client=tag,
            )
            self._write_lease_locked(lease)
            return lease

    def release(self, owner_id: str) -> None:
        """释放跨进程 lease。只有 owner 本人能释放。"""
        with self._cross_process_lock():
            existing = self._read_lease_locked()
            if existing is not None and existing.owner_id == owner_id:
                try:
                    self._lease_file().unlink(missing_ok=True)
                except Exception:
                    pass

    def current_lease(self) -> Optional[ComputeLease]:
        """查看当前全局跨进程 lease（不获取）。"""
        with self._cross_process_lock():
            return self._read_lease_locked()

    def has_lease(self) -> bool:
        """是否有全局 lease 被任何进程占用。"""
        return self.current_lease() is not None


# 全局单例
chem_scheduler = ChemComputeScheduler()
