"""后处理任务管理器。

统一管理 Multiwfn/VMD 后处理任务，使用 ChemComputeScheduler 保证互斥。
任务信息持久化到 data_dir/postprocess/<task_id>.json。
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from ..config import settings
from ..resource_scheduler import chem_scheduler, ResourceBusyError
from .gaussian_tools import ensure_fchk
from .models import ArtifactInfo, PostprocessRequest, PostprocessTask
from .multiwfn import (
    generate_esp_cube_commands,
    generate_orbital_cube_commands,
    load_profile,
)


class PostprocessManager:
    """后处理任务管理器（单例）。"""

    def __init__(self) -> None:
        self.tasks_dir = settings.data_dir / "postprocess"
        self.tasks_dir.mkdir(parents=True, exist_ok=True)

    def _task_file(self, task_id: str) -> Path:
        return self.tasks_dir / f"{task_id}.json"

    def _save(self, task: PostprocessTask) -> None:
        with open(self._task_file(task.task_id), "w", encoding="utf-8") as f:
            json.dump(task.model_dump(), f, ensure_ascii=False, indent=2)

    def _load(self, task_id: str) -> Optional[PostprocessTask]:
        path = self._task_file(task_id)
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return PostprocessTask(**data)

    def list_tasks(self, limit: int = 50) -> List[Dict]:
        """列出所有后处理任务。"""
        files = sorted(self.tasks_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        tasks = []
        for f in files[:limit]:
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    tasks.append(json.load(fh))
            except Exception:
                continue
        return tasks

    def get_task(self, task_id: str) -> Optional[Dict]:
        """获取任务状态。"""
        task = self._load(task_id)
        if not task:
            return None
        return task.model_dump()

    # 三档网格对应的估算网格点数（16Å 立方盒子的粗估，用于提前拒绝超限配置）
    _GRID_EST_POINTS = {
        "coarse": 262_000,
        "medium": 1_200_000,
        "fine": 4_100_000,
    }

    def _check_grid_points(self, req: PostprocessRequest) -> None:
        """M6c: 网格点数提前预检，超过 postprocess_max_grid_points 直接拒绝。"""
        est = self._GRID_EST_POINTS.get(req.grid, self._GRID_EST_POINTS["medium"])
        cap = settings.postprocess_max_grid_points
        if est > cap:
            raise ValueError(
                f"网格档位 '{req.grid}' 估算约 {est:,} 点，超过上限 {cap:,} 点；"
                f"请改用更粗网格（coarse/medium）。"
            )

    def create_task(self, req: PostprocessRequest) -> PostprocessTask:
        """创建后处理任务。

        注意：此方法只创建任务记录，不实际执行。
        实际执行由 run_task() 完成。
        """
        task_id = uuid.uuid4().hex[:12]
        task = PostprocessTask(
            task_id=task_id,
            kind=req.kind,
            status="pending",
            created_at=time.time(),
        )
        self._save(task)
        return task

    def resolve_source(self, req: PostprocessRequest) -> Path:
        """解析输入源：chk_path / fchk_path / job_id → fchk 路径。"""
        # 直接指定 fchk
        if req.fchk_path:
            p = Path(req.fchk_path)
            if not p.exists():
                raise FileNotFoundError(f"fchk 文件不存在：{p}")
            return p

        # 直接指定 chk（自动 formchk）
        if req.chk_path:
            p = Path(req.chk_path)
            return ensure_fchk(p)

        # 从 Gaussian job_id 解析
        if req.job_id:
            from ..job_manager import job_manager
            job = job_manager.get_job(req.job_id, log_tail_lines=0)
            if not job:
                raise ValueError(f"Gaussian 任务不存在：{req.job_id}")
            if not job.get("normal_termination", False) and job.get("status") != "completed":
                raise ValueError(f"Gaussian 任务 {req.job_id} 未完成，无法后处理")
            chk_path = Path(job["chk_path"])
            return ensure_fchk(chk_path)

        raise ValueError("必须提供 fchk_path / chk_path / job_id 之一")

    def run_task(self, task_id: str, req: PostprocessRequest) -> Dict:
        """执行后处理任务。

        使用 ChemComputeScheduler 获取 lease，执行 Multiwfn/VMD 流水线。
        """
        task = self._load(task_id)
        if not task:
            return {"ok": False, "error": "任务不存在"}

        # M6: 内存 hard 阈值时拒绝新后处理（不杀已有进程）
        from ..memory_guard import memory_guard
        if not memory_guard.can_accept_compute():
            snap = memory_guard.snapshot()
            task.status = "failed"
            task.error = (
                f"后端内存达 hard 阈值（RSS {snap['rss_mb']}MB >= {snap['hard_mb']}MB），"
                "暂不接受新后处理任务。"
            )
            task.finished_at = time.time()
            self._save(task)
            return {"ok": False, "error": task.error, "task": task.model_dump()}

        # M6c: 网格点数提前预检（避免大网格在 15GB 内存下跑爆）
        try:
            self._check_grid_points(req)
        except ValueError as e:
            task.status = "failed"
            task.error = str(e)
            task.finished_at = time.time()
            self._save(task)
            return {"ok": False, "error": str(e), "task": task.model_dump()}

        # 获取计算资源 lease
        try:
            lease = chem_scheduler.acquire(task_id, "multiwfn")
        except ResourceBusyError as e:
            task.status = "failed"
            task.error = str(e)
            self._save(task)
            return {"ok": False, "error": str(e), "task": task.model_dump()}

        try:
            task.status = "running"
            task.started_at = time.time()
            self._save(task)

            # 解析输入源
            fchk_path = self.resolve_source(req)
            task.source = str(fchk_path)
            self._save(task)

            # 加载 profile
            profile = load_profile()

            # 创建任务工作目录
            work_dir = settings.work_dir / f"postproc_{task_id}"
            work_dir.mkdir(parents=True, exist_ok=True)

            artifacts: List[ArtifactInfo] = []

            if req.kind == "orbitals":
                # 确定轨道编号
                orbitals = req.orbitals or []
                if req.orbital_labels:
                    from ..fchk_reader import read_fchk_orbital_info
                    orb_info = read_fchk_orbital_info(fchk_path)
                    for label in req.orbital_labels:
                        if label == "HOMO":
                            orbitals.append(orb_info.homo_alpha_index + 1)  # 1-based
                        elif label == "LUMO":
                            orbitals.append(orb_info.lumo_alpha_index + 1)
                if not orbitals:
                    # 默认 HOMO, LUMO
                    from ..fchk_reader import read_fchk_orbital_info
                    orb_info = read_fchk_orbital_info(fchk_path)
                    orbitals = [orb_info.homo_alpha_index + 1, orb_info.lumo_alpha_index + 1]

                # 生成 Multiwfn 命令
                commands = generate_orbital_cube_commands(orbitals, req.grid, profile)

                # TODO: 实际调用 Multiwfn 执行
                # 这里先记录命令，实际执行在 M3 完成 VMD 后一起测试
                cmd_file = work_dir / "multiwfn_commands.txt"
                cmd_file.write_text(commands, encoding="utf-8")

                task.logs = f"轨道 cube 命令已生成（待 Multiwfn 执行）：轨道 {orbitals}\n命令文件：{cmd_file}"

            elif req.kind == "esp":
                commands = generate_esp_cube_commands(req.grid, profile)
                cmd_file = work_dir / "multiwfn_commands.txt"
                cmd_file.write_text(commands, encoding="utf-8")
                task.logs = f"ESP 双 cube 命令已生成（待 Multiwfn 执行）\n命令文件：{cmd_file}"

            elif req.kind == "rdg":
                from .multiwfn import generate_rdg_cube_commands
                commands = generate_rdg_cube_commands(profile=profile)
                cmd_file = work_dir / "multiwfn_commands.txt"
                cmd_file.write_text(commands, encoding="utf-8")
                task.logs = f"RDG/NCI 命令已生成（待 Multiwfn 执行）\n命令文件：{cmd_file}"

            elif req.kind == "mo_levels":
                from ..fchk_reader import read_fchk_orbital_info, generate_mo_level_svg
                orb_info = read_fchk_orbital_info(fchk_path)
                svg = generate_mo_level_svg(orb_info)
                svg_path = work_dir / "mo_levels.svg"
                svg_path.write_text(svg, encoding="utf-8")
                artifacts.append(ArtifactInfo(
                    name="mo_levels.svg",
                    path=str(svg_path),
                    kind="image/svg+xml",
                    size_bytes=svg_path.stat().st_size,
                ))
                task.logs = f"MO 能级图已生成：HOMO={orb_info.homo_energy:.4f}, LUMO={orb_info.lumo_energy:.4f}, gap={orb_info.gap:.4f} eV"

            task.status = "completed"
            task.finished_at = time.time()
            task.artifacts = artifacts
            self._save(task)

            return {"ok": True, "task": task.model_dump()}

        except Exception as e:
            task.status = "failed"
            task.error = str(e)
            task.finished_at = time.time()
            self._save(task)
            return {"ok": False, "error": str(e), "task": task.model_dump()}

        finally:
            chem_scheduler.release(task_id)


# 全局单例
postprocess_manager = PostprocessManager()
