# 科学正确性验证报告 (SCIENTIFIC_VALIDATION)

> **当前状态**：`PASS`（Phase 3 完成全部 10 项计算化学科学边界核验、Bug 修复及自动化回归测试）  
> **验收基线**：`C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe -m unittest discover -s tests -v` -> **99/99 测试全部通过 (`EXIT=0`, 24.597s)**（其中 `tests/test_scientific_phase3.py` 10 项、`tests/test_scientific_correctness.py` 与 `tests/test_scientific_workflow.py` 协同覆盖）。

---

## 一、10 项计算化学关键边界逐项验证结论

| 编号 | 科学边界核查项 | 实现位置 | 验证机制与实测依据 | 状态 |
| :---: | :--- | :--- | :--- | :---: |
| `1` | 单点能 (`sp`) vs 几何优化 (`opt`) 最后一步取值语义 | `backend/gaussian_output.py` (`parse_gaussian_log`, `calculation_type`) | `test_01_single_point_vs_opt_last_step_semantics`：2 步 Opt 日志正确提取终态 Cycle 2 能量 `-76.422500123` Hartree 与 `opt_steps=2`，不取未松弛 Step 1 | `PASS` |
| `2` | HOMO-LUMO 轨道能隙 vs TD-DFT 垂直激发态区分 | `backend/gaussian_output.py`, `backend/gaussian_input.py` | 修复 `Alpha occ./virt.` `\s+` 跨行误匹配 `Excited` 导致 `ValueError` 的真实缺陷；同时返回基态 KS 能隙 `homo_lumo_gap_ev`、`excited_states` 与区分提示 `scientific_caveats`；`generate_gjf(job_type="td")` 显式发出 TD-DFT 提示 (`test_02`) | `PASS` |
| `3` | Hartree / eV / kcal/mol / kJ/mol 单位精确标注与转换常数 | `backend/gaussian_output.py`, `backend/fchk_reader.py` | 锁定 `HARTREE_TO_EV = 27.211386245988`、`HARTREE_TO_KCAL_MOL = 627.5094740631`、`HARTREE_TO_KJ_MOL = 2625.4996394799` 并输出 `energy_units_detail`；验证 `CH3Cl.fchk` MO SVG 明确区分 Hartree 与 eV (`test_03`) | `PASS` |
| `4` | DFT/SCF 能量 vs Post-HF (`CCSD(T)` / `CCSD` / `MP4` / `MP2`) 优先级 | `backend/gaussian_output.py` | `CCSD(T)` (`-76.35123456789`) 优先于 `EUMP2` 与 HF `scf_energy` (`-76.05`)；`MP2` 优先取 `EUMP2`；若 Post-HF 相关能缺失回退 `SCF` 时主动生成 `warnings` 告警 (`test_04`) | `PASS` |
| `5` | 频率分析虚频判别 (`0` / `1` / `>=2`) 与热化学总能量 | `backend/gaussian_output.py` | 精确输出 `stationary_point_character`（`local_minimum` / `first_order_saddle_point_or_ts` / `higher_order_saddle_point`）、过渡态/高阶鞍点告警、`total_zpe_energy` / `total_enthalpy` / `total_free_energy` 及 RRHO 298.15 K 声明 (`test_05`) | `PASS` |
| `6` | RDKit 力场 3D 初始构象 vs 量子化学 DFT 平衡几何限制声明 | `backend/mcp_server.py`, `backend/smiles/rdkit_builder.py` | `generate_gaussian_input_from_smiles` 在 `smiles_info` 返回 `geometry_disclaimer` 与 `mmff_energy_unit` (`kcal/mol`)；若用于 `job_type="sp"` 主动附加警告 (`test_06`) | `PASS` |
| `7` | Mock 模拟结果 (`is_simulated=True`) 零混淆隔离 | `backend/gaussian_output.py`, `backend/mock_worker.py` | 对 `run_mock()` 输出日志解析时强制 `is_simulated=True`、`real_gaussian_result=False`、`energy_source="mock_simulation_placeholder"`、`final_energy=None`、`scf_energy=None`、`total_*=None`，仅在 `simulated_energy` 保留占位符 (`test_07`) | `PASS` |
| `8` | `Normal termination` 与优化收敛 (`Optimization completed`) 分离 | `backend/gaussian_output.py` | 兼容标准 4 列 (`Item Value Threshold Converged?`) 与 3 列收敛表；检测到 `NO` 且已 `Normal termination` 时置 `opt_converged=False`、`stationary_point=False` 并发出未收敛告警 (`test_08`) | `PASS` |
| `9` | BSE 基组索引元数据 vs Gaussian `Gen` / `GenECP` 完整基组差异 | `backend/basis_set.py`, `backend/gaussian_input.py` | `list_basis_sets()` 条目统一附加 `metadata_only: True` 提示需调用 `get_basis_set` 获取完整 Gaussian94 段；`Gen`/`GenECP` 缺少 `append_text` 时主动告警 (`test_09`) | `PASS` |
| `10` | 多步 `Link1` 部分完成 / 截断与残缺日志稳健处理 | `backend/gaussian_output.py` | 统计 `Entering Link 1` / `--Link1--` / 多 `#` Route 卡片得到 `route_steps`；Step 1 `Normal termination` 后出现 `Error termination` 或后续步截断时，置 `normal_termination=False` 与 `incomplete_multistep=True` (`test_10`) | `PASS` |

