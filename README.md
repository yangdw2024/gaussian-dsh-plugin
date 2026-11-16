[![Listed on dsh-plugin.org](https://dsh-plugin.org/badges/listed.svg)](https://dsh-plugin.org/plugins/yangdw2024/gaussian-dsh-plugin)
# Gaussian DSH Plugin & MCP Server (`@yangdw2024/gp` · v0.3.0)

AI 计算化学工程助手 —— 同时支持 **DeepSeek Harness (DSH) 原生插件**、**标准 `stdio` MCP Server** 与 **Agensi 独立 Agent Skills**。

> **开源许可声明**：本项目代码基于 [MIT License](./LICENSE) 开源；内置打包分发的 Open Babel (`3.2.1`) 遵循 `GPL-2.0-only` 协议，所调用的 Gaussian 16、Multiwfn 3.8 与 VMD 均为第三方专有/商业软件，需由用户在本地自行合法安装并配置路径（详情见 [THIRD_PARTY_LICENSES.md](./THIRD_PARTY_LICENSES.md)）。

---

## 核心特性 / Highlights (`v0.3.0`)

1. **DSH 原生桌面插件（`19` DSH Tools + `1` Prompt）**
   - 包名正式回归 `@yangdw2024/gp`（同步保留 `@gd/gp` 兼容构建脚本 `scripts/build_npm_packages.mjs`）。
   - **彻底修复 Windows `MAX_PATH=260` 限制**：通过 PyInstaller `contents_directory="."` 扁平布局与 `runtimes/win32-x64/b/gaussian-backend.exe` 短路径目录及冗余数据裁剪，使 147+ 字符的 DSH `.generations\live\...` 解压路径全长控制在 `< 250` 字符以内。
2. **标准 Python MCP Server（`17` Core Tools + 可选 `2` Sobko Tools）**
   - 入口文件：`mcp_server.py`（亦支持跨工作目录直接执行 `backend/mcp_server.py`）。
   - 支持 **OpenAI Codex CLI**、**Claude Desktop / Claude Code**、**Cursor IDE** 等标准 MCP `stdio` 客户端，内置脱敏配置模板 [`examples/mcp_configs/`](./examples/mcp_configs/README.md)。
3. **三层执行安全门禁与路径沙盒**
   - **Layer 1 文件完整性 (`file_integrity`)**：基于 SHA-256 绑定 `.gjf` 内容与 `mem`/`nproc`/`job_name` 资源签名。
   - **Layer 2 人工线下授权 (`human_authorization`)**：通过独立人工 CLI（`scripts/approve_gaussian_job.py`）签发一次性 HMAC-SHA256 授权令牌与回执；MCP 与 HTTP 管理员接口严格禁止 Agent 自行签发。
   - **Layer 3 宿主执行开关 (`host_execution_gate`)**：默认 `GAUSSIAN_ALLOW_REAL_EXECUTION=false`，未显式授权时绝不拉起真实 `g16.exe`。
   - **跨进程调度锁与路径隔离**：DSH PyInstaller 后端与独立 MCP Server 共享同一 OS 文件锁（`<data_dir>`）阻止并发抢占 GPU/CPU 配额；拦截 Windows NTFS ADS（`:`）、UNC SMB 路径（`\\\\`）、保留 DOS 设备名（`CON`/`NUL`/`COM1`...）、符号链接/Junction 与 Link0 CR/LF 注入。
4. **独立 Agent Skills（无需 MCP 亦可开箱运行）**
   - [`skills/gaussian-job-setup`](./skills/gaussian-job-setup/SKILL.md)：`.xyz -> .gjf` 生成、语法与电子自旋奇偶校验、路线关键词参考。
   - [`skills/gaussian-output-analysis`](./skills/gaussian-output-analysis/SKILL.md)：`.log/.out` 能量/能隙/热力学/虚频与 `--Link1--` 多步未完解析，及 Link 错误（`l9999`, `l502`, `l301`, `l103`, `l913`）诊断。
   - [`skills/gaussian-postprocessing`](./skills/gaussian-postprocessing/SKILL.md)：`formchk -> Multiwfn 3.8 -> .cub -> VMD Tachyon -> .png` 轨道 / ESP / RDG 脚本生成与 `16,000,000` 格点上限防护。

---

## 快速安装与使用 / Quick Start

### 1. 在 DSH Desktop 中安装
在 DSH 客户端 → 插件 → 添加插件，搜索并安装 npm 包：

```text
@yangdw2024/gp
```

> 本插件原生自带 `runtimes/win32-x64/` 编译后 Python 后端与嵌入式 Open Babel 3.2.1，在 Windows x64 下开箱即用。

### 2. 作为独立 MCP Server 接入 Codex CLI / Claude / Cursor
1. 安装 Python 3.12 依赖：
   ```bash
   pip install -r requirements.txt -r requirements-mcp.txt
   ```
   *(RDKit 若在特定平台无 PyPI wheel，推荐使用 `conda install -c conda-forge rdkit` 或官方 Python 3.12+ 发行版)*
2. 参考 [`examples/mcp_configs/`](./examples/mcp_configs/README.md) 中的 `codex_config.toml`、`claude_desktop_config.json` 或 `cursor_mcp.json` 将 `<PATH_TO_REPO>/mcp_server.py` 注册到客户端。

### 3. 本地开发、测试与构建

```bash
# 运行全部 Python 单元测试与科研/安全/跨进程回归套件
python -m unittest discover -s tests -v

# 重新构建 DSH JS 扩展与 UI
npm run build

# 打包 Agensi standalone skill ZIP（校验 SKILL.md 根目录结构与脱敏）
python scripts/package_agensi_skills.py
```

---

## 工具列表 / Tools Overview

| 类别 | MCP 核心工具 (`17` 个) |
| :--- | :--- |
| **环境与输入准备** | `gaussian_status`, `search_gaussian_keywords`, `generate_gaussian_input_from_smiles`, `extract_structure_from_file`, `generate_gaussian_input` |
| **基组查询** | `search_basis_sets`, `get_basis_set`（支持离线回退与 `~/.gaussian-dsh/basis_cache/` 专用缓存） |
| **计算调度与状态** | `submit_gaussian_calculation`, `get_gaussian_job_status`, `list_gaussian_jobs`, `stop_gaussian_calculation` |
| **结果与报错诊断** | `parse_gaussian_output`, `diagnose_gaussian_error` |
| **波函数与可视化后处理** | `postprocess_capabilities`, `create_postprocess_task`, `get_postprocess_task`, `list_postprocess_tasks` |
| **可选知识库扩展 (`2` 个)** | `sobko_search`, `sobko_fetch`（仅当检测到本地 Sobko 项目时自动注册；无知识库时优雅跳过） |

---

## 环境变量配置 / Configuration

| 环境变量 | 默认值 | 说明 |
| :--- | :--- | :--- |
| `GAUSSIAN_BACKEND_MODE` | `managed` | `managed`（插件托管后端进程）或 `external` |
| `GAUSSIAN_BACKEND_URL` | `http://127.0.0.1:8765` | `external` 模式下连接的后端地址 |
| `GAUSSIAN_ALLOW_REAL_EXECUTION` | `false` | **宿主真实计算总开关**；设为 `true` 后仍需人工签发单次 HMAC 令牌 |
| `GAUSSIAN_EXE` | `D:\G16W\g16.exe` | 用户本机 Gaussian 16 主程序路径 |
| `FORMCHK_EXE` | `D:\G16W\formchk.exe` | Gaussian `formchk` 路径 |
| `MULTIWFN_EXE` | `D:\Multiwfn\Multiwfn_3.8_bin_Win64\Multiwfn.exe` | Multiwfn 3.8 可选后处理路径 |
| `VMD_EXE` | `D:\VMD\vmd.exe` | VMD 可选渲染路径 |
| `GAUSSIAN_WORK_DIR` | `%USERPROFILE%\.gaussian-dsh\gjf` *(或配置覆盖)* | 科研输入 / 输出 / `.chk` 受控读写目录 |
| `GAUSSIAN_DATA_DIR` | `%USERPROFILE%\.gaussian-dsh` | 任务状态、跨进程锁、授权目录及后处理产物根目录 |
| `GAUSSIAN_DEFAULT_MEM` | `12GB` | 默认内存预算 |
| `GAUSSIAN_DEFAULT_NPROC` | `8` | 默认 CPU 核数 |
| `GAUSSIAN_MAX_LOG_SIZE_MB` | `100` | HTTP 解析最大 `.log` 文件体积限制（超限返回 `413`） |

---

## 更多文档 / Documentation

- [CHANGELOG.md](./CHANGELOG.md) — 版本变更记录
- [CONTRIBUTING.md](./CONTRIBUTING.md) — 开发环境搭建、构建、测试与 PR 规范
- [SECURITY.md](./SECURITY.md) — 安全架构、沙盒隔离与漏洞披露指南
- [TROUBLESHOOTING.md](./TROUBLESHOOTING.md) — 常见安装/运行问题排查手册
- [THIRD_PARTY_LICENSES.md](./THIRD_PARTY_LICENSES.md) — 第三方依赖与开源许可清单
