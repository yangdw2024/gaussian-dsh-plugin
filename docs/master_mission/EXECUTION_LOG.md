# 工程执行日志 (EXECUTION_LOG)

| 时间 / 阶段 | 动作 | 结果 | 关键观测事实与产出 |
| :--- | :--- | :--- | :--- |
| `Phase 0` | 核验 Git 基线与远端状态 | `PASS` | `feature/mcp-server` 位于 `27ed1dc5c71c3809755d0e6077ec6d7a33e09485`，工作区干净；`origin/main = eba50e6...`, `v0.2.0 = 06e1f8f...` |
| `Phase 0` | 检查宿主软件、Agent 与注册表环境 | `PASS` | `py312` (`3.12.10`), Node `24.19.0`, `codex 0.148.0`; `claude/cursor/gh` 未安装；`LongPathsEnabled = 0`；`g16/formchk/Multiwfn/VMD` 均存在 |
| `Phase 0` | 基线单元测试预扫与全模块源码审计 | `PASS (需Phase 1复跑清日志)` | `py312` 跑出 `79 tests in 40.346s — OK`（外层命令行捕获曾返回退出码 1）；源码审计定位 6 类待修缺陷 |
| `Phase 1` | 复跑纯净基线单测 + V5.3 真实计算前置预检验 | `PASS` | `py312 -m unittest` **79/79 OK (`EXIT=0`)**；验证 `g16/formchk/Multiwfn/VMD` 存在；`h2_sp_preaccept.gjf` dry-run 通过（`preflight_id=043de4095b8b4869`）；未授权提交拦截于 `human_authorization` 层；真实 `g16.exe` 保持 `HUMAN_APPROVAL_REQUIRED` |
| `Phase 2` | 补齐 17 核心 MCP 工具 + Sobko 扩展，修复已审计缺陷并做安全后处理烟雾测试 | `PASS` | 修复 6 处后端/描述缺陷，新增 `mcp_sobko_ext.py` 与 `test_mcp_v53_complete.py`；全量单测 `89/89 OK (33.962s, EXIT=0)`；`CH3Cl.fchk` 实测 `Multiwfn 3.8 + VMD` 输出 `mo_levels.svg` (`2835` B)、`orb000013.cub`、`orbital_0.png` (`43599` B) |
| `Phase 3` | 完成 10 项计算化学科学正确性审计、Bug 修复与专项测试 | `PASS` | 修复 `Alpha occ./virt.` 跨行匹配 `Excited` 崩溃及多步 `Link1` 部分终止漏判；新增 `tests/test_scientific_phase3.py` (10 项)；`py312 -m unittest` **99/99 OK (24.597s, `EXIT=0`)**；本地检查点提交 `62b33a5`；输出 `SCIENTIFIC_VALIDATION.md` |
| `Phase 4` | 完成全链路安全与稳定性深度审计、6 项漏洞加固与对抗回归测试 | `PASS` | 审计覆盖全链 16 大安全维度；加固 `security.py`、`gaussian_input.py`、`process_utils.py`、`artifact_gc.py`、`app.py`、`rdkit_builder.py`；新增 `tests/test_security_phase4.py` (7 项，含真实 `mklink /J` NTFS Junction 测试)；`py312 -m unittest` **106/106 OK (34.167s, `EXIT=0`)**；输出 `SECURITY_AUDIT.md` |
| `Phase 5 (当前)` | 启动跨 Agent 兼容性测试（DSH 只读校验 + Codex CLI 隔离实机调用） | `IN_PROGRESS` | 严禁污染用户 `~/.codex/config.toml` 或 `%APPDATA%\dsh-desktop` |

## Phase 5 增量完成记录（2026-11-12）
- [x] **DSH 构建与宿主只读检查**：`node scripts/build.mjs` 重建 `lib/index.js`、`lib/client.js`，本地 Cordis 注册校验通过（`dsh_tool_count=19`, `prompts=1`, `all_have_schema_and_output=true`）；只读核查 `%APPDATA%\dsh-desktop` 仅发现 `.bak-gd-gp-20261024` 备份（`verify_*.mjs` 返回 `EXIT=1` 因未安装 `@gd/gp`）。
- [x] **MCP 跨目录直启修复 (`backend/mcp_server.py`)**：补充 `__package__ = "backend"` 与 `sys.path` 引导；从 `C:\Users\Administrator` 直启验证 `RC: 0`, `TOOL_COUNT: 19`。
- [x] **独立脱敏配置模板 (`examples/mcp_configs/`)**：新增 `claude_desktop_config.json`、`codex_config.toml`、`cursor_mcp.json`、`README.md`。
- [x] **OpenAI Codex CLI v0.148.0 隔离实机调用 (`task-2133`)**：使用临时 `CODEX_HOME`（不触碰 `~/.codex/config.toml`）通过 `gpt-5.6-sol`（`sandbox: read-only`, `--approve-for-me`）完成 4 项真实 MCP 调用（`gaussian_status`, `extract_structure_from_file`, `parse_gaussian_output`, `postprocess_capabilities`），`EXIT=0`。
- [x] **兼容性矩阵文档**：创建 `docs/master_mission/COMPATIBILITY_MATRIX.md`；`claude`/`cursor` 如实标注 `NOT_RUN`。
- [x] **全量 Python 回归**：修改 `backend/mcp_server.py` 后执行 `py312 -m unittest discover -s tests -v` -> `Ran 106 tests in 29.124s` (`OK`, `EXIT=0`)。

