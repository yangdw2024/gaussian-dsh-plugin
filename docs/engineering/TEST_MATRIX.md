# Gaussian AI 综合测试矩阵与验证报告 (V5.1)

> 基线分支：`feature/mcp-server` ｜ 环境：Windows 10/11 (Python 3.12.10, OpenAI Codex CLI v0.148.0, Node.js)

## 1. 测试层级与状态矩阵

| 测试编号 | 测试层次 | 测试套件 / 脚本 | 测试内容与断言 | 退出码 | 结果 | 责任判定与说明 |
|---|---|---|---|---|---|---|
| **T01** | L1 单元测试 | `tests/test_security.py` | 只读/只写边界隔离、目录逃逸拦截、相对路径解析、绝对路径越界拒绝、源码目录写保护、用户目录写入拒绝、100MB 大文件限制、Null Byte 攻击防御 | 0 | **PASS** | 10 / 10 通过 |
| **T02** | L1 单元测试 | `tests/test_mcp_batch1.py` | 首批 4 个 MCP 工具 (`gaussian_status`, `generate_gaussian_input`, `parse_gaussian_output`, `diagnose_gaussian_error`)、300 原子上限与快速错误诊断 | 0 | **PASS** | 12 / 12 通过 |
| **T03** | L1 单元测试 | `tests/test_mcp_batch2.py` | 第二批 4 个 MCP 工具 (`search_gaussian_keywords`, `search_basis_sets`, `get_basis_set`, `generate_gaussian_input_from_smiles`)、RDKit 构象与专用 Cache Roots 检查 | 0 | **PASS** | 12 / 12 通过 |
| **T04** | L1 行为回归 | `tests/test_dsh_shared_regression.py` | DSH 共享模块行为回归：`opt+freq` 映射、BSE 损坏缓存容灾、无网离线回退 | 0 | **PASS** | 3 / 3 通过 |
| **T05** | L1 科研解析与基准 | `tests/test_scientific_correctness.py` | H2/H2O/TS/SCF 合成解析样例数值提取、RDKit 苯构象及本地外部 G16 日志比对 | 0 | **PASS** | 6 / 6 通过（外部 CLASS A 日志存在可移植性边界） |
| **T06** | L2 协议集成 | `tests/test_mcp_protocol_stdio.py` | 标准 stdio 管道 JSON-RPC 2.0 握手、`tools/list` 全量 12 工具发现、`tools/call` 交互与 stdout 零污染 | 0 | **PASS** | 1 / 1 通过 |
| **T07** | L2 任务生命周期与终止防护 | `tests/test_job_lifecycle.py` | Dry-run 预检、三层授权门禁拦截、Mock 运行与 `is_simulated` 标记、并发互斥、SCF 失败模拟、`stop_gaussian_calculation` 杀进程 / 重复终止拦截 / OS PID 复用保护 | 0 | **PASS** | 9 / 9 通过 |
| **T08** | L3 科研闭环与能量隔离 | `tests/test_scientific_workflow.py` | SMILES (`CCO`, `c1ccccc1`) -> 3D -> GJF -> Mock 计算 -> 轮询 -> 解析与诊断，验证 `final_energy=None` / `last_energy=None` 与 `simulated_energy` 隔离 | 0 | **PASS** | 2 / 2 通过 |
| **T09** | L2 跨进程资源调度 | `tests/test_cross_process_scheduling.py` | `dsh_backend` 与 `mcp_server` 双独立 OS 进程实测：跨进程租赁互斥、同步爆破提交仅 1 成功、跨进程取消终态一致性、崩溃租约回收与存活 `g16` 子进程保护 | 0 | **PASS** | 4 / 4 通过 |
| **T10** | L1/L2 执行授权对抗 | `tests/test_execution_authorization.py` | 预检不含人工授权、`confirmed=True` 绕过拦截、`integrity_token` 冒用拦截、GJF/资源篡改拦截、`approvals/` 沙箱禁止访问、单次 nonce 防重放、`/v1/admin/jobs/approve` 与 `scripts/approve_gaussian_job.py` | 0 | **PASS** | 8 / 8 通过 |
| **T11** | L3 Codex CLI 全工具实测 | `docs/_verify/v5_audit/` + `docs/_verify/v5_1_audit/` | 受控 `--approve-for-me` 沙箱下覆盖 V5.0 (8 项) + V5.1 剩余 4 工具与授权门禁 (5 项) | 0 | **PASS** | 8/8 (V5.0) + 5/5 (V5.1) 通过，全量 12 工具 100% 实机覆盖 |
| **T12** | L1 后端离线烟雾 | `docs/_verify/backend_offline_smoke.py` | FastAPI 后端 `/health`、`/v1/status`、`/v1/postprocess/capabilities`、匿名 `/v1/admin/shutdown` 403、非法 GJF 拒绝、`/v1/jobs` | 0 | **PASS** | 6 / 6 通过 |
| **T13** | L1 DSH 输出契约校验 | `docs/_verify/output_contract_check.mjs` | 校验 DSH 插件全量 19 个工具 `schema`/`render` 输出契约定义 | 0 | **PASS** | 19 / 19 通过 |
| **T14** | L5 发布演练 (非发布) | `npm pack --dry-run` + `dist/agensi/*.zip` | 检查 npm tarball 清单与 Agensi Skills ZIP 内部结构 (`SKILL.md`, `references/`, `templates/mcp-config.json`) | 0 | **PASS (演练)** | `gd-gp-0.2.0.tgz` (2153 files, 72.2MB)；仅演练未发布 |
| **T15** | L1 二进制产物测试 | `scripts/smoke_test_backend.ps1` | 验证预构建 `runtimes/` 下 `gaussian-backend.exe` | — | **STALE / NOT RE-RUN IN V5.1** | `runtimes/` 仍为旧阶段构建产物，V5.1 未重编二进制，发布新二进制前需重编并重测 |
| **T16** | L4 外部 DSH 宿主探针 | `scripts/verify_installed_runtime.mjs` / `verify_plugin_shape.mjs` | 探测 DSH Desktop 宿主 live profile 安装挂载与包结构 | — | **BLOCKED (External Host)** | 本环境未运行于已安装插件的 DSH 宿主 profile 下，受外部宿主条件限制 |
| **T17** | L3 真实 Gaussian 执行 | 真实 `g16.exe` 计算 | 在开启 `GAUSSIAN_ALLOW_REAL_EXECUTION=true` 下调用物理 `g16.exe` 完成真实作业 | — | **NOT RUN (Policy Locked)** | 遵守阶段约束，保持真实物理计算门禁关闭 |
| **T18** | L5 对外发布动作 | `git push` / `npm publish` / Agensi 上传 | 推送至 GitHub、发布 npm 或上传 Agensi 市场 | — | **NOT RUN (Forbidden)** | 严格遵守授权边界，仅做本地提交与发布前演练 |

