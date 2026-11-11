# 检查点状态 (CHECKPOINT)

- **当前总任务**: Gaussian MCP Master Engineering Mission V1.0
- **最新阶段**: `Phase 4` 已完成并通过 (`106/106` 单测退出码 0)，进入 `Phase 5`（跨 Agent 兼容性验证）
- **分支与提交**: `feature/mcp-server`（Phase 2-3 检查点 `62b33a5`，当前含 Phase 4 安全加固改动）
- **最近完整检查**: `py312 -m unittest discover -s tests -v` -> **106/106 OK (34.167s, `EXIT=0`)**；已完成 `SECURITY_AUDIT.md`

## 环境事实快照 (Phase 0 实测)

- Python 3.12 工具链: `C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe` (`Python 3.12.10`)
- PATH 默认 python: `D:\YDW\Trae_Gromacs\miniconda3\python.exe`（工程构建与测试显式锁定 Python 3.12）
- Node / npm: `v24.19.0` / `11.17.0`
- 客户端可用性:
  - `codex`: `codex-cli 0.148.0`（存在 `~/.codex/config.toml`）
  - `claude`: `NOT_FOUND`
  - `cursor`: `NOT_FOUND`
  - `gh`: `NOT_FOUND`
  - DSH Desktop profile 路径: `%APPDATA%\dsh-desktop\harness\profiles\web`（存在 `node_modules\@gd\gp`）
- 外部化学软件（路径存在性已验证，真实 Gaussian 未触发运行）:
  - `D:\G16W\g16.exe`
  - `D:\G16W\formchk.exe`
  - `D:\Multiwfn\Multiwfn_3.8_bin_Win64\Multiwfn.exe`
  - `D:\VMD\vmd.exe`
  - `E:\YDW\Trae_Sob\Sobko_MCP_project-main` (`sobko_mode = "bm25_only"`)
- Windows `LongPathsEnabled`: `0`
- npm 包版本: `@yangdw2024/gp` 线上最新 `0.2.0`（历史版本 `0.0.0-stage`, `0.2.0`）

## 待突破人工门禁 (Always Preserved)

1. 真实 `g16.exe` 运行 (`GATE-G16-REAL`) — 需用户带签名参数/审批令牌手动放行。
2. `git merge` / `git push` 到 `main` (`GATE-GIT-MAIN`)。
3. 正式公开发布 npm / GitHub Release / Agensi 付费上架 (`GATE-RELEASE-PUB`)。
