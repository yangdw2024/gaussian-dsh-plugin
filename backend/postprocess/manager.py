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

    # 三档网格点数保守上界（按 16Å 盒子、默认间距估的偏大值，用于提交前提前拒绝）。
    # 注意：这是提交前的粗估，不替代真实网格；执行器生成 cube 后必须再读 cube header
    # 的 nx*ny*nz 复核（M5），超额产物不得进入 VMD。
    _GRID_EST_POINTS = {
        "coarse": 262_000,
        "medium": 1_200_000,
        "fine": 4_100_000,
    }

    @staticmethod
    def _cube_header_point_count(cube_path: Path) -> int:
        """R3: 读标准 cube header 的 NX*NY*NZ，非法 header 直接 raise（fail-closed）。

        标准 cube 布局（0-based）：第 0-1 行注释；第 2 行=原子数+网格原点；
        第 3/4/5 行分别为 nx/ny/nz + 格矢量，网格点数取这三行的【首字段】。
        读不到或非正整数不返回 None 放行，而是报错拒绝该产物。
        """
        with open(cube_path, "r", encoding="utf-8", errors="ignore") as f:
            header = [f.readline() for _ in range(6)]
        if len(header) < 6:
            raise ValueError(f"cube header 不完整（少于6行）：{cube_path}")
        dims = []
        for line in header[3:6]:
            parts = line.split()
            if not parts:
                raise ValueError(f"cube 网格维度行缺失：{cube_path}")
            try:
                n = int(parts[0])
            except ValueError as e:
                raise ValueError(f"cube 网格维度非整数：{line!r}") from e
            if n <= 0:
                raise ValueError(f"cube 网格维度非正：{n}（{cube_path}）")
            dims.append(n)
        return dims[0] * dims[1] * dims[2]

    def _check_grid_points(self, req: PostprocessRequest) -> None:
        """M6c/M5: 提交前按档位保守上界预检，超过 postprocess_max_grid_points 直接拒绝。"""
        est = self._GRID_EST_POINTS.get(req.grid, self._GRID_EST_POINTS["medium"])
        cap = settings.postprocess_max_grid_points
        if est > cap:
            raise ValueError(
                f"网格档位 '{req.grid}' 保守估算约 {est:,} 点，超过上限 {cap:,} 点；"
                f"请改用更粗网格（coarse/medium）。"
            )

    def verify_cube_within_limit(self, cube_path: Path) -> int:
        """M5/R3: 执行器生成 cube 后、送入 VMD 前的复核钩子（执行器接入点）。

        读 cube header 的 nx*ny*nz：header 非法直接 raise（fail-closed，不放行）；
        超过 postprocess_max_grid_points 拒绝进入渲染。返回实际点数。
        """
        cap = settings.postprocess_max_grid_points
        points = self._cube_header_point_count(cube_path)
        if points > cap:
            raise ValueError(
                f"cube 网格 {points:,} 点超过上限 {cap:,}，拒绝进入 VMD 渲染；请使用更粗网格。"
            )
        return points

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

            # M6: 产物统一放到 data_dir/postprocess/<task_id>，使其纳入 GC 扫描范围；
            # 不再散落在用户 work_dir（那里 GC 不扫，MO SVG 等会永久残留）。
            work_dir = settings.data_dir / "postprocess" / task_id
            work_dir.mkdir(parents=True, exist_ok=True)

            artifacts: List[ArtifactInfo] = []
            final_status = "completed"

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

                # P2-1: 状态机 running_multiwfn → rendering_vmd → completed
                task.status = "running_multiwfn"
                task.logs = f"正在用 Multiwfn 生成轨道 cube（轨道 {orbitals}，grid={req.grid}）..."
                self._save(task)

                from .multiwfn import run_orbital_cube_batch
                cubes = run_orbital_cube_batch(
                    fchk_path=fchk_path,
                    orbitals=orbitals,
                    grid=req.grid,
                    work_dir=work_dir,
                )
                for c in cubes:
                    artifacts.append(ArtifactInfo(
                        name=c.name, path=str(c), kind="chemical/cube",
                        size_bytes=c.stat().st_size,
                    ))

                # VMD 渲染 PNG
                if req.render:
                    task.status = "rendering_vmd"
                    task.logs = f"Multiwfn 完成（{len(cubes)} cube），正在用 VMD 渲染等值面..."
                    self._save(task)
                    from .vmd import render_orbitals
                    pngs = render_orbitals(
                        cube_paths=cubes,
                        output_dir=work_dir,
                        isovalue=req.orbital_isovalue,
                        base_name="orbital",
                    )
                    for p in pngs:
                        artifacts.append(ArtifactInfo(
                            name=p.name, path=str(p), kind="image/png",
                            size_bytes=p.stat().st_size,
                        ))
                    task.logs = f"轨道分析完成：{len(cubes)} 个 cube + {len(pngs)} 张 PNG。"
                else:
                    task.logs = f"轨道 cube 已生成 {len(cubes)} 个（render=false，未渲染 PNG）"
                final_status = "completed"

            elif req.kind == "esp":
                task.status = "running_multiwfn"
                task.logs = f"正在用 Multiwfn 生成密度 + ESP 双 cube（grid={req.grid}）..."
                self._save(task)

                from .multiwfn import run_esp_cube_batch
                density_cube, esp_cube = run_esp_cube_batch(
                    fchk_path=fchk_path,
                    grid=req.grid,
                    work_dir=work_dir,
                )
                for c in (density_cube, esp_cube):
                    artifacts.append(ArtifactInfo(
                        name=c.name, path=str(c), kind="chemical/cube",
                        size_bytes=c.stat().st_size,
                    ))

                if req.render:
                    task.status = "rendering_vmd"
                    task.logs = "Multiwfn 完成，正在用 VMD 渲染 ESP 着色表面..."
                    self._save(task)
                    from .vmd import render_esp_surface
                    png = work_dir / "esp_surface.png"
                    out = render_esp_surface(
                        density_cube=density_cube,
                        esp_cube=esp_cube,
                        output_path=png,
                    )
                    artifacts.append(ArtifactInfo(
                        name=out.name, path=str(out), kind="image/png",
                        size_bytes=out.stat().st_size,
                    ))
                    task.logs = f"ESP 表面图完成：{density_cube.name} + {esp_cube.name} + {out.name}"
                else:
                    task.logs = f"ESP 双 cube 已生成（render=false，未渲染 PNG）"
                final_status = "completed"

            elif req.kind == "rdg":
                task.status = "running_multiwfn"
                task.logs = f"正在用 Multiwfn 做 NCI/RDG 分析（grid={req.grid}）..."
                self._save(task)

                from .multiwfn import run_rdg_cube_batch
                signrho_cube, rdg_cube = run_rdg_cube_batch(
                    fchk_path=fchk_path,
                    grid=req.grid,
                    work_dir=work_dir,
                )
                for c in (signrho_cube, rdg_cube):
                    artifacts.append(ArtifactInfo(
                        name=c.name, path=str(c), kind="chemical/cube",
                        size_bytes=c.stat().st_size,
                    ))

                if req.render:
                    task.status = "rendering_vmd"
                    task.logs = "Multiwfn 完成，正在用 VMD 渲染 RDG/NCI 等值面..."
                    self._save(task)
                    from .vmd import render_rdg
                    png = work_dir / "rdg_nci.png"
                    out = render_rdg(
                        signrho_cube=signrho_cube,
                        rdg_cube=rdg_cube,
                        output_path=png,
                    )
                    artifacts.append(ArtifactInfo(
                        name=out.name, path=str(out), kind="image/png",
                        size_bytes=out.stat().st_size,
                    ))
                    task.logs = f"RDG/NCI 图完成：{signrho_cube.name} + {rdg_cube.name} + {out.name}"
                else:
                    task.logs = f"RDG 双 cube 已生成（render=false，未渲染 PNG）"
                final_status = "completed"

            elif req.kind == "mo_levels":
                from ..fchk_reader import read_fchk_orbital_info, generate_mo_level_svg
                orb_info = read_fchk_orbital_info(fchk_path)
                svg = generate_mo_level_svg(orb_info)
                svg_path = work_dir / "mo_levels.svg"
                svg_path.write_text(svg, encoding="utf-8")
                # M2: 只有产物真实存在且非零才算 completed
                if not svg_path.exists() or svg_path.stat().st_size == 0:
                    raise RuntimeError("MO 能级图未成功写入")
                artifacts.append(ArtifactInfo(
                    name="mo_levels.svg",
                    path=str(svg_path),
                    kind="image/svg+xml",
                    size_bytes=svg_path.stat().st_size,
                ))
                task.logs = f"MO 能级图已生成：HOMO={orb_info.homo_energy:.4f}, LUMO={orb_info.lumo_energy:.4f}, gap={orb_info.gap:.4f} eV"

            task.status = final_status
            if final_status == "completed":
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