---

## 2. Python 自动化测试统计总表 (最终回滚复核后执行结果)

| 测试套件 | 测试文件 | 测试用例数 | 结果 |
|---|---|---|---|
| 安全边界测试 | `tests/test_security.py` | 10 | **PASS (10/10)** |
| MCP 工具批次 1 | `tests/test_mcp_batch1.py` | 12 | **PASS (12/12)** |
| MCP 工具批次 2 | `tests/test_mcp_batch2.py` | 12 | **PASS (12/12)** |
| 协议层 stdio 测试 | `tests/test_mcp_protocol_stdio.py` | 1 | **PASS (1/1)** |
| 共享模块行为回归 | `tests/test_dsh_shared_regression.py` | 3 | **PASS (3/3)** |
| 量子化学科研解析 | `tests/test_scientific_correctness.py` | 6 | **PASS (6/6)** |
| 任务生命周期与终止防护 | `tests/test_job_lifecycle.py` | 9 | **PASS (9/9)** |
| 端到端科研闭环与隔离 | `tests/test_scientific_workflow.py` | 2 | **PASS (2/2)** |
| 跨进程并发调度与恢复 | `tests/test_cross_process_scheduling.py` | 4 | **PASS (4/4)** |
| 执行授权三层隔离对抗 | `tests/test_execution_authorization.py` | 8 | **PASS (8/8)** |
| **全量自动化测试总计** | **10 个测试文件** | **67** | **PASS (67/67, 100%)** |