---

## 二、Phase 3 实测发现并当场修复的源码缺陷

1. **轨道本征值正跨行匹配崩溃 (`backend/gaussian_output.py`)**：原有 `Alpha occ./virt. eigenvalues --((?:\s+-?[\d.Ee+]+)+)` 因 `\s+` 匹配换行符且 `[\d.Ee+]+` 可匹配单个字符 `'E'`，在 TD-DFT 日志 `Alpha virt. eigenvalues` 紧接 `Excited State 1:` 时触发 `ValueError: could not convert string to float: 'E'`。已收敛为单行水平空白 `[ \t]+` 与严格浮点正则 `-?\d+(?:\.\d+)?(?:[Ee][+-]?\d+)?`（含频率行同步收敛）。
2. **多步 `Link1` 后续步失败/截断识别遗漏 (`backend/gaussian_output.py`)**：当 Step 1 打印 `Normal termination` 后经 `--Link1--` 进入 Step 2 并以 `Error termination` 终止（且片段未重复打印 `Entering Link 1` 字样）时，原实现未统计多 `#` route 且未置 `incomplete_multistep=True`。现已联合统计 `--Link1--` 与 `#` route，精准标记 `route_steps=2`、`incomplete_multistep=True` 与 `normal_termination=False`。

---

## 三、科研数据来源分类声明

- **真实 Gaussian 16 基准日志 (`REAL G16 LOG`)**：宿主机苯优化真实输出 `E:\YDW\ChemDatas\Gjf\c1ccccc1_opt_B3LYP_631Gdp_67f4b8f183fa.log`（仅在磁盘存在时由 `tests/test_scientific_correctness.py` 自动核验 `-232.258201851` Hartree、HOMO `-0.24688`、LUMO `0.00260`、偶极矩 `0.0000` Debye）。
- **受控离线物理基准样例 (`tests/fixtures/*.log`)**：`h2_sp_reference.log`（HF/STO-3G）、`h2o_freq_reference.log`、`ts_imag_reference.log`、`scf_failed_reference.log`，用于离线可复现解析精度校准。
- **人工构造边界样例 (`tests/test_scientific_phase3.py`)**：4 列收敛失败表、多步 `Link1` 部分出错/截断、`CCSD(T)`/`MP2` 缺相关能回退、TD-DFT 激发态等边界用例，清晰标定于自动化测试脚本中，不与真实量化计算混同。
- **受控模拟样例 (`backend/mock_worker.py`)**：全部包含 `[MOCK_GAUSSIAN_SIMULATION]` 等 6 项强制横幅标记，解析层隔离 `final_energy=None`。
