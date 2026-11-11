# Gaussian Test Fixtures Provenance & Verification Matrix

本文档记录 `tests/` 与测试样本的数据来源、理论级别、核验边界以及已知可移植性限制，严格区分**真实硬件计算日志**、**第三方基准**、**合成解析回归样例**与**受控进程仿真输出**。

---

## 一、样本数据来源分类标准

1. **[CLASS A - REAL HARDWARE] 真实 Gaussian 硬件计算日志**：由商业版 Gaussian 16 (`g16.exe`) 在本地工作站真实执行生成的输出日志，包含真实机器环境头、CPU/Walltime 与完整 SCF/几何优化轨迹。
2. **[CLASS B - THIRD-PARTY BENCHMARK] 第三方算法与文献基准**：基于 RDKit (`ETKDGv3 + MMFF94s`) 的确定性三维构象化学规则校验，以及标准 DFT/HF 数量级能标对照。
3. **[CLASS C - SYNTHETIC PARSER FIXTURE] 合成解析回归样例**：为精确覆盖边界条件（単点能、实频/热力学、单虚频 TS、SCF 失败、日志截断）而在仓库 `tests/fixtures/` 目录下固定保留的结构化 `.log` 文本样例（**非真实 Gaussian 运行产物**）。
4. **[CLASS C-SIM - CONTROLLED SIMULATION] 受控进程仿真产物**：由 `backend/mock_worker.py` 在 `mock_mode=True` 下生成的模拟日志与输出字典，带显式仿真标识，其合成数值严格隔离至 `simulated_energy`，不得当作真实量子化学计算结果。

---

## 二、样本清单与真实来源核对

### 1. `tests/fixtures/h2_sp_reference.log`（CLASS C — 合成解析回归样例）
- **文件属性**：人工构造的 Gaussian 16 Rev A.03 格式固定回归测试样例（`PID=1234`, `10-Nov-2026`），用于检验单点能、轨道能级与偶极矩解析器，**非真实硬件计算输出**。
- **分子体系与方法**：$H_2$ ($r_{\text{H-H}} = 0.7414\text{ \AA}$)，`HF/STO-3G sp` (`%mem=12GB`, `%nprocshared=8`)
- **文件中的精确固定值**：
  - `Charge = 0`, `Multiplicity = 1`
  - `SCF Done: E(RHF) = -1.11750588210 A.U.`
  - `Alpha occ. eigenvalues`: `-0.57790` (HOMO)
  - `Alpha virt. eigenvalues`: `0.66970` (LUMO, Gap = `1.24760`)
  - `Dipole moment Tot`: `0.0000 Debye`
  - 终止行：`Normal termination of Gaussian 16`

### 2. `tests/fixtures/h2o_freq_reference.log`（CLASS C — 合成解析回归样例）
- **文件属性**：人工构造的振动频率与热力学解析回归测试样例（`PID=1235`, `10-Nov-2026`），**非真实硬件计算输出**。
- **分子体系与方法**：$H_2O$，`B3LYP/6-31G(d) freq`
- **文件中的精确固定值**：
  - 简正振动频率 (3 个实频)：`1648.5020`, `3825.1200`, `3935.4500 cm^-1`（0 个虚频）
  - `Zero-point correction = 0.021540 Hartree`
  - `Thermal correction to Energy = 0.024376 Hartree`
  - `Thermal correction to Enthalpy = 0.025320 Hartree`
  - `Thermal correction to Gibbs Free Energy = 0.003920 Hartree`
  - `SCF Done: E(RB3LYP) = -76.4089528701 A.U.`
  - `Dipole moment Tot = 1.8540 Debye`
  - 终止行：`Normal termination of Gaussian 16`

### 3. `tests/fixtures/ts_imag_reference.log`（CLASS C — 合成解析回归样例）
- **文件属性**：人工构造的一阶鞍点（单虚频）解析回归测试样例（`PID=1236`, `10-Nov-2026`），**非真实硬件计算输出**。
- **分子体系与方法**：双分子过渡态构型样例，`B3LYP/6-31G(d) opt=(ts,calcfc,noeigentest) freq`
- **文件中的精确固定值**：
  - 振动频率：`Frequencies -- -485.3200  1250.4500  1890.1200 cm^-1`
  - 解析器校验：正确将 `-485.3200` 归入 `imaginary_frequencies`，并在 `warnings` 给出过渡态提示。

### 4. `tests/fixtures/scf_failed_reference.log`（CLASS C — 合成解析回归样例）
- **文件属性**：人工构造的 SCF 发散非正常终止回归样例（`PID=1237`），**非真实硬件计算输出**。
- **文件中的精确固定行**：
  - `Convergence failure -- run terminated.`
  - `Error termination via Lnk1e in C:\G16W\l502.exe`
  - 解析器校验：`normal_termination = False`，识别为 SCF 收敛失败。

### 5. `c1ccccc1_opt_B3LYP_631Gdp_67f4b8f183fa.log`（CLASS A — 本地真实 G16 计算日志）
- **分类属性**：CLASS A（真实商业版 `Gaussian 16: ES64W-G16RevA.03` 执行产物，运行日期 `24-Oct-2026`, `PID=8728`, 总计 1071 行）。
- **体系与关键物理量**：苯 ($C_6H_6$)，`B3LYP/6-31G(d,p)` 优化，`HF = -232.2582019 Hartree`，`Dipole = 0.0000 Debye`，四项几何优化收敛判据全部达成。
- **可移植性与隐私说明**：该日志存于本机科研工作目录 (`GAUSSIAN_WORK_DIR`) 中，内含本机工作站主机名与用户运行头信息，**未纳入 Git 仓库分发**。在外部 CI 或未配备该工作目录日志的环境中，`tests/test_scientific_correctness.py` 会跳过真实日志比对段，仅执行仓库内置基准测试。

### 6. `test_benzene_smiles_and_real_g16_benchmark` RDKit 部分（CLASS B — 确定性化学基准）
- **分类属性**：CLASS B（RDKit ETKDGv3 + MMFF94s 算法输出）。
- **核验项**：从 SMILES `c1ccccc1` 生成 12 个显式氢全原子三维坐标、碳六元环共面性与键长合理性。

### 7. `backend/mock_worker.py` 生成数据（CLASS C-SIM — 受控进程仿真）
- **分类属性**：CLASS C-SIM（受控测试仿真）。
- **显式仿真标记与能量隔离 (V5.1 加固)**：
  - Mock `.log` 文件固定包含 `[MOCK_GAUSSIAN_SIMULATION]`、`MOCK_WORKER_SIMULATION`、`[SIMULATED]`、`[MOCK_SIMULATED_ENERGY]`（失败模式含 `[MOCK_SIMULATED_FAILURE]` 与 `mock_l502.exe`）。
  - 所有 MCP/后端输出（`parse_gaussian_output`、`submit_gaussian_calculation`、`get_gaussian_job_status`、`list_gaussian_jobs`）检测到仿真标记时，强制设置 `is_simulated=True`、`real_gaussian_result=False`、`energy_source="mock_simulation_placeholder"`，并将合成数值隔离到 `simulated_energy` 字段，同时将 `final_energy` / `last_energy` 置为 `None`，从数据结构上杜绝仿真数值被误报为真实 Gaussian 计算结果。
