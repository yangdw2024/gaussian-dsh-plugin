# 任务看板 (TASK_BOARD)

| Task ID | Phase | 任务描述 | 状态 | 备注/证据索引 |
| :--- | :--- | :--- | :--- | :--- |
| `T0-01` | Phase 0 | Git 基线、远端状态、工作区清洁度核验 | `PASS` | `feature/mcp-server @ 27ed1dc5c71c3809755d0e6077ec6d7a33e09485` |
| `T0-02` | Phase 0 | 工具链、外部软件、Agent 客户端及注册表盘点 | `PASS` | `py312`, Node `24.19.0`, `codex 0.148.0`; `claude`/`cursor`/`gh` 缺失 |
| `T0-03` | Phase 0 | 核心后端、前后端接口及打包脚本源码审计 | `PASS` | 发现 6 处具体代码/配置缺陷与路径风险 |
| `T0-04` | Phase 0 | 建立 `docs/master_mission/` 工程中枢文档体系 | `PASS` | 11 份控制中心文件已创建 |
| `T1-01` | Phase 1 | 使用 `py312 -NoProfile` 获取干净退出码 0 的基线单测日志 | `PASS` | `79/79 OK` (27.225s), `BASELINE_EXIT_CODE=0` |
| `T1-02` | Phase 1 | 核验 `D:\G16W\g16.exe`、`formchk.exe` 权限与隔离目录写入 | `PASS` | `g16.exe`/`formchk.exe`/`Multiwfn.exe`/`vmd.exe` 均存在且可执行 |
| `T1-03` | Phase 1 | 针对 `h2_sp_preaccept.gjf` 执行 SHA-256 绑定与 dry-run | `PASS (真实执行 HUMAN_APPROVAL_REQUIRED)` | `preflight_id=043de4095b8b4869`, 归一化 SHA `a72a3e86...`, 未启动 `g16.exe` |
| `T1-04` | Phase 1 | 验证未授权/不匹配审批令牌被拒绝执行 | `PASS` | 无人工令牌/替代 `integrity_token` 均在 `human_authorization` 层拦截 |
| `T2-01` | Phase 2 | 修复 `backend/config.py` 重复 `data_dir` 与版本常量梳理 | `PASS` | `SERVICE_VERSION = "0.2.0"` 收敛，消除 `data_dir` 重复覆盖 |
| `T2-02` | Phase 2 | 加固 `backend/structure_reader.py` 句柄/临时目录/Z=1..118 映射 | `PASS` | 修复 `_parse_orientation_block` 双横线状态机、Z=1..118、句柄及 `struct_*` 清理 |
| `T2-03` | Phase 2 | 加固 `backend/postprocess/` (`manager.py`, `multiwfn.py`, `vmd.py`) 与 `app.py` | `PASS` | `verify_cube_within_limit` 全覆盖、`_load(tid)` 修复、`.tga` 清理、`CH3Cl.fchk` 实测出图 |
| `T2-04` | Phase 2 | `backend/mcp_server.py` 补齐 5 个核心工具 (12 -> 17) | `PASS` | 17 核心工具全部对齐并经 `test_mcp_v53_complete.py` + stdio 验证 |
| `T2-05` | Phase 2 | 创建可选 Sobko 扩展模块 `backend/mcp_sobko_ext.py` | `PASS` | `GAUSSIAN_MCP_ENABLE_SOBKO` 控制加载，缺失时不崩溃 |
| `T2-06` | Phase 2 | 同步 `src/index.js` 工具描述与版本检查，新增 Phase 2 测试套件 | `PASS` | `Ran 89 tests in 33.962s — OK` (`EXIT=0`) |
| `T3-01` | Phase 3 | 审计并加固 10 项计算化学科学正确性边界 | `PASS` | 加固 `gaussian_output.py` / `gaussian_input.py` / `basis_set.py` / `mcp_server.py` 并修复两项实测缺陷 |
| `T3-02` | Phase 3 | 新增不完整日志、多步优化+频率、Post-HF 与单位歧义测试 | `PASS` | `tests/test_scientific_phase3.py` (10 项)，全量 `99/99 OK (24.597s, EXIT=0)` + `SCIENTIFIC_VALIDATION.md` |
| `T4-01` | Phase 4 | 全读并审计 `execution_policy.py`、`job_manager.py`、`resource_scheduler.py`、`process_utils.py` | `PASS` | 静态全局扫描零高危调用，审计 `app.py`、`security.py`、`vmd.py`、`templates/*.tcl`、`artifact_gc.py`、`gaussian_input.py` |
| `T4-02` | Phase 4 | 修复发现的安全隐患并补充攻击面回归测试 | `PASS` | 修复 ADS/UNC/DOS设备名、CRLF/chk注入、HTTP 403/413、GC symlink、SMILES 2000字符、PID<=0；`106/106 OK (34.167s, EXIT=0)` + `SECURITY_AUDIT.md` |
| `T5-01` | Phase 5 | 隔离环境下验证 DSH 工具契约与 Codex CLI (`CODEX_HOME`) 调用 | `TODO` | 零污染正式配置 |
| `T5-02` | Phase 5 | 生成 Claude Code / Cursor 标准化配置模板，标记未装客户端为 `NOT_RUN` | `TODO` | 输出 `COMPATIBILITY_MATRIX.md` |
| `T6-01` | Phase 6 | 根治 Windows `MAX_PATH=260` 与 `@yangdw2024/gp` 包路径问题 | `TODO` | `LongPathsEnabled=0` 下完整验证 |
| `T6-02` | Phase 6 | 升级至 `0.3.0`，重构 Vite/esbuild 与 PyInstaller 运行时并做隔离安装验真 | `TODO` | 检查最长路径 `< 260` 与可执行启动 |
| `T7-01` | Phase 7 | 升级优化 Agensi Skills (`SKILL.md` + 参考 + 模板 + 零秘密/绝对路径) | `TODO` | 构建至 `dist/agensi/` |
| `T7-02` | Phase 7 | 验证独立降级运行规范并撰写 Agensi 上架/定价方案草案 | `TODO` | `GATE-RELEASE-PUB` 前就绪 |
| `T8-01` | Phase 8 | 完善双语文档、Issue 模板、安全政策与 GitHub CI/CD 工作流 | `TODO` | 不触发远端强制推送 |
| `T9-11` | Phase 9–11 | 组装 `dist/release-candidate/`、执行全量回归扫描并生成 `FINAL_REPORT.md` | `TODO` | 本地提交 `feature/mcp-server` 并标记 `READY_FOR_APPROVAL` |

