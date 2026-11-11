# Gaussian MCP V5.1 工程任务检查点 (Task Checkpoint)

> 当前分支：`feature/mcp-server`
> 基线提交：`06e1f8f2ecc6084d14240d6604cd62f259e15d32`（V5.1 提交见本地 Git log）
> 验证解释器：系统标准用户级 Python 3.12 (`<PYTHON312_EXE>`)
> MCP 工具数：12 / 12 全部实现、协议就绪并完成 Codex CLI 受控实机全覆盖

---

## 1. V5.1 核心验收任务进度追踪表

| 任务域 | 任务名称 | 状态 | 交付文件 / 依据 | 关键实现与验收结果 |
|---|---|---|---|---|
| **任务一** | 跨进程调度核验与统一锁 | **PASS** | `backend/resource_scheduler.py`<br>`backend/job_manager.py`<br>`tests/test_cross_process_scheduling.py` | 确认 DSH Backend 与 MCP Server 为独立 OS 进程；以内核文件锁 (`compute_lease.lock`) + 原子状态 (`compute_lease.json`) + `has_running()` 二次核查 + 磁盘终态优先解决双客户端 TOCTOU 与状态覆盖；4 项跨进程并发/取消/崩溃回收测试全通 |
| **任务二** | 执行授权三层隔离加固 | **PASS** | `backend/execution_policy.py`<br>`backend/mcp_server.py`<br>`backend/app.py`<br>`backend/security.py`<br>`scripts/approve_gaussian_job.py`<br>`tests/test_execution_authorization.py` | 严格分离 Layer 1 文件完整性 (`integrity_token`)、Layer 2 宿主门禁 (`GAUSSIAN_ALLOW_REAL_EXECUTION`)、Layer 3 带外人工单次授权 (`human_approval_token` + 密钥置于 `approvals/.human_signing_key` 受沙箱禁止访问)；明确拒绝 Agent `confirmed=True` 或冒用 `integrity_token`；8 项对抗与授权测试全通 |
| **任务三** | 科研正确性、Mock 隔离与全工具验收 | **PASS** | `backend/mock_worker.py`<br>`backend/gaussian_output.py`<br>`tests/test_job_lifecycle.py`<br>`tests/test_scientific_workflow.py`<br>`tests/fixtures/PROVENANCE.md`<br>`docs/_verify/v5_1_audit/codex_remaining_tools_audit.json` | 所有 Mock 输出与 API 强制标注 `is_simulated=True` / `real_gaussian_result=False` 并将合成值隔离至 `simulated_energy` (`final_energy=None`, `last_energy=None`)；补充 PID 存活清理、重复停止及 OS PID 复用保护测试；更正 `PROVENANCE.md` 样本分类；Codex CLI 补齐剩余 4 工具 + 授权阻断实测 (5/5 PASS) |
| **任务四** | 仓库整理、发布演练与本地提交 | **PASS** | `.gitignore`<br>`requirements-mcp.txt`<br>`docs/engineering/*.md`<br>`dist/agensi/*.zip` | 更新 `.gitignore` 收录 `!tests/fixtures/*.log` 并排除备份/超大日志；完成密钥与隐私扫描；验证 `dist/agensi/*.zip` 与 `npm pack --dry-run`；全量 67 项单元测试 + 烟雾 + DSH 契约校验全部通过后执行本地 Git 提交（不推远程、不发包、不跑真实 g16） |

---

## 2. 自动化测试套件统计 (全量 67 项全部通过)

- `tests/test_security.py`: 10 / 10 PASS
- `tests/test_mcp_batch1.py`: 12 / 12 PASS
- `tests/test_mcp_batch2.py`: 12 / 12 PASS
- `tests/test_mcp_protocol_stdio.py`: 1 / 1 PASS（覆盖全量 12 个 MCP 工具发现与调用）
- `tests/test_dsh_shared_regression.py`: 3 / 3 PASS
- `tests/test_scientific_correctness.py`: 6 / 6 PASS
- `tests/test_job_lifecycle.py`: 9 / 9 PASS（含新增 `stop_gaussian_calculation` 进程清理、重复停止与 PID 复用保护测试）
- `tests/test_scientific_workflow.py`: 2 / 2 PASS（含 `final_energy=None` / `simulated_energy` 隔离断言）
- `tests/test_cross_process_scheduling.py`: 4 / 4 PASS（双独立 OS 子进程并发互斥、爆破提交、跨进程取消与孤儿/崩溃回收）
- `tests/test_execution_authorization.py`: 8 / 8 PASS（含防篡改、防提权、防冒充、防重放、管理接口与审批 CLI）
- **总计**：**67 / 67 项** Python 测试全部 PASS（0 失败，0 错误）。
