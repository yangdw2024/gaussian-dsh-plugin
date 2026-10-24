"""Gaussian 任务管理器：提交、监控、停止、串行队列。

用户硬约束：严禁并行多任务，必须串行。提交时若有任务在运行则拒绝。
任务信息持久化到 data_dir/jobs/<job_id>.json。
"""
from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import time
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("gaussian-dsh-backend")

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
        # R5a: Popen 成功后的运行态 job 对象（磁盘主记录可能因写盘失败仍停在 pending/pid=None），
        # 用于当前进程内进程退出时统一 finalize、释放 lease，不依赖磁盘记录。
        self._running_jobs: Dict[str, GaussianJob] = {}

    def _job_file(self, job_id: str) -> Path:
        return self.jobs_dir / f"{job_id}.json"

    def _save(self, job: GaussianJob) -> None:
        with open(self._job_file(job.job_id), "w", encoding="utf-8") as f:
            json.dump(asdict(job), f, ensure_ascii=False, indent=2)

    def _recover_file(self, job_id: str) -> Path:
        return self.jobs_dir / f"{job_id}.recover.json"

    def _write_pid_recover(self, job: GaussianJob) -> bool:
        """R5/R5c: Popen 成功但完整 _save 失败时，落一份最小 pid 恢复记录。
        返回是否成功建立 pid 持久化凭据；失败时调用方应明确标注不可重启恢复，不能假装可恢复。"""
        try:
            data = {
                "job_id": job.job_id,
                "job_name": job.job_name,
                "status": "running",
                "pid": job.pid,
                "pid_start_time": job.pid_start_time,
                "gjf_path": job.gjf_path,
                "log_path": job.log_path,
                "chk_path": job.chk_path,
                "started_at": job.started_at,
                "recover": True,
            }
            with open(self._recover_file(job.job_id), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False

    def _clear_pid_recover(self, job_id: str) -> None:
        try:
            p = self._recover_file(job_id)
            if p.exists():
                p.unlink()
        except Exception:
            pass

    def _load_recover(self, job_id: str) -> Optional[Dict]:
        try:
            p = self._recover_file(job_id)
            if not p.exists():
                return None
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def _load(self, job_id: str) -> Optional[GaussianJob]:
        path = self._job_file(job_id)
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return GaussianJob(**data)

    def list_jobs(self, limit: int = 50) -> List[Dict]:
        """列出所有任务（按创建时间倒序）。R5b: 排除 *.recover.json，避免同一 job 重复出现。"""
        files = [
            p for p in self.jobs_dir.glob("*.json")
            if not p.name.endswith(".recover.json")
        ]
        files = sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)
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
        """R4: 判断任务是否最终成功。

        不能用"整份日志含 Normal termination 子串"——链式任务前段 Link1 成功、后段 Error
        时仍会误报 completed。改为有界尾读最后一段，取【最后一个】termination event：
        只有最后一个是 Normal termination、且其后没有 Error termination 才算成功。
        """
        try:
            p = Path(log_path)
            if not p.exists():
                return False
            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                tail = list(deque(f, maxlen=400))
            text = "\n".join(tail)
            # 按出现位置取最后一个终止标记
            norm_pos = text.rfind("Normal termination of Gaussian")
            err_pos = text.rfind("Error termination")
            if norm_pos == -1:
                return False
            # Error 出现在最后一个 Normal 之后 → 最终失败
            if err_pos != -1 and err_pos > norm_pos:
                return False
            return True
        except Exception:
            return False

    def _finalize_if_dead(self, job: GaussianJob, trust_handle: bool = False) -> bool:
        """若 running 任务的进程已退出，按日志落为 completed/failed 并释放 lease。

        返回 True 表示本次判定为已结束（调用方据此不再视为 running）。
        trust_handle=True 时表示 Popen 句柄 poll() 已确认退出，不再用裸 PID 存活性
        否决（避免 PID 快速复用时误判进程仍存活）。
        """
        if job.status != "running":
            return False
        if not trust_handle and job.pid and self._pid_alive(job.pid):
            # PID 存活时再做实例校验：明确不匹配(False)说明原 Gaussian 已退出、PID 被复用，
            # 落到下面 finalize；True 或 None(不可判定)都保守视为仍在运行，不终结、不释放 lease。
            inst = pid_is_same_instance(job.pid, job.pid_start_time)
            if inst is not False:
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

    def _reap_ram_jobs(self) -> None:
        """R5a: 磁盘主记录写盘失败仍停在 pending/pid=None 时，用内存运行态 job 在进程退出时
        统一终态回收：判 completed/failed、释放 lease、清 recover，避免当前进程内 lease 永久 busy。"""
        done: List[str] = []
        for job_id, job in list(self._running_jobs.items()):
            proc = self._processes.get(job_id)
            try:
                exited = proc is not None and proc.poll() is not None
            except Exception:
                exited = job.pid is not None and not self._pid_alive(job.pid)
            if exited:
                # Popen handle 已确认退出：信任句柄，不用裸 PID 复存活检测否决；
                # 只有真正落终态才清 recover/移出内存，避免 lease 丢失。
                finalized = self._finalize_if_dead(job, trust_handle=True)
                if finalized:
                    self._clear_pid_recover(job_id)
                    done.append(job_id)
        for job_id in done:
            self._running_jobs.pop(job_id, None)
            self._processes.pop(job_id, None)

    def _release_lease(self, owner_id: str) -> None:
        """安全释放本 owner 持有的计算 lease（无持有则无副作用）。"""
        try:
            chem_scheduler.release(owner_id)
        except Exception:
            pass

    @staticmethod
    def _normalize_chk(content: str, chk_path: Path) -> str:
        """R1/N4/R1b: 按每个 --Link1-- 段局部规范化 chk，只调整 %chk 与 %nosave 的相对顺序，
        绝不搬动 %mem/%nproc/%rwf 等其他 Link0 指令（避免改变别的 scratch 文件相对 nosave 的保留语义）。

        - 大小写不敏感替换该段【所有】%chk 行为任务 chk_path；
        - %NoSave 删除其之前命名的 scratch/chk，因此段内保证 %nosave 在 %chk 前；
        - 仅主段（第一段）在缺 chk 时插入，插到最后一个 nosave 之后；其他段不新增 chk。
        """
        chk_line = f"%chk={chk_path}"
        chk_re = re.compile(r"^\s*%chk\s*=", re.IGNORECASE)
        nosave_re = re.compile(r"^\s*%nosave\b", re.IGNORECASE)
        link1_re = re.compile(r"^\s*--link1--\s*$", re.IGNORECASE)

        def fix_seg(seg: List[str], allow_insert: bool) -> List[str]:
            # 1) 替换本段所有 chk 行
            chk_idx = [i for i, l in enumerate(seg) if chk_re.match(l)]
            for i in chk_idx:
                seg[i] = chk_line
            nosave_idx = [i for i, l in enumerate(seg) if nosave_re.match(l)]

            # 2) 仅主段缺 chk 时插入：最后一个 nosave 之后；无 nosave 放到首个 % 指令前
            if not chk_idx and allow_insert:
                if nosave_idx:
                    insert_at = nosave_idx[-1] + 1
                else:
                    insert_at = next(
                        (i for i, l in enumerate(seg) if l.strip().startswith("%")), 0
                    )
                seg.insert(insert_at, chk_line)
                chk_idx = [insert_at]

            # 3) 局部保证 nosave 在 chk 前：若 chk 落在最后一个 nosave 之前，仅把 chk 行移到其后，
            #    其他行（%mem/%nproc/%rwf…）原位不动。
            if nosave_idx and chk_idx:
                last_n = nosave_idx[-1]
                if any(c < last_n for c in chk_idx):
                    moved = [seg[i] for i in chk_idx]
                    for i in sorted(chk_idx, reverse=True):
                        del seg[i]
                    nn = [i for i, l in enumerate(seg) if nosave_re.match(l)]
                    anchor = nn[-1] + 1 if nn else 0
                    for j, cl in enumerate(moved):
                        seg.insert(anchor + j, cl)
            return seg

        # 按 --Link1-- 切块，保留分隔行
        blocks: List[tuple] = []
        cur: List[str] = []
        for ln in content.splitlines():
            if link1_re.match(ln.strip()):
                blocks.append(("seg", cur))
                blocks.append(("sep", [ln]))
                cur = []
            else:
                cur.append(ln)
        blocks.append(("seg", cur))

        out_lines: List[str] = []
        first = True
        for kind, seg in blocks:
            if kind == "sep":
                out_lines.extend(seg)
            else:
                out_lines.extend(fix_seg(seg, allow_insert=first))
                first = False
        return "\n".join(out_lines)

    def has_running(self) -> bool:
        """是否有任务在运行（检查进程存活；顺带把已死任务落终态）。"""
        # R5a: 先用内存运行态回收已退出但磁盘记录写失败的任务，释放 lease
        self._reap_ram_jobs()
        # R5: 内存句柄兜底——磁盘记录因写盘失败停在 pending 时，只要 Popen 句柄仍存活就算占用，
        # 避免第二个 Gaussian 并发提交。
        for proc in self._processes.values():
            try:
                if proc is not None and proc.poll() is None:
                    return True
            except Exception:
                continue
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
        seen: set = set()

        def _adopt_or_finalize(job: GaussianJob, pid: Optional[int]) -> None:
            # R5a/R9: PID 实例三态，不能把 None(不可判定) 当成"不匹配"：
            #   same_instance is False → 明确 PID 被复用，按原进程已结束 finalize；
            #   same_instance is True  → 确属原 Gaussian，adopt + 重新占 lease；
            #   same_instance is None  → 创建时间缺失/取不到，不可判定，【保守视为仍运行】，
            #                            同样 adopt + 占 lease，只记 warning，绝不误判结束放行第二个 Gaussian。
            alive = bool(pid and self._pid_alive(pid))
            same_instance = (
                pid_is_same_instance(pid, job.pid_start_time) if alive else False
            )
            if alive and same_instance is not False:
                # 进程还活着（实例确认或不可判定）：接管，不重复启动
                job.status = "running"
                self._processes[job.job_id] = None  # 无 Popen 句柄，但标记为被接管
                # 重启后内存 lease 丢失，重新为该任务占用 gaussian lease（B1）；
                # 若已被别的任务占用则不抢占，仅保留任务记录。
                try:
                    chem_scheduler.acquire(job.job_id, "gaussian")
                except ResourceBusyError:
                    pass
                stats["adopted"] += 1
                if same_instance is None:
                    logger.warning(
                        "Job %s: PID %d 存活但创建时间不可校验，保守视为原 Gaussian 仍在运行并保留 lease",
                        job.job_id, pid,
                    )
            else:
                # 不存活，或明确 PID 复用：按原进程已结束，统一终态判据（最后一个 Normal/Error），
                # 不把前序 Link1 的正常结束误当成整任务成功。
                job.finished_at = time.time()
                if self._log_normal_termination(job.log_path):
                    job.status = "completed"
                    job.error = None
                    stats["completed"] += 1
                else:
                    job.status = "failed"
                    job.error = "后端重启时进程已终止/疑似PID复用，日志未检测到完整 Normal termination"
                    stats["failed"] += 1
            self._save(job)
            self._clear_pid_recover(job.job_id)

        # 主 JSON 记录：非 running/缺 pid 时用 R5 最小恢复文件补齐
        for job_data in self.list_jobs():
            job_id = job_data["job_id"]
            seen.add(job_id)
            job = self._load(job_id)
            rec = self._load_recover(job_id)
            if job is None:
                # 主记录缺失但有 recover：用 recover 重建一个可接管的 job
                if rec:
                    job = GaussianJob(
                        job_id=job_id,
                        job_name=rec.get("job_name", "recovered"),
                        status="running",
                        gjf_path=rec.get("gjf_path", ""),
                        log_path=rec.get("log_path", ""),
                        chk_path=rec.get("chk_path", ""),
                        pid=rec.get("pid"),
                        pid_start_time=rec.get("pid_start_time"),
                        started_at=rec.get("started_at"),
                    )
                else:
                    continue
            else:
                # R5: recover 只补 pending 或 running+缺 pid；终态（completed/failed/stopped）
                # 主记录永远优先，绝不用 stale recover 把已结束任务复活成 running、重新占 lease。
                if rec and job.status == "pending" and not job.pid:
                    job.pid = rec.get("pid") or job.pid
                    job.pid_start_time = rec.get("pid_start_time") or job.pid_start_time
                    job.log_path = rec.get("log_path") or job.log_path
                    job.gjf_path = rec.get("gjf_path") or job.gjf_path
                    job.chk_path = rec.get("chk_path") or job.chk_path
                    job.status = "running"
                elif rec and job.status == "running" and not job.pid:
                    job.pid = rec.get("pid") or job.pid
                    job.pid_start_time = rec.get("pid_start_time") or job.pid_start_time
                elif rec:
                    # 终态主记录 + 残留 recover：清掉残留，不复活
                    self._clear_pid_recover(job_id)
            if job.status != "running" or not job.pid:
                continue
            _adopt_or_finalize(job, job.pid)

        # 仅有 recover 文件、主 JSON 都不存在的极端孤儿
        for p in self.jobs_dir.glob("*.recover.json"):
            rid = p.name[: -len(".recover.json")]
            if rid in seen:
                continue
            rec = self._load_recover(rid)
            if not rec or not rec.get("pid"):
                continue
            job = GaussianJob(
                job_id=rid,
                job_name=rec.get("job_name", "recovered"),
                status="running",
                gjf_path=rec.get("gjf_path", ""),
                log_path=rec.get("log_path", ""),
                chk_path=rec.get("chk_path", ""),
                pid=rec.get("pid"),
                pid_start_time=rec.get("pid_start_time"),
                started_at=rec.get("started_at"),
            )
            _adopt_or_finalize(job, job.pid)
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

        # N2/R5: 统一事务边界。lease 与"是否真的启动了进程"绑定：
        # - Popen 之前任何失败（写文件、构造命令、exe 缺失）→ 未启动，释放 lease 记 failed；
        # - Popen 成功后（含随后 _save 失败）→ Gaussian 已在跑，【绝不释放 lease】，
        #   否则会允许第二个 Gaussian 并发。
        # R5: 先落一条 pending 持久化——即使 running 状态两次保存都失败，JSON 记录仍在，
        # reconcile/终态扫描能按 pid 找到它并最终释放 lease，不会永久 busy 或重启丢失。
        proc_started = False
        try:
            self._save(job)
            # R1/N4: 规范化 %Chk 路径并保证 %NoSave 在 %Chk 前
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
            self._running_jobs[job_id] = job  # R5a: 内存运行态，供当前进程终态回收 lease
            # R5/R5c: 先落完整 running 记录；失败则写最小 pid 恢复文件；两者都失败须如实标注
            try:
                self._save(job)
                self._clear_pid_recover(job_id)
            except Exception:
                if not self._write_pid_recover(job):
                    job.error = "运行状态与恢复凭据均写盘失败：进程仍在运行，但重启后可能无法接管"
            return {"ok": True, "job": asdict(job)}
        except Exception as exc:
            if proc_started:
                # 进程已在运行：保留 lease，绝不释放；即便完整记录写盘失败，也落最小 pid 恢复文件
                job.status = "running"
                self._running_jobs[job_id] = job
                try:
                    self._save(job)
                    self._clear_pid_recover(job_id)
                except Exception:
                    if not self._write_pid_recover(job):
                        job.error = f"启动后状态与恢复凭据写盘失败（进程仍在运行，重启后可能丢失）：{exc}"
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
        # R5a: 先回收已退出的内存运行态任务，再读取
        self._reap_ram_jobs()
        job = self._load(job_id)
        # R5a: 磁盘主记录写盘失败停在 pending 时，用内存运行态对象返回真实状态
        if job_id in self._running_jobs:
            job = self._running_jobs[job_id]
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
        # R5a: 主记录写盘失败仍停在 pending/pid=None 时，用内存运行态对象接管停止；
        # 内存对象才是真实的 running+pid 来源。
        ram_job = self._running_jobs.get(job_id)
        if ram_job is not None:
            job = ram_job
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
        # R5a: 停止成功后同步清理内存跟踪与 recover，避免 get_job 用残留的内存 running
        # 对象覆盖磁盘 stopped 状态、并再次 finalize 成 failed/completed。
        self._processes.pop(job_id, None)
        self._running_jobs.pop(job_id, None)
        self._clear_pid_recover(job_id)
        return {"ok": True, "job": asdict(job)}


# 延迟 import re（在文件顶部更规范，但这里保持简洁）
import re  # noqa: E402

job_manager = JobManager()