### Phase 5 更新状态（2026-11-12）
- Phase 5（DSH 验证与 Codex/MCP 跨客户端兼容）：**COMPLETED**
  - DSH 插件 构建+契约验证通过（`19` tools / `1` prompt）；live profile 未安装（只读核查，未修改 `%APPDATA%\dsh-desktop`）
  - Codex CLI `v0.148.0` 隔离 `CODEX_HOME` 实机 `4` 个 MCP 工具调用 `EXIT=0`
  - `backend/mcp_server.py` 跨工作目录直接启动修复并回归验证（`106/106` tests `OK`）
  - `examples/mcp_configs/*` 与 `docs/master_mission/COMPATIBILITY_MATRIX.md` 已就绪（`claude` / `cursor` 标为 `NOT_RUN`）
- 下一阶段：Phase 6（Windows `MAX_PATH=260` 彻底根治、版本升级至 `0.3.0`、后端与前端重新打包、隔离 `npm pack`/`install` 校验）

### Phase 6 更新状态（2026-11-12）
- Phase 6（Windows `MAX_PATH=260` 根治、版本升级至 `0.3.0`、前后端重建与隔离包安装实测）：**COMPLETED**
  - `pyinstaller` + `deploy_runtime.ps1` 重建 `runtimes/win32-x64/b/gaussian-backend.exe`（`0.3.0`，1064 运行时文件，包内最长相对路径 `96` 字符）
  - 离线包 `yangdw2024-gp-0.3.0.tgz` 与 `gd-gp-0.3.0.tgz` 已构建（`64.7 MB` / `153.0 MB` / `1158` files）
  - 模拟 153 字符深度 DSH 前缀 `npm install --offline` 最长路径 `249 < 260`，且 EXE 在该深度目录启动 + RDKit `c1ccccc1` 建模 + 优雅关闭全通
- 下一阶段：Phase 7（Agensi Agent Skills 升级、第 3 技能 `gaussian-postprocessing` 新增、内置独立无 MCP CLI 脚本与 `dist/agensi/*.zip` 构建校验）

### Phase 7 更新状态（2026-11-12）
- Phase 7（Agensi Agent Skills 产品化与独立 CLI 工具链）：**COMPLETED**
  - 新增/升级 3 项 Skill（`gaussian-job-setup`, `gaussian-output-analysis`, `gaussian-postprocessing`），无 MCP 亦可独立运行
  - 生成并校验 3 份 `dist/agensi/*-v0.3.0.zip`，新增 `tests/test_agensi_skills_phase7.py` (`4/4` PASS)
  - 编写 `docs/master_mission/AGENSI_LISTING_STRATEGY.md`
- 下一阶段：Phase 8（GitHub 开源治理、README 0.3.0 同步、`CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md`, `TROUBLESHOOTING.md`, `THIRD_PARTY_LICENSES.md`, `.github/` Templates & Workflows）

### Phase 8 更新状态（2026-11-12）
- Phase 8（GitHub 开源治理与 CI/CD 模板）：**COMPLETED**
  - 完成 `README.md`、`CHANGELOG.md`、`CONTRIBUTING.md`、`SECURITY.md`、`TROUBLESHOOTING.md`、`THIRD_PARTY_LICENSES.md`、`.github/`
  - 校验全部 `README.md` 站内链接与更新后 Agensi ZIP 重建均通过
- 下一阶段：Phases 9–11（组装完整 `dist/release-candidate/` 产物与 `SHA256SUMS`、全仓密钥/路径扫描、最终全量测试/打包/MAX_PATH 验收、`RELEASE_MANIFEST.md`、`RELEASE_CHECKLIST.md`、`FINAL_REPORT.md` 与最终本地提交）

### Phases 9–11 更新状态（2026-11-12）
- Phase 9（Release Candidate 组装、校验和、秘密扫描）：**COMPLETED**
- Phase 10（最终全量 110 项自动化测试与产物独立核验）：**COMPLETED**
- Phase 11（交付报告与 `READY_FOR_APPROVAL` 收尾提交）：**COMPLETED**
- 外部公开操作（`git push`, `merge main`, `npm publish`, GitHub Release, Agensi 上架, 真实 `g16.exe` 执行）：**HUMAN_APPROVAL_REQUIRED**
