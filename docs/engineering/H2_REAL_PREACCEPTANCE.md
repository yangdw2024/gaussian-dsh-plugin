# H2 真实 Gaussian 预验收与 V5.3 最小试运行档案（V5.2 仅 Dry-Run）

> **状态声明（V5.2）**：本档案仅完成只读环境盘点、输入生成、SHA-256 固化、Dry-Run 预检及参考基准对齐验证。  
> **严格约束**：`GAUSSIAN_ALLOW_REAL_EXECUTION=false`，**V5.2 阶段未启动真实 `g16.exe` 或 `formchk.exe` 计算进程**（`real_g16_launched = false`）。真实运行需等待项目负责人明确签发 V5.3 授权后执行。

---

## 1. 本地 Gaussian 可执行文件静态核查（只读）

来源档案：[h2_preflight_dossier.json](file:///E:/YDW/ChemDatas/gaussian-dsh-plugin/docs/_verify/v5_2_audit/h2_preflight_dossier.json)

| 组件 | 路径 | 存在状态 | 文件大小 | 本次是否启动 |
| :--- | :--- | :--- | :--- | :--- |
| Gaussian 主程序 | `D:\G16W\g16.exe` | `exists = true` | `803,328` bytes | `launched = false` |
| 格式化检查点工具 | `D:\G16W\formchk.exe` | `exists = true` | `23,430,144` bytes | `false` |

---

## 2. 最小预验收输入规格（H2 `HF/STO-3G` 单点能）

输入文件：[h2_sp_preaccept.gjf](file:///E:/YDW/ChemDatas/gaussian-dsh-plugin/docs/_verify/v5_2_audit/h2_sp_preaccept.gjf)

```gjf
%mem=2GB
%nprocshared=2
%nosave
%chk=h2_sp_preaccept.chk
# HF/STO-3G

H2 HF/STO-3G single-point V5.2 pre-acceptance (dry-run only)

0 1
 H       0.00000000     0.00000000     0.00000000
 H       0.00000000     0.00000000     0.74000000
```

| 核查项 | V5.2 实测记录值 |
| :--- | :--- |
| 文件大小 | `249` bytes |
| 原子数量 / 体系 | `2` atoms（H2，键长 `r = 0.74` Å，电荷 `0`，自旋多重度 `1`） |
| 理论方法与基组 | `HF/STO-3G` 单点能（SP） |
| 资源配额 | `%mem=2GB`，`%nprocshared=2` |
| 内容 SHA-256 | `a72a3e86196bf70c7608fd344dd102260f60d56ea69f764d8679d31712a58e46` |

---

## 3. V5.2 Dry-Run 预检与三层授权拦截基线

1. **Dry-Run 预检结果**：
   - 执行模式：`dry_run = true`
   - 宿主许可开关：`GAUSSIAN_ALLOW_REAL_EXECUTION = false`
   - 预检编号：`preflight_id = "e1b3276b7e364f2e"`
   - 预检是否授予人类批准：`grants_human_approval = false`（仅颁发 `integrity_token` 与 `preflight_id`，不颁发 `human_approval_token`）。
2. **三层授权门控确认**：
   - 第 1 层（文件完整性）：校对 `.gjf` SHA-256、任务名、`%mem`、`%nprocshared` 与路线卡匹配。
   - 第 2 层（宿主执行许可）：强制校验环境变量 `GAUSSIAN_ALLOW_REAL_EXECUTION=true`。
   - 第 3 层（单次任务人工授权）：强制要求带外工具（CLI/Loopback Admin API）签发的一次性 `human_approval_token` 与宿主侧签名回执（`approvals/grants/<preflight_id>.json`），并在真实拉起前消费销毁。
   - 详见 [execution_policy.py](file:///E:/YDW/ChemDatas/gaussian-dsh-plugin/backend/execution_policy.py) 与 [approve_gaussian_job.py](file:///E:/YDW/ChemDatas/gaussian-dsh-plugin/scripts/approve_gaussian_job.py)。

---

## 4. 科研参考基准对齐（来自测试夹具只读解析）

参考日志：[h2_sp_reference.log](file:///E:/YDW/ChemDatas/gaussian-dsh-plugin/tests/fixtures/h2_sp_reference.log)

| 物理量 | 参考解析值 | V5.3 真实试运行验收判据 |
| :--- | :--- | :--- |
| SCF 总能量（`HF/STO-3G`） | `-1.1175058821` Hartree | `|E_real - (-1.1175058821)| < 1e-4` Hartree |
| 正常终止状态 | `normal_termination = true` | 必须包含 `Normal termination of Gaussian` |
| HOMO / LUMO 轨道能量 | `-0.5779` / `0.6697` Hartree | 与参考轨道对称性及数值吻合 |
| 电偶极矩 | `0.0` Debye | 对称双原子分子零偶极矩 |
| 检查点产物 | `.chk` -> `formchk.exe` -> `.fchk` | `.log`、`.chk` 与可选 `.fchk` 均落盘至受控 `WORK_DIR` |

---

## 5. V5.3 最小真实计算批准与执行规程（待授权后实施）

1. **开启宿主执行开关（独立受控进程环境变量）**：
   - 设置 `GAUSSIAN_ALLOW_REAL_EXECUTION=true`，并设定独立的受控 `GAUSSIAN_WORK_DIR`（避免污染其他科研目录）。
2. **Agent / 操作者执行预检与核对 SHA-256**：
   - 使用 `run_gaussian_calculation(..., dry_run=True)` 获取最新 `preflight_id`、`integrity_token` 与实时计算的文件 SHA-256。
3. **带外人工签发一次性授权令牌**：
   - 在 AI 不可通过 MCP 调用的独立终端由操作者人工运行：
     ```powershell
     python scripts/approve_gaussian_job.py docs/_verify/v5_2_audit/h2_sp_preaccept.gjf `
       --preflight-id <preflight_id> `
       --approve-by <operator_id> `
       --expected-sha256 a72a3e86196bf70c7608fd344dd102260f60d56ea69f764d8679d31712a58e46
     ```
   - 核对 CLI 打印的路线行 `# HF/STO-3G`、电荷/多重度 `0 1`、原子数 `2`、`%mem`、`%nprocshared`，输入 `y` 确认（默认 `TTL = 600s`），获取一次性 `human_approval_token` 并生成宿主侧回执。
4. **提交真实作业并回收审计证据**：
   - 带齐 `integrity_token` 与 `human_approval_token` 提交真实作业（`dry_run=False`, `mock_mode=False`）；
   - 验证回执文件在执行前即被消费删除（防重放），并通过 `parse_gaussian_output` 核对真实输出日志非模拟标记、正常终止及能量误差 `< 1e-4` Hartree；
   - 测试收尾后立即将 `GAUSSIAN_ALLOW_REAL_EXECUTION` 恢复为 `false`。
