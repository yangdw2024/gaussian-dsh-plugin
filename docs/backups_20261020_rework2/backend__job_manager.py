"""Gaussian 任务管理器：提交、监控、停止、串行队列。

用户硬约束：严禁并行多任务，必须串行。提交时若有任务在运行则拒绝。
任务信息持久化到 data_dir/jobs/<job_id>.json。
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .config import settings
from .gaussian_output import parse_gaussian_log
from .process_utils import pid_alive, kill_process_tree
from .resource_scheduler import chem_scheduler, ResourceBusyError


@dataclass
class GaussianJob:
    """一个 Gaussian 计算任务。"""
    job_id: str
    job_name: str
    status: str = "pending"  # pending/running/completed/failed/stopped
    gjf_path: str = ""
    log_path: str = ""
    chk_path: str = ""
    pid: Optional[int] = None
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    error: Optional[str] = None
    # 运行时解析
    current_step: Optional[int] = None
    last_energy: Optional[float] = None
    log_tail: str = ""


class JobManager:
    """任务管理器（单例）。"""

    def __init__(self) -> None:
        self.jobs_dir = settings.data_dir / "jobs"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self._processes: Dict[str, subprocess.Popen] = {}

    def _job_file(self, job_id: str) -> Path:
        return self.jobs_dir / f"{job_id}.json"

    def _save(self, job: GaussianJob) -> None:
        with open(self._job_file(job.job_id), "w", encoding="utf-8") as f:
            json.dump(asdict(job), f, ensure_ascii=False, indent=2)

    def _load(self, job_id: str) -> Optional[GaussianJob]:
        path = self._job_file(job_id)
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return GaussianJob(**data)

    def list_jobs(self, limit: int = 50) -> List[Dict]:
        """列出所有任务（按创建时间倒序）。"""
        files = sorted(self.jobs_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        jobs = []
        for f in files[:limit]:
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    jobs.append(json.load(fh))
            except Exception:
                continue
        return jobs

    @staticmethod
    def _log_normal_termination(log_path: str) -> bool:
        """读取日志判断是否 Normal termination（统一终态判据，避免各函数各判各的）。"""
        try:
            p = Path(log_path)
            if not p.exists():
                return False
            text = p.read_text(encoding="utf-8", errors="ignore")
            return "Normal termination of Gaussian" in text
        except Exception:
            return False

    def _finalize_if_dead(self, job: GaussianJob) -> bool:
        """若 running 任务的进程已退出，按日志落为 completed/failed 并释放 lease。

        返回 True 表示本次判定为已结束（调用方据此不再视为 running）。
        """
        if job.status != "running":
            return False
        if job.pid and self._pid_alive(job.pid):
            return False
        # 进程已退出：以日志 Normal termination 为准，而不是无条件判 failed（M1）
        job.finished_at = time.time()
        if self._log_normal_termination(job.log_path):
            job.status = "completed"
            job.error = None
        else:
            job.status = "failed"
            job.error = "进程已退出但日志未检测到 Normal termination"
        self._release_lease(job.job_id)
        self._save(job)
        return True

    def _release_lease(self, owner_id: str) -> None:
        """安全释放本 owner 持有的计算 lease（无持有则无副作用）。"""
        try:
            chem_scheduler.release(owner_id)
        except Exception:
            pass

    def has_running(self) -> bool:
        """是否有任务在运行（检查进程存活；顺带把已死任务落终态）。"""
        for job in self.list_jobs():
            if job["status"] != "running" or not job.get("pid"):
                continue
            j = self._load(job["job_id"])
            if not j:
                continue
            if self._pid_alive(j.pid):
                return True
            self._finalize_if_dead(j)
        return False

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        """检查进程是否存活（委托给统一的 process_utils.pid_alive）。"""
        return pid_alive(pid)

    def reconcile(self) -> Dict[str, int]:
        """后端启动时调用：扫描持久化的 running 任务，接管或清理。

        - PID 存活：adopt 为 running（不重复启动，保留原进程）
        - PID 已死：读 log 判断 completed / failed

        Returns:
            {"adopted": n, "completed": n, "failed": n}
        """
        stats = {"adopted": 0, "completed": 0, "failed": 0}
        for job_data in self.list_jobs():
            if job_data.get("status") != "running":
                continue
            job_id = job_data["job_id"]
            pid = job_data.get("pid")
            job = self._load(job_id)
            if not job:
                continue

            if pid and self._pid_alive(pid):
                # 进程还活着：接管（adopt），不重复启动，保留原 Gaussian 进程
                job.status = "running"
                self._processes[job_id] = None  # 无 Popen 句柄，但标记为被接管
                # 重启后内存 lease 丢失，重新为该任务占用 gaussian lease（B1）；
                # 若已被别的任务占用则不抢占，仅保留任务记录。
                try:
                    chem_scheduler.acquire(job_id, "gaussian")
                except ResourceBusyError:
                    pass
                stats["adopted"] += 1
            else:
                # 进程已死：根据 log 判断结果
                job.finished_at = time.time()
                log_path = Path(job.log_path)
                if log_path.exists():
                    try:
                        log_text = log_path.read_text(encoding="utf-8", errors="ignore")
                        if "Normal termination" in log_text:
                            job.status = "completed"
                            stats["completed"] += 1
                        else:
                            job.status = "failed"
                            job.error = "后端重启时进程已终止，日志未检测到 Normal termination"
                            stats["failed"] += 1
                    except Exception:
                        job.status = "failed"
                        job.error = "后端重启时进程已终止，日志读取失败"
                        stats["failed"] += 1
                else:
                    job.status = "failed"
                    job.error = "后端重启时进程已终止，日志文件不存在"
                    stats["failed"] += 1
            self._save(job)
        return stats

    def submit(self, job_name: str, gjf_content: str, mem: Optional[str] = None,
               nproc: Optional[int] = None) -> Dict:
        """提交一个 Gaussian 任务（串行：统一 lease 互斥，若有运行中任务则拒绝）。

        返回任务信息字典。
        """
        # M6: 内存 hard 阈值时拒绝新任务（不杀已有进程）
        from .memory_guard import memory_guard
        if not memory_guard.can_accept_compute():
            snap = memory_guard.snapshot()
            return {
                "ok": False,
                "error": (
                    f"后端内存已达 hard 阈值（RSS {snap['rss_mb']}MB >= {snap['hard_mb']}MB），"
                    "为保护运行中的计算与系统内存，暂不接受新 Gaussian 任务。"
                    "请等待后端释放或重启后端（正在运行的任务会被 reconcile 接管）。"
                ),
            }

        # 重启孤儿兜底：内存 lease 可能为空，但持久化记录的 Gaussian 仍存活
        if self.has_running():
            return {"ok": False, "error": "已有 Gaussian 任务在运行，必须串行执行。请等待当前任务完成后再提交。"}

        job_id = uuid.uuid4().hex[:12]
        safe_name = re.sub(r"[^\w\-.]", "_", job_name.strip()) or "gaussian_job"
        gjf_path = settings.work_dir / f"{safe_name}_{job_id}.gjf"
        log_path = settings.work_dir / f"{safe_name}_{job_id}.log"
        chk_path = settings.work_dir / f"{safe_name}_{job_id}.chk"

        # B7: 提交边界校验 GJF（原子数 / 资源 / 电荷多重度），禁止原文绕过
        from .gaussian_input import validate_gjf
        try:
            validate_gjf(gjf_content, max_atoms=settings.max_atoms)
        except ValueError as e:
            return {"ok": False, "error": f"GJF 校验未通过：{e}"}

        # B1: 原子获取 gaussian lease（scheduler 内部加锁，杜绝并发请求同时通过检查）
        try:
            chem_scheduler.acquire(job_id, "gaussian")
        except ResourceBusyError as e:
            return {"ok": False, "error": f"计算资源被占用，无法提交：{e}"}

        # 写入 gjf（替换 %chk 路径为实际路径）
        content = gjf_content
        content = re.sub(r"%chk=.*", f"%chk={chk_path}", content)
        with open(gjf_path, "w", encoding="utf-8") as f:
            f.write(content)

        job = GaussianJob(
            job_id=job_id,
            job_name=safe_name,
            status="pending",
            gjf_path=str(gjf_path),
            log_path=str(log_path),
            chk_path=str(chk_path),
        )

        # 启动 g16.exe
        try:
            # Windows: g16.exe input.gjf output.log
            cmd = [settings.gaussian_exe, str(gjf_path), str(log_path)]
            creationflags = 0
            if os.name == "nt":
                # CREATE_NO_WINDOW + CREATE_NEW_PROCESS_GROUP：
                # B2 —— 让 Gaussian 脱离后端控制台组，后端被 terminate 时不连带 Gaussian。
                creationflags = subprocess.CREATE_NO_WINDOW | 0x00000200
            proc = subprocess.Popen(
                cmd,
                cwd=str(settings.work_dir),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
            job.pid = proc.pid
            job.status = "running"
            job.started_at = time.time()
            self._processes[job_id] = proc
            self._save(job)
            return {"ok": True, "job": asdict(job)}
        except FileNotFoundError:
            self._release_lease(job_id)
            job.status = "failed"
            job.error = f"Gaussian 可执行文件未找到：{settings.gaussian_exe}"
            self._save(job)
            return {"ok": False, "error": job.error, "job": asdict(job)}
        except Exception as exc:
            self._release_lease(job_id)
            job.status = "failed"
            job.error = f"启动失败：{exc}"
            self._save(job)
            return {"ok": False, "error": job.error, "job": asdict(job)}

    def get_job(self, job_id: str, log_tail_lines: int = 30) -> Optional[Dict]:
        """获取任务状态（含实时解析）。"""
        job = self._load(job_id)
        if not job:
            return None

        # 若标记 running 但进程已死，用统一判据落终态（M1，含 lease 释放）
        if job.status == "running":
            self._finalize_if_dead(job)

        # 读取 log 尾部并解析当前进度
        if Path(job.log_path).exists():
            try:
                log_text = Path(job.log_path).read_text(encoding="utf-8", errors="ignore")
                lines = log_text.splitlines()
                job.log_tail = "\n".join(lines[-log_tail_lines:])
                # 当前优化步数
                step_matches = re.findall(r"Optimization cycle\s+(\d+)", log_text)
                if step_matches:
                    job.current_step = int(step_matches[-1])
                # 最新能量
                energy_matches = re.findall(r"SCF Done:\s+E\(\S+\)\s*=\s*(-?[\d.]+)", log_text)
                if energy_matches:
                    job.last_energy = float(energy_matches[-1])
            except Exception:
                pass

        return asdict(job)

    def stop_job(self, job_id: str) -> Dict:
        """停止任务。"""
        job = self._load(job_id)
        if not job:
            return {"ok": False, "error": "任务不存在"}
        if job.status != "running":
            return {"ok": False, "error": f"任务状态为 {job.status}，无法停止"}

        # B9: 终止进程树（g16.exe 可能有子进程 l101.exe 等），并复核进程确实消失，
        # 未确认结束不得写入 stopped，避免 taskkill 失败/PID 复用时误报成功。
        target_pid = job.pid
        kill_ok = False
        if target_pid:
            try:
                result = subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(target_pid)],
                    capture_output=True, text=True, timeout=10,
                )
                kill_ok = (result.returncode == 0)
            except Exception:
                try:
                    os.kill(target_pid, signal.SIGTERM)
                    kill_ok = True
                except Exception:
                    kill_ok = False

            # 轮询最多 5 秒，确认目标 PID 已退出
            gone = False
            for _ in range(10):
                if not self._pid_alive(target_pid):
                    gone = True
                    break
                time.sleep(0.5)
            if not gone:
                # 进程仍存活：不谎报 stopped，保留 running 并返回失败
                return {
                    "ok": False,
                    "error": (
                        f"停止未确认：PID {target_pid} 在 {result.stderr.strip() if kill_ok else 'taskkill 失败'} 后仍存活，"
                        "请人工检查该进程，避免误杀其他程序。"
                    ),
                    "job": asdict(job),
                }

        self._release_lease(job_id)
        job.status = "stopped"
        job.finished_at = time.time()
        self._save(job)
        if job_id in self._processes:
            del self._processes[job_id]
        return {"ok": True, "job": asdict(job)}


# 延迟 import re（在文件顶部更规范，但这里保持简洁）
import re  # noqa: E402

job_manager = JobManager()
