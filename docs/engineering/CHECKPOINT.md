# 工程阶段检查点（CHECKPOINT）

> 最新阶段：**Gaussian MCP V5.2 — 运行时一致性、授权对抗加固与真实计算预验收**  
> 所在分支：`feature/mcp-server`（基于 V5.1 提交 `52cda40b97788ae42d9b7a3520787e3d1bb439f8` 增量推进）

---

## 1. V5.2 完成清单

1. **Windows 后端运行时重建与协议一致性（Task 1）**：
   - 修正 [build_backend.ps1](file:///E:/YDW/ChemDatas/gaussian-dsh-plugin/scripts/build_backend.ps1)（默认 `Python312`、`Remove-Item dist\gaussian-backend` 保留 `dist\agensi\*.zip`）与 [deploy_runtime.ps1](file:///E:/YDW/ChemDatas/gaussian-dsh-plugin/scripts/deploy_runtime.ps1)。
   - 在 [entrypoint.py](file:///E:/YDW/ChemDatas/gaussian-dsh-plugin/backend/entrypoint.py) 新增 `--mock-worker` 分发，并在 [job_manager.py](file:///E:/YDW/ChemDatas/gaussian-dsh-plugin/backend/job_manager.py) 与 [process_utils.py](file:///E:/YDW/ChemDatas/gaussian-dsh-plugin/backend/process_utils.py) 显式添加 `stdin=subprocess.DEVNULL, close_fds=True`，定位并根除 stdio MCP 父进程下的 Windows 子进程句柄挂起缺陷。
   - 在 [execution_policy.py](file:///E:/YDW/ChemDatas/gaussian-dsh-plugin/backend/execution_policy.py) 与 [app.py](file:///E:/YDW/ChemDatas/gaussian-dsh-plugin/backend/app.py) 打通 `POST /v1/jobs` 与 MCP 完全一致的三层执行授权门控及一次性回执消费机制。
2. **编译后双客户端跨进程实测（Task 2）**：
   - 新增 [test_v52_compiled_cross_process.py](file:///E:/YDW/ChemDatas/gaussian-dsh-plugin/tests/test_v52_compiled_cross_process.py)（`5/5 OK`），使用真实编译产物 `runtimes/win32-x64/gaussian-backend/gaussian-backend.exe` 与独立 `mcp_server.py` stdio 客户端联合实测共享租约、并发提交、优雅停机、取消竞争与 `DATA_DIR` 隔离效应。
3. **7 向量授权对抗加固验证（Task 3）**：
   - 新增 [test_v52_auth_adversarial.py](file:///E:/YDW/ChemDatas/gaussian-dsh-plugin/tests/test_v52_auth_adversarial.py)（`7/7 OK`），覆盖密钥与回执路径渗漏、12 工具面审计、Admin 审批接口越权、`GAUSSIAN_ALLOW_REAL_EXECUTION` 与 HMAC 伪造、令牌/回执重放、审批后参数与资源升级篡改、跨作业劫持及非法 `job_id` 探测。
4. **跨机器默认值、包名 `MAX_PATH` 审计与 Agensi 资产检查（Task 4）**：
   - [config.py](file:///E:/YDW/ChemDatas/gaussian-dsh-plugin/backend/config.py) 新增 `_default_work_dir()` 回退至 `<data_dir>/gjf`；[index.js](file:///E:/YDW/ChemDatas/gaussian-dsh-plugin/src/index.js) 泛化 `GAUSSIAN_GUIDANCE`；[README.md](file:///E:/YDW/ChemDatas/gaussian-dsh-plugin/README.md) 明确 `@gd/gp` 与 `@yangdw2024/gp` 在 Windows `MAX_PATH = 260` 下的长度差异（`253` vs `269` 字符）。
   - 验证 `@gd/gp@0.2.0` (`npm pack --dry-run`: `2244` 文件，`76,686,018` B) 与两份 `dist/agensi/*.zip` 完好且无隐私路径泄漏。
5. **H2 `HF/STO-3G` Dry-Run 预验收档案（Task 5）**：
   - 产出 [h2_sp_preaccept.gjf](file:///E:/YDW/ChemDatas/gaussian-dsh-plugin/docs/_verify/v5_2_audit/h2_sp_preaccept.gjf)、[h2_preflight_dossier.json](file:///E:/YDW/ChemDatas/gaussian-dsh-plugin/docs/_verify/v5_2_audit/h2_preflight_dossier.json) 与 [H2_REAL_PREACCEPTANCE.md](file:///E:/YDW/ChemDatas/gaussian-dsh-plugin/docs/engineering/H2_REAL_PREACCEPTANCE.md)，严格保持 `real_g16_launched=false`。

---

## 2. 边界与下一步（V5.3 待批准事项）

- **全量回归状态**：`79/79` Python 自动化单测、`6/6` 离线冒烟、`19/19` DSH 契约校验、`2150` 运行时文件 SHA-256 核验与隔离 `gaussian-backend.exe` 冒烟全部通过。
- **尚未开放操作**：真实 `g16.exe` 运行、`git push`、`npm publish` 与 Agensi 在线上架，均需由用户明确下达 V5.3 执行指令后再行开启。
