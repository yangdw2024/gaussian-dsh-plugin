# 工程测试与验收矩阵（V5.2）

> 本矩阵所有状态均来自 V5.2 最终代码与编译产物修改后的真实命令实测输出，无推定或跳过放行项。

---

## 1. 全链路验收矩阵

| 编号 | 测试层次 | 测试对象 / 脚本 | V5.2 实测结果 | 关键实测依据 |
| :--- | :--- | :--- | :--- | :--- |
| T01 | 安全隔离 | `tests/test_security.py` | **PASS (10/10)** | 路径逃逸、读写目录隔离、Windows Junction/Symlink 与大文件限制全部通过 |
| T02 | MCP Tool | `tests/test_mcp_batch1.py` | **PASS (12/12)** | 状态查询、`generate_gaussian_input`、`parse_gaussian_output`、`diagnose_gaussian_error` |
| T03 | MCP Tool | `tests/test_mcp_batch2.py` | **PASS (12/12)** | `smiles_to_gjf`、BSE 检索/离线回退、基组缓存、关键字检索 |
| T04 | MCP 协议 | `tests/test_mcp_protocol_stdio.py` | **PASS (1/1)** | 真实 `mcp_server.py` stdio 握手、`list_tools` 与工具调用闭环 |
| T05 | 回归基准 | `tests/test_dsh_shared_regression.py` | **PASS (3/3)** | BSE 离线容错、损坏缓存恢复与 DSH `job_type` 路线映射 |
| T06 | 科研正确性 | `tests/test_scientific_correctness.py` | **PASS (6/6)** | `H2` / `H2O` / `TS` 虚频 / SCF 失败识别；含依赖本机参考日志的 `test_benzene_smiles_and_real_g16_benchmark` |
| T07 | 作业生命周期 | `tests/test_job_lifecycle.py` | **PASS (9/9)** | Dry-Run / Mock 提交、模拟标识校验、停止/重复停止、PID 复用防护 |
| T08 | 科研闭环 | `tests/test_scientific_workflow.py` | **PASS (2/2)** | 乙醇与苯分子端到端“SMILES -> 输入 -> Mock 计算/失败诊断 -> 解析”闭环 |
| T09 | 跨进程调度 | `tests/test_cross_process_scheduling.py` | **PASS (4/4)** | 源码级 DSH 与 MCP 双客户端并发抢占（严格仅 1 个生效）、跨进程取消与租约回收 |
| T10 | 执行授权 | `tests/test_execution_authorization.py` | **PASS (8/8)** | Dry-Run 禁颁人类令牌、三层独立拦截、资源篡改拒绝与单次消费防重放 |
| T11 | 对抗安全 | `tests/test_v52_auth_adversarial.py` | **PASS (7/7)** | 新增 V5.2：7 类对抗向量（密钥渗漏、12 工具清单审计、Admin API 越权、HMAC 伪造、重放、审批后篡改、跨作业劫持） |
| T12 | 编译端双端互操作 | `tests/test_v52_compiled_cross_process.py` | **PASS (5/5)** | 新增 V5.2：真实 `gaussian-backend.exe` + `mcp_server.py` 跨进程租约可见、并发竞争、`/shutdown` 保留运行子进程、并发取消与 `DATA_DIR` 分离对比 |
| T13 | 后端离线冒烟 | `docs/_verify/backend_offline_smoke.py` | **PASS (6/6)** | `/v1/health`、`/v1/status`、`/v1/postprocess/capabilities`、`/v1/admin/shutdown` 匿名 403、非法 GJF 拒绝、`/v1/jobs` |
| T14 | DSH 契约校验 | `docs/_verify/output_contract_check.mjs` | **PASS (19/19)** | `CONTRACT PASS`（注：因环境未安装 `@deepseek-ai/dsh-llm`，使用脚本内置内联子集校验器） |
| T15 | 编译运行时完整性 | `runtimes/win32-x64/runtime.json` + `check_long_paths.ps1` + `smoke_test_backend.ps1` | **PASS** | `2150` 个文件 SHA-256 校验 `BAD = 0`；最长相对路径 `172` 字符（`0 > 260`）；隔离环境变量冒烟退出码 `0` |
| T16 | 默认工作目录回退 | `_default_work_dir` Python 隔离验证 | **PASS** | 模拟遗留 `E:\YDW\ChemDatas\Gjf` 不存在时正确回退至 `<data_dir>\gjf` |
| T17 | 打包与 Skills 资产 | `npm pack --dry-run` + `dist/agensi/*.zip` + `fake @gd/gp` | **PASS** | `@gd/gp@0.2.0` (`2244` 文件，tarball `76,686,018` B / 展开 `172,725,790` B)；两份 Agensi ZIP 完整保留；隔离 `lib/index.js` 导出正常 |
| T18 | H2 真实预处理档案 | `H2_REAL_PREACCEPTANCE.md` + `h2_preflight_dossier.json` | **Dry-Run READY** | 完成输入 SHA-256 固化、Dry-Run 预检及参考能量对齐；**V5.2 严禁且未启动真实 `g16.exe`** |

---

## 2. Python 自动化测试统计总表

- 运行解释器：`Python 3.12.10`（`$env:LOCALAPPDATA\Programs\Python\Python312\python.exe`）
- 执行环境变量：`GAUSSIAN_ALLOW_REAL_EXECUTION=false`
- 执行命令：`python -m unittest discover -s tests -v`
- 汇总结果：**Ran 79 tests — OK（退出码 `0`，失败 `0`，错误 `0`，跳过 `0`）**

> 说明：[test_benzene_smiles_and_real_g16_benchmark](file:///E:/YDW/ChemDatas/gaussian-dsh-plugin/tests/test_scientific_correctness.py) 在当前开发工作站上通过，依赖于工作站本地已有历史参考日志文件；跨机器在未放置该日志的新主机运行该单测需注意此前置条件。
