# 复验提示词（第十轮，has_running 复用实例三态 + 全量回归）— 复制给评审 AI

> 用法：把「==== 复验任务开始 ====」以下整段复制给评审 AI，文件已打包在 `acceptance_bundle.zip`。
> 定位：第九轮"有条件交付"，串行安全（PID 三态）已闭环，唯一剩 has_running() 用裸 pid_alive() 短路、
> 没走实例三态，PID 复用时永久判 running、队列卡死且与 get_job 路径不一致。本包收口这一处。
> **只读、不改、不装软件、不要求评审机跑真实 Gaussian/RDKit/Multiwfn/VMD。**

==== 复验任务开始 ====

## 你是谁
你是资深静态评审工程师，精通 Python FastAPI（子进程、PID 复用、串行 lease、重启接管）与 DSH/Cordis
插件生命周期、Gaussian、JSON-RPC stdio。**只评审、只读；不要改文件、不要装依赖。**
不要采信任何 FIX_REPORT 的"已修复"声明——每条都自己打开 ZIP 内源码核实，给 `文件:行号` 证据。

## 背景
项目 `gaussian-dsh-plugin` 是 DSH 客户端里的 Gaussian 辅助插件，严格串行（同一时刻只跑一个 Gaussian）。
本轮只复核 has_running() 是否统一走了带 PID 实例三态的终态判断。

## 一、本轮重点复核（状态：闭环 / 部分 / 未闭环 + 文件:行号证据）

- **has_running() 不再用裸 pid_alive() 短路**：`backend/job_manager.py has_running()` 对持久化 running job，
  是否删除了 `if self._pid_alive(j.pid): return True` 的短路，改为统一调用 `self._finalize_if_dead(j)`：
  只有它返回 False（仍在运行/不可判定）才视为占用；明确 PID 复用（实例 False）或进程已退出时落终态、
  释放 lease、返回 False。确认 PID 复用时 has_running() 不再永久判 running，且与 get_job() 路径状态一致。

## 二、已闭环项回归确认（不得回退，逐条给结论）
- **PID 三态（R9a/R9b）**：`_adopt_or_finalize` 与 `_finalize_if_dead` 仍区分 True/False/None，
  None 保守视为运行；alive+None → adopt+acquire；alive+False → finalize 不 acquire；alive+True → adopt。
- **终态优先级**：reconcile 仍只让 recover 补 pending/running 缺 pid；completed/failed/stopped 永不被复活。
- **R5a-1/R5a-2**：stop 用内存 `_running_jobs`、成功后清内存/processes/recover；reap `trust_handle=True`。
- **R2**：最终 SCF 无 virt 时 LUMO/gap=None；正常多行 virt 取 `following[0]` 首根。
- **Sobko-init/R9/R1/R3/R4/R5b/R5c/R7/R8/R6主体/_waitReady**：均保持上轮实现。

## 三、回归检查（逐条给结论）
1. 改动文件有无未定义变量、import 缺失、语法；pydantic 仍用 model_dump。
2. has_running 三条路径：alive+None → True（保守占用）；alive+True → True；alive+False → False（落终态、释放 lease）。
3. Popen 句柄仍存活的内存兜底（`self._processes` 循环）未被破坏。
4. 正常存活（非复用）进程重启后仍被 adopt 并重新 acquire。
5. 前端 stdio=inherit、cwd 必填字符串、waitForExit===true 才认退出；外部 reuse 仍 owned=false。

## 四、有意保留、禁止误判为 blocker
- 后端 PyInstaller onedir exe 尚未重打（runtimes 旧版），属部署步骤。
- 真实 chk→formchk→Multiwfn→VMD 端到端、真实 DSH managed 联调未跑。
- one-file 未实现（开关拒绝），不判缺陷。
- Windows Job Object 无法静态证明 breakaway，"受控 shutdown 不杀树 + 诚实注释"视为合理缓解。

## 输出格式（严格遵守）
1. **总体结论**：可交付 / 有条件交付 / 需返工，一句话。
2. **逐条核对表**：本轮 1 项 + 第二部分回归项，每列 `状态 — 文件:行号 — 一句话说明`。
3. **新发现问题**：`[级别] 文件:行号 — 问题 — 影响 — 建议`；没有就写"未发现新问题"，不要凑数。
4. **回归项检查结果**（第三部分 1–5 逐条给结论）。
5. **优点**：3–5 点，必须有代码证据。
6. 禁止编造评审机无法验证的运行结果，禁止给无依据的化学结论。

==== 复验任务结束 ====

---

## 提交给复验 AI 的文件清单（已在 acceptance_bundle.zip 内，纯文本）

### 根目录配置/说明
- `README.md`、`package.json`、`cordis.patch.yml`、`start_backend.bat`

### 文档
- `docs/FIX_REPORT_20261020.md`、`docs/STATUS.md`、`docs/LESSONS_LEARNED.md`、本复验提示词

### 后端源码（重点）
- `backend/job_manager.py`（has_running/三态/终态优先级）、`backend/gaussian_output.py`（R2）
- `backend/sobko_client.py`、`backend/process_utils.py`、`backend/postprocess/manager.py`、
  `backend/gaussian_input.py` 及其余 app.py/config.py/entrypoint.py/resource_scheduler.py/
  memory_guard.py/artifact_gc.py/basis_set.py/keywords.py/fchk_reader.py/smiles/*/postprocess/*/
  profiles/*/templates/*

### 前端源码（给 src，不给压缩产物）
- `src/index.js`、`src/client.js`

### 打包/脚本
- `packaging/gaussian-backend.spec`、`scripts/build_backend.ps1`、`deploy_runtime.ps1`、
  `smoke_test_backend.ps1`、`build.mjs`

### 不要提交
- `runtimes/`、`lib/`、所有 `__pycache__/`、`.pyc`、`docs/backups_*`、`*.recover.json`、临时 staging
