"""Artifact 垃圾回收（M6 加固）。

只清理 data_dir（~/.gaussian-dsh）下的派生产物，按 mtime TTL：
- cube（.cube/.cub）：7 天（体积大、可由 fchk 重新生成）
- 图片（.png/.jpg/.jpeg/.svg）：30 天
- 日志（.log/.txt/.out）：30 天

白名单【永不自动删除】：
- .chk（checkpoint，重算昂贵，可能被后处理引用）
- .fchk/.fch（formchk 产物，后处理输入）
- .gjf（用户输入）
- .json（任务状态记录）

注意：不扫描、不删除 work_dir（用户工作目录 E:\\...\\Gjf）里的文件，
避免误删用户自己保存的输入与结果。
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Dict, List

from .config import settings

# 扩展名 → TTL 天数
_TTL_BY_EXT = {
    ".cube": settings.cube_ttl_days,
    ".cub": settings.cube_ttl_days,
    ".png": settings.image_ttl_days,
    ".jpg": settings.image_ttl_days,
    ".jpeg": settings.image_ttl_days,
    ".svg": settings.image_ttl_days,
    ".log": settings.log_ttl_days,
    ".txt": settings.log_ttl_days,
    ".out": settings.log_ttl_days,
}

# 白名单：无论多旧都不删
_PROTECTED_EXT = {".chk", ".fchk", ".fch", ".gjf", ".json", ".yaml", ".yml"}

# 扫描的子目录（相对 data_dir）
_SCAN_SUBDIRS = ["jobs", "postprocess", "logs"]


def _iter_candidate_files(data_dir: Path) -> List[Path]:
    files: List[Path] = []
    for sub in _SCAN_SUBDIRS:
        root = data_dir / sub
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if p.is_file():
                files.append(p)
    return files


def sweep(dry_run: bool = False) -> Dict:
    """执行一次 GC。

    Args:
        dry_run: True 只统计不删除。

    Returns:
        {"deleted": n, "freed_bytes": int, "kept_protected": n, "scanned": n, "actions": [...]}
    """
    now = time.time()
    deleted = 0
    freed = 0
    kept_protected = 0
    actions: List[Dict] = []

    for p in _iter_candidate_files(settings.data_dir):
        ext = p.suffix.lower()
        if ext in _PROTECTED_EXT:
            kept_protected += 1
            continue
        ttl_days = _TTL_BY_EXT.get(ext)
        if ttl_days is None:
            # 不在回收清单内的类型（如未知扩展），保留不动
            kept_protected += 1
            continue
        age_s = now - p.stat().st_mtime
        if age_s > ttl_days * 86400:
            size = p.stat().st_size
            if not dry_run:
                try:
                    p.unlink()
                except OSError as exc:
                    actions.append({"path": str(p), "error": str(exc)})
                    continue
            deleted += 1
            freed += size
            actions.append({
                "path": str(p),
                "age_days": round(age_s / 86400, 1),
                "size_bytes": size,
                "would_delete": dry_run,
            })

    return {
        "scanned": len(_iter_candidate_files(settings.data_dir)),
        "deleted": deleted,
        "freed_bytes": freed,
        "kept_protected": kept_protected,
        "dry_run": dry_run,
        "actions": actions,
    }
