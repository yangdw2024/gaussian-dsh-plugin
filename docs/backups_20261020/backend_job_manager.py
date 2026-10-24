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

    def has_running(self) -> bool:
        """是否有任务在运行（检查进程存活）。"""
        for job in self.list_jobs():
            if job["status"] == "running" and job.get("pid"):
                if self._pid_alive(job["pid"]):
                    return True
                # 进程已死但状态还是 running，修正为 failed
                j = self._load(job["job_id"])
                if j:
                    j.status = "failed"
                    j.error = "进程意外终止"
                    j.finished_at = time.time()
                    self._save(j)
        return False

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def submit(self, job_name: str, gjf_content: str, mem: Optional[str] = None,
               nproc: Optional[int] = None) -> Dict:
        """提交一个 Gaussian 任务（串行：若有运行中任务则拒绝）。

        返回任务信息字典。
        """
        if self.has_running():
            return {"ok": False, "error": "已有 Gaussian 任务在运行，必须串行执行。请等待当前任务完成后再提交。"}

        job_id = uuid.uuid4().hex[:12]
        safe_name = re.sub(r"[^\w\-.]", "_", job_name.strip()) or "gaussian_job"
        gjf_path = settings.work_dir / f"{safe_name}_{job_id}.gjf"
        log_path = settings.work_dir / f"{safe_name}_{job_id}.log"
        chk_path = settings.work_dir / f"{safe_name}_{job_id}.chk"

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
            proc = subprocess.Popen(
                cmd,
                cwd=str(settings.work_dir),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            job.pid = proc.pid
            job.status = "running"
            job.started_at = time.time()
            self._processes[job_id] = proc
            self._save(job)
            return {"ok": True, "job": asdict(job)}
        except FileNotFoundError:
            job.status = "failed"
            job.error = f"Gaussian 可执行文件未找到：{settings.gaussian_exe}"
            self._save(job)
            return {"ok": False, "error": job.error, "job": asdict(job)}
        except Exception as exc:
            job.status = "failed"
            job.error = f"启动失败：{exc}"
            self._save(job)
            return {"ok": False, "error": job.error, "job": asdict(job)}

    def get_job(self, job_id: str, log_tail_lines: int = 30) -> Optional[Dict]:
        """获取任务状态（含实时解析）。"""
        job = self._load(job_id)
        if not job:
            return None

        # 若标记 running 但进程已死，修正状态
        if job.status == "running":
            if job.pid and not self._pid_alive(job.pid):
                job.status = "completed" if Path(job.log_path).exists() else "failed"
                job.finished_at = time.time()
                # 检查是否正常结束
                if Path(job.log_path).exists():
                    log_text = Path(job.log_path).read_text(encoding="utf-8", errors="ignore")
                    if "Normal termination" not in log_text:
                        job.status = "failed"
                        job.error = "进程结束但日志中未检测到 Normal termination"
                self._save(job)

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

        # 终止进程树（g16.exe 可能有子进程 l101.exe 等）
        if job.pid:
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(job.pid)],
                    capture_output=True, timeout=10,
                )
            except Exception:
                try:
                    os.kill(job.pid, signal.SIGTERM)
                except Exception:
                    pass

        job.status = "stopped"
        job.finished_at = time.time()
        self._save(job)
        if job_id in self._processes:
            del self._processes[job_id]
        return {"ok": True, "job": asdict(job)}


# 延迟 import re（在文件顶部更规范，但这里保持简洁）
import re  # noqa: E402

job_manager = JobManager()
