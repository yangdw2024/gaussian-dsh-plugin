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
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .config import settings
from .gaussian_output import parse_gaussian_log
from .process_utils import pid_alive, kill_process_tree, pid_is_same_instance, pid_create_time
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
    pid_start_time: Optional[float] = None  # B9: 提交时记录进程创建时间，防 PID 复用误杀
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
    def _tail_lines(path: Path, n: int) -> List[str]:
        """N11: 有界尾读，只保留最后 n 行，避免大日志整份读入内存。"""
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return list(deque(f, maxlen=n))
        except Exception:
            return []

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

    @staticmethod
    def _normalize_chk(content: str, chk_path: Path) -> str:
        """N4: 大小写不敏感地规范化 %Chk 行（%chk/%Chk/%CHK 都识别），统一改写为任务实际 chk 路径；
        原文没有 %Chk 时插入到首个 Link0(% 指令)前，避免写到别处或覆盖已有 chk。
        """
        chk_line = f"%chk={chk_path}"
        lines = content.splitlines()
        for i, ln in enumerate(lines):
            if re.match(r"\s*%chk\s*=", ln, re.IGNORECASE):
                lines[i] = chk_line
                break
        else:
            idx = next((i for i, l in enumerate(lines) if l.strip().startswith("%")), 0)
            lines.insert(idx, chk_line)
        return "\n".join(lines)

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
                # M1: 进程已死：复用与 _finalize_if_dead 完全相同的统一判据
                # （完整串 "Normal termination of Gaussian"），避免各函数各判各的、
                # 把前序 Link1 的正常结束误当成整任务成功。
                job.finished_at = time.time()
                if self._log_normal_termination(job.log_path):
                    job.status = "completed"
                    job.error = None
                    stats["completed"] += 1
                else:
                    job.status = "failed"
                    job.error = "后端重启时进程已终止，日志未检测到完整 Normal termination"
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

        job = GaussianJob(
            job_id=job_id,
            job_name=safe_name,
            status="pending",
            gjf_path=str(gjf_path),
            log_path=str(log_path),
            chk_path=str(chk_path),
        )

        # N2: 统一事务边界。lease 与"是否真的启动了进程"绑定：
        # - Popen 之前任何失败（写文件、构造命令、exe 缺失）→ 未启动，释放 lease 记 failed；
        # - Popen 成功后（含随后 _save 失败）→ Gaussian 已在跑，【绝不释放 lease】，
        #   否则会允许第二个 Gaussian 并发；只记录异常，进程交由 reconcile 接管。
        proc_started = False
        try:
            # N4: 大小写不敏感规范化 %Chk 路径
            content = self._normalize_chk(gjf_content, chk_path)
            with open(gjf_path, "w", encoding="utf-8") as f:
                f.write(content)

            # Windows: g16.exe input.gjf output.log
            cmd = [settings.gaussian_exe, str(gjf_path), str(log_path)]
            creationflags = 0
            if os.name == "nt":
                # CREATE_NO_WINDOW；CREATE_NEW_PROCESS_GROUP 只用于与后端控制台解耦，
                # 注意它不等于 CREATE_BREAKAWAY_FROM_JOB，不能当作脱离 DSH Job Object 的保证。
                creationflags = subprocess.CREATE_NO_WINDOW | 0x00000200
            proc = subprocess.Popen(
                cmd,
                cwd=str(settings.work_dir),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
            proc_started = True
            job.pid = proc.pid
            # B9: best-effort 记录进程创建时间，停止时用于识别 PID 是否被复用
            job.pid_start_time = pid_create_time(proc.pid)
            job.status = "running"
            job.started_at = time.time()
            self._processes[job_id] = proc
            # _save 失败不回滚 lease：进程已启动，不能让第二个 Gaussian 并发。
            self._save(job)
            return {"ok": True, "job": asdict(job)}
        except Exception as exc:
            if proc_started:
                # 进程已在运行：保留 lease，仅把状态异常记到日志，仍按已启动返回。
                job.status = "running"
                job.error = f"启动后状态记录异常（进程仍在运行）：{exc}"
                try:
                    self._save(job)
                except Exception:
                    pass
                return {"ok": True, "job": asdict(job)}
            # 进程未启动：安全释放 lease，记 failed。
            self._release_lease(job_id)
            job.status = "failed"
            job.error = f"启动失败：{exc}"
            try:
                self._save(job)
            except Exception:
                pass
            return {"ok": False, "error": job.error, "job": asdict(job)}

    def get_job(self, job_id: str, log_tail_lines: int = 30) -> Optional[Dict]:
        """获取任务状态（含实时解析）。"""
        job = self._load(job_id)
        if not job:
            return None

        # 若标记 running 但进程已死，用统一判据落终态（M1，含 lease 释放）
        if job.status == "running":
            self._finalize_if_dead(job)

        # N11: log_tail_lines<=0 表示调用方不要日志尾部，直接返回空、不读整份日志；
        # >0 时用有界尾读，只取最后 n 行做进度/能量解析，避免大日志整份加载。
        if log_tail_lines and log_tail_lines > 0 and Path(job.log_path).exists():
            try:
                tail = self._tail_lines(Path(job.log_path), log_tail_lines)
                job.log_tail = "\n".join(tail)
                window = "\n".join(tail)
                # 当前优化步数（尾部窗口内最新值）
                step_matches = re.findall(r"Optimization cycle\s+(\d+)", window)
                if step_matches:
                    job.current_step = int(step_matches[-1])
                # 最新能量（尾部窗口内最新值）
                energy_matches = re.findall(r"SCF Done:\s+E\(\S+\)\s*=\s*(-?[\d.]+)", window)
                if energy_matches:
                    job.last_energy = float(energy_matches[-1])
            except Exception:
                pass
        else:
            job.log_tail = ""

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
        # N8: 统一初始化错误信息变量，杜绝回退路径引用未赋值的 result 造成 UnboundLocalError。
        target_pid = job.pid
        kill_detail = "未执行终止"
        kill_ok = False
        if target_pid:
            # B9: 先做 PID 实例身份核对；创建时间不符说明 PID 已被复用，拒绝终止以免误杀
            identity = pid_is_same_instance(target_pid, job.pid_start_time)
            if identity is False:
                return {
                    "ok": False,
                    "error": (
                        f"PID {target_pid} 的创建时间与提交记录不符，疑似 PID 已被其他程序复用，"
                        "为避免误杀已跳过终止，请人工核对该进程。"
                    ),
                    "job": asdict(job),
                }
            try:
                result = subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(target_pid)],
                    capture_output=True, text=True, timeout=10,
                )
                kill_ok = (result.returncode == 0)
                kill_detail = (result.stderr or result.stdout or "taskkill").strip()
            except Exception as tk_exc:
                # taskkill 抛异常（如找不到命令）：尝试 POSIX 信号兜底
                try:
                    os.kill(target_pid, signal.SIGTERM)
                    kill_ok = True
                    kill_detail = f"taskkill 不可用，已尝试 os.kill：{tk_exc}"
                except Exception as kill_exc:
                    kill_ok = False
                    kill_detail = f"taskkill 与 os.kill 均失败：{tk_exc}; {kill_exc}"

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
                        f"停止未确认：PID {target_pid} 在{kill_detail or '终止操作'}后仍存活，"
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
