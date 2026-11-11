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
| `T4-01` | Phase 4 | 全读并审计 `execution_policy.py`、`job_manager.py`、`resource_scheduler.py`、`process_utils.py` | `TODO` | 逐条验证 21 项安全与稳定性清单 |
| `T4-02` | Phase 4 | 修复发现的安全隐患并补充攻击面回归测试 | `TODO` | 输出 `SECURITY_AUDIT.md` |
| `T5-01` | Phase 5 | 隔离环境下验证 DSH 工具契约与 Codex CLI (`CODEX_HOME`) 调用 | `TODO` | 零污染正式配置 |
| `T5-02` | Phase 5 | 生成 Claude Code / Cursor 标准化配置模板，标记未装客户端为 `NOT_RUN` | `TODO` | 输出 `COMPATIBILITY_MATRIX.md` |
| `T6-01` | Phase 6 | 根治 Windows `MAX_PATH=260` 与 `@yangdw2024/gp` 包路径问题 | `TODO` | `LongPathsEnabled=0` 下完整验证 |
| `T6-02` | Phase 6 | 升级至 `0.3.0`，重构 Vite/esbuild 与 PyInstaller 运行时并做隔离安装验真 | `TODO` | 检查最长路径 `< 260` 与可执行启动 |
| `T7-01` | Phase 7 | 升级优化 Agensi Skills (`SKILL.md` + 参考 + 模板 + 零秘密/绝对路径) | `TODO` | 构建至 `dist/agensi/` |
| `T7-02` | Phase 7 | 验证独立降级运行规范并撰写 Agensi 上架/定价方案草案 | `TODO` | `GATE-RELEASE-PUB` 前就绪 |
| `T8-01` | Phase 8 | 完善双语文档、Issue 模板、安全政策与 GitHub CI/CD 工作流 | `TODO` | 不触发远端强制推送 |
| `T9-11` | Phase 9–11 | 组装 `dist/release-candidate/`、执行全量回归扫描并生成 `FINAL_REPORT.md` | `TODO` | 本地提交 `feature/mcp-server` 并标记 `READY_FOR_APPROVAL` |
