# Gaussian MCP Server 开发与集成指南

## 1. 架构与运行方式

Gaussian MCP Server 基于官方 Python MCP SDK（`mcp>=1.0.0`）开发，通过标准 **stdio** 方式与 AI Agent 客户端交互：

- **程序入口**：`mcp_server.py` 或 `python -m backend.mcp_server`
- **运行命令**：
  ```bash
  <PYTHON312_EXE> mcp_server.py
  ```
- **stdio 协议保证**：所有诊断和服务器运行日志输出至 `sys.stderr`，`sys.stdout` 仅流动标准的 JSON-RPC 2.0 帧，无任何日志污染。

---

## 2. 全量 12 个 MCP 工具定义

### 批次 1：基础核心工具 (阶段二)
1. `gaussian_status`：查询 Gaussian 16 主程序、formchk、受控工作目录、授权只读/只写根目录、内存与核数配额、以及跨进程计算调度租约状态。
2. `generate_gaussian_input`：依据分子三维坐标、方法、基组、电荷与多重度生成规范 `.gjf` 文件；受 `validate_safe_path(..., mode="write")` 与 `<= 300` 原子上限保护。
3. `parse_gaussian_output`：解析 `.log` / `.out` 计算结果（Normal/Error 终止、SCF/后-HF 能量、几何优化 4 项收敛、HOMO-LUMO、偶极矩、频率与虚频、ZPE/Enthalpy/Gibbs）。V5.1 强制检测仿真实标：若日志来自 `mock_worker`，`final_energy` 置为 `None`，合成能量隔离在 `simulated_energy`，并附带 `is_simulated=True` / `real_gaussian_result=False` 警告。
4. `diagnose_gaussian_error`：基于本地 `keywords.py` 快速规则匹配典型 Gaussian 报错（SCF 不收敛、内存不足、线性角、积分格点等）并给出修复参数建议。

### 批次 2：科学辅助与 3D 构象工具 (阶段三)
5. `search_gaussian_keywords`：纯内存检索 Gaussian 官方常见关键词与错误处理词条（支持分类过滤，上限 50）。
6. `search_basis_sets`：在 Basis Set Exchange (BSE) 基组库中检索基组，优先读取本地缓存并支持无网离线回退。
7. `get_basis_set`：获取指定元素与格式（默认 `gaussian94`）的基组定义，支持受 `Cache Roots` (`~/.gaussian-dsh/basis_cache/`) / `Write Roots` 沙箱约束的安全保存。
8. `generate_gaussian_input_from_smiles`：通过 RDKit ETKDGv3 多构象采样与 MMFF94s 优化从 2D SMILES 构建三维全氢结构 `.gjf`；受内存硬守卫与跨进程 `rdkit` 独占租约保护。

### 批次 3：受控任务调度与生命周期工具 (V5.0 / V5.1)
9. `submit_gaussian_calculation`：默认 `dry_run=True` 仅执行预检并返回 SHA-256 摘要与 `integrity_token`。
   - 支持 `mock_mode=True` 安全仿真闭环（带 `is_simulated=True`, `real_gaussian_result=False`）。
   - 真实物理执行 (`mock_mode=False`) 强制通过三层独立授权门禁：文件完整性 (`integrity_token`) + 人工带外单次授权 (`human_approval_token` / 宿主授权凭据) + 宿主环境变量 (`GAUSSIAN_ALLOW_REAL_EXECUTION=true`)。
10. `get_gaussian_job_status`：有界尾读（`<= 100` 行）查询任务实时状态、步数、进度与日志尾；对 Mock 任务隔离 `last_energy=None`、`simulated_energy`。
11. `list_gaussian_jobs`：分页列出任务队列及当前跨进程活动状态，排除恢复临时文件。
12. `stop_gaussian_calculation`：执行 OS 进程创建时间戳实例核对（防 PID 复用误杀）后拆除整棵子进程树，支持跨进程取消状态同步与重复停止拦截。

---

## 3. 带外人工授权工作流 (Out-of-Band Human Approval, V5.1)

真实硬件计算严禁仅凭 Agent 自签令牌或 `confirmed=True` 放行。人工算子须在 MCP 工具外部通过受信任接口授权精确任务：

- **方式 A（命令行交互/审计工具）**：
  ```powershell
  <PYTHON312_EXE> scripts/approve_gaussian_job.py "<GAUSSIAN_WORK_DIR>\job.gjf" `
    --preflight-id <PREFLIGHT_ID> --approve-by <OPERATOR_ID> --mem 4GB --nproc 4 --yes
  ```
- **方式 B（DSH 宿主管理 HTTP 接口）**：
  `POST /v1/admin/jobs/approve`（经 `_require_admin` Bearer Token / 本机回环校验保护）。

---

## 4. 客户端集成配置模板与受控调用实测

### 4.1 Codex CLI 集成与受控沙箱实测

注册命令（替换为本机 Python 3.12 与仓库路径）：
```bash
codex mcp add gaussian -- "<PYTHON312_EXE>" "<REPO_ROOT>/mcp_server.py"
```

V5.0 / V5.1 受控沙箱非交互实测（**禁止使用危险绕过参数**，统一使用 `--approve-for-me` + workspace-write 沙箱）：
```powershell
codex exec -m gpt-5.6-sol --ephemeral --approve-for-me "<prompt invoking gaussian MCP tools>"
```
所有实测日志均保存至 `docs/_verify/v5_audit/` 与 `docs/_verify/v5_1_audit/`。

### 4.2 Claude Code 配置 (`claude.json` / `settings.json`)

```json
{
  "mcpServers": {
    "gaussian-chemistry": {
      "command": "<PYTHON312_EXE>",
      "args": [
        "<REPO_ROOT>/mcp_server.py"
      ],
      "env": {
        "GAUSSIAN_DATA_DIR": "<GAUSSIAN_DATA_DIR>",
        "GAUSSIAN_WORK_DIR": "<GAUSSIAN_WORK_DIR>",
        "GAUSSIAN_ALLOWED_READ_ROOTS": "<GAUSSIAN_WORK_DIR>",
        "GAUSSIAN_ALLOWED_WRITE_ROOTS": "<GAUSSIAN_WORK_DIR>",
        "GAUSSIAN_DEFAULT_MEM": "12GB",
        "GAUSSIAN_DEFAULT_NPROC": "8",
        "GAUSSIAN_ALLOW_REAL_EXECUTION": "false"
      }
    }
  }
}
```

### 4.3 Cursor / Generic MCP 配置 (`.cursor/mcp.json`)

```json
{
  "mcpServers": {
    "gaussian": {
      "command": "<PYTHON312_EXE>",
      "args": [
        "-m",
        "backend.mcp_server"
      ],
      "cwd": "<REPO_ROOT>",
      "env": {
        "GAUSSIAN_WORK_DIR": "<GAUSSIAN_WORK_DIR>",
        "GAUSSIAN_ALLOW_REAL_EXECUTION": "false"
      }
    }
  }
}
```
