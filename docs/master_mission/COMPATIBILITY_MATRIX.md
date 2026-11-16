# Gaussian MCP & DSH 多客户端兼容性矩阵（Phase 5）

本文档记录 Phase 5 阶段对 DSH 插件桌面端与多客户端 MCP 接入配置的真实核验结果。严格区分已实机验证项与未运行项（`NOT_RUN`）。

## 1. 客户端与宿主环境兼容性总览

| 客户端 / 宿主 | 接入方式 | 验证状态 | 工具数量 / 覆盖情况 | 隔离与环境影响 |
| :--- | :--- | :--- | :--- | :--- |
| **DSH Desktop Harness** (`@gd/gp` / `@yangdw2024/gp`) | Cordis 插件 (`lib/index.js` + FastAPI Runtime) | **BUILD + CONTRACT VERIFIED**；live profile 未安装（`EXIT=1` 符合预期） | `19` DSH tools，`1` prompt，`all_have_schema_and_output=true` | 只读检查 `%APPDATA%\dsh-desktop`（仅发现 `.bak-gd-gp-20261024` 备份）；未修改用户 profile |
| **OpenAI Codex CLI** (`v0.148.0`) | `stdio` (`python mcp_server.py`) | **PASS**（真实受控调用 `EXIT=0`） | MCP Core `17` + Sobko `2` = `19` 已注册；实机完成 `4` 工具调用 | 使用独立临时 `CODEX_HOME`、`codex_work`、`codex_data`；未修改 `~/.codex/config.toml` |
| **Python MCP Stdio Client** (Direct / Subprocess) | `stdio` (`backend/mcp_server.py` / `mcp_server.py`) | **PASS**（跨工作目录直启 `EXIT=0`） | Core `17` + Sobko `2` = `19` | 从仓库外目录 `C:\Users\Administrator` 直启成功 |
| **Claude Desktop / Claude Code** (`claude`) | `stdio` (`examples/mcp_configs/claude_desktop_config.json`) | **NOT_RUN** | 配置模板已提供，未在本机自动实机运行 | 未修改全局 Claude 配置 |
| **Cursor IDE** (`cursor`) | `stdio` (`examples/mcp_configs/cursor_mcp.json`) | **NOT_RUN** | 配置模板已提供，未在本机自动实机运行 | 未修改全局 Cursor 配置 |

## 2. Phase 5 关键发现与修复

### 2.1 `backend/mcp_server.py` 跨工作目录直启修复
- **问题定位**：若外部 MCP 客户端（或用户配置）直接运行 `python <repo>/backend/mcp_server.py` 且工作目录不在仓库根目录时，原文件顶层相对导入会触发 `ImportError: attempted relative import with no known parent package`。
- **修复措施**：在 `backend/mcp_server.py` 增加 `__package__ = "backend"` 与 `sys.path` 引导逻辑。
- **验证证据**：从仓库外目录 `C:\Users\Administrator` 直接通过 `Popen` 启动验证，`RC: 0`，`TOOL_COUNT: 19`。

### 2.2 独立客户端配置模板 (`examples/mcp_configs/`)
已提供脱敏配置模板（统一使用 `<PATH_TO_REPO>/mcp_server.py` 占位符，不含任何密钥或个人本机绝对路径）：
- `examples/mcp_configs/claude_desktop_config.json`
- `examples/mcp_configs/codex_config.toml`
- `examples/mcp_configs/cursor_mcp.json`
- `examples/mcp_configs/README.md`

## 3. Codex CLI 独立受控验证明细（`task-2133`）

- **Codex 版本与参数**：`OpenAI Codex v0.148.0`，model `gpt-5.6-sol`，`sandbox: read-only`，`approval: on-request`（`--ephemeral --approve-for-me --skip-git-repo-check`）
- **受控隔离目录**：`CODEX_HOME`、`GAUSSIAN_WORK_DIR`、`GAUSSIAN_DATA_DIR` 均指向临时 scratch 目录；只读白名单额外包含 `tests/fixtures`
- **实机调用结果**（`EXIT=0`，`tokens used: 19,552`）：
  1. `gaussian/gaussian_status` -> `status: "ok"`，`server_version: "0.2.0"`（Phase 6 前基线），`core_tools_count: 17`，`optional_extensions.sobko.tools: ["sobko_search", "sobko_fetch"]`，`running_job: false`
  2. `gaussian/extract_structure_from_file`（目标 `tests/fixtures/h2_sp_reference.log`）-> `ok: true`，`smiles: "[H][H]"`，`extractor: "openbabel"`，`natoms_guess: 2`
  3. `gaussian/parse_gaussian_output`（目标 `tests/fixtures/h2_sp_reference.log`）-> `normal_termination: true`，`method: "HF"`，`basis: "STO-3G"`，`scf_energy: -1.1175058821`，`is_simulated: false`，`real_gaussian_result: true`
  4. `gaussian/postprocess_capabilities` -> `ok: true`，`formchk.exists: true`，`multiwfn.version: "3.8"`，`vmd.exists: true`，`max_grid_points: 16000000`

## 4. DSH Desktop 检查明细

- Workspace 构建：`node scripts/build.mjs` 重建 `lib/index.js` 与 `lib/client.js`，本地 Cordis 注册核验通过（`dsh_tool_count= 19`, `prompts= 1`, `all_have_schema_and_output= true`）。
- 宿主 live profile 只读检查：`%APPDATA%\dsh-desktop` 仅存在 `.bak-gd-gp-20261024` 清理备份，未安装 `@gd/gp`；因此 `verify_plugin_shape.mjs`、`verify_profile_bundle.mjs`、`verify_installed_runtime.mjs` 均返回 `EXIT=1`（目标目录缺失），未触动宿主配置。Windows `MAX_PATH=260` 打包根目录超长根因将在 Phase 6 彻底修复并做隔离 `npm pack` + `npm install` 验证。