## Phase 6 完成记录（2026-11-12）
- [x] **统一版本升级 (`0.2.0 -> 0.3.0`)**：同步更新 `backend/config.py` (`SERVICE_VERSION = "0.3.0"`)、`src/index.js`、`package.json`、`scripts/deploy_runtime.ps1`、`tests/test_mcp_batch1.py`。
- [x] **包名正式回归 `@yangdw2024/gp` 并提供兼容打包器 (`scripts/build_npm_packages.mjs`)**：同步更新 `package.json`、`cordis.patch.yml`、`src/client.js`、`lib/client.js` 及 `verify_*.mjs`；新增 `scripts/build_npm_packages.mjs` 同时产出 `yangdw2024-gp-0.3.0.tgz`（主发布包）与 `gd-gp-0.3.0.tgz`（短命名兼容包）。
- [x] **Windows `MAX_PATH=260` 彻底根治**：
  - `packaging/gaussian-backend.spec`：在 `EXE(...)` 启用 `contents_directory="."` 消除 `_internal/` 层级（节省 10 字符），扩展 `excludes` 并通过 `_keep_runtime_data` 裁剪 `rdkit/Contrib/`、`.dist-info/licenses/`、`.dist-info/sboms/`、`jsonschema_specifications/`、`setuptools/`、`_tcl_data/`、`_tk_data/`。
  - `scripts/deploy_runtime.ps1`：将运行目录 `gaussian-backend` 缩短为 `b`（`runtimes/win32-x64/b/gaussian-backend.exe`，节省 15 字符），将文件总数由 `2150` 精简至 `1064`，包内最长相对路径由 `135` 字符降至 `96` 字符（`runtimes/win32-x64/b/rdkit.libs/RDKitEnumerateStereoisomers-*.dll`）。
  - 模拟超长 `153` 字符 DSH 安装前缀离线 `npm install` 解包实测：1158 文件全部落盘，最长绝对路径 **`249` 字符 (`< 260`)**（真实 `147` 字符 `@yangdw2024/gp` 仅 `243` 字符），且深度目录启动 EXE (`version=0.3.0`, `/v1/molecules/from-smiles` 苯 3D, `/v1/admin/shutdown`) 全绿。

## Phase 7 完成记录（2026-11-12）
- [x] **三大 Agensi Standalone Skills (`v0.3.0`) 完成**：
  - `skills/gaussian-job-setup/`（升级 `SKILL.md` + `templates/mcp-config.json` 指向 `<PATH_TO_REPO>/mcp_server.py` + 新增纯 stdlib CLI `scripts/gjf_helper.py`）
  - `skills/gaussian-output-analysis/`（升级 `SKILL.md` + `templates/mcp-config.json` + 新增纯 stdlib CLI `scripts/log_analyzer.py`）
  - `skills/gaussian-postprocessing/`（新增第 3 技能：Multiwfn 3.8 + VMD `formchk -> .cub -> .png` 工作流、`16,000,000` 格点上限守卫与 `scripts/multiwfn_recipe.py`）
- [x] **自动化打包与 ZIP 根结构/脱敏校验 (`scripts/package_agensi_skills.py`)**：生成 `dist/agensi/{gaussian-job-setup,gaussian-output-analysis,gaussian-postprocessing}-v0.3.0.zip`（同步复制至 `dist/release-candidate/agensi/`），校验 `SKILL.md` 位于 ZIP 根目录、frontmatter 字段完整、零硬编码密钥与私人主机路径。
- [x] **商业化上架策略文档**：创建 `docs/master_mission/AGENSI_LISTING_STRATEGY.md`（结合 `joeri@agensi.io` 邮件规范：非独占 IP、70/30 分成、独立无 MCP 运行 + 本地 MCP 引导架构）。
- [x] **自动化测试扩展 (`tests/test_agensi_skills_phase7.py`)**：4/4 测试全部通过（`0.242s`）。
