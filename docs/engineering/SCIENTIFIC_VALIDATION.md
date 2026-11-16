# Gaussian AI 计算化学科研正确性验证报告 (V5.1)

## 1. 验证目标与质量准则

计算化学 MCP Server 必须具备严谨的物理量解析准确性与模拟结果防混淆机制：
- **严禁仿真能量混同真实计算**：`mock_mode=True` 产生的所有数值必须显式标记为仿真占位结果，绝不能填入 `final_energy` 或 `last_energy` 字段冒充真实量子化学结果。
- **区分 SCF 收敛与几何优化收敛**：SCF 单点迭代收敛不代表分子达到势能面驻点。
- **区分理论方法能量**：准确区分 HF/DFT 与 MP2/CCSD 后相关总能量。
- **单虚频过渡态识别**：精准将负值频率分离至 `imaginary_frequencies`，区分极小点与一阶鞍点。
- **样本溯源透明**：明确区分仓库内合成回归样例 (CLASS C)、第三方基准 (CLASS B)、受控仿真 (CLASS C-SIM) 与本地真实 Gaussian 输出日志 (CLASS A)。

---

## 2. 科学基准与回归数据集核对

| 测试用例 | 数据分类 | 理论级别 | 验证物理量与精确基准值 | MCP 解析与验证结果 | 状态 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **$H_2$ 单点能样例** (`h2_sp_reference.log`) | CLASS C (合成解析样例) | `HF/STO-3G sp` | $E = -1.11750588210\text{ a.u.}$, $q=0$, $M=1$, $\text{HOMO}=-0.57790$, $\text{LUMO}=+0.66970$, Gap=$1.24760$ | 精确匹配提取，`is_simulated=False` | **PASS** |
| **$H_2O$ 频率与热力学样例** (`h2o_freq_reference.log`) | CLASS C (合成解析样例) | `B3LYP/6-31G(d) freq` | $E=-76.4089528701\text{ a.u.}$, 3 实频 ($1648.5020, 3825.1200, 3935.4500\text{ cm}^{-1}$), $\text{ZPVE}=0.021540$, $H_{\text{corr}}=0.025320$, $G_{\text{corr}}=0.003920\text{ Hartree}$, $\mu=1.8540\text{ D}$ | 提取 3 实频 (0 虚频)，热力学修正与偶极矩完全匹配 | **PASS** |
| **过渡态虚频样例** (`ts_imag_reference.log`) | CLASS C (合成解析样例) | `B3LYP/6-31G(d) opt=ts freq` | 含唯一虚频 $-485.3200\text{ cm}^{-1}$ 与 2 实频 ($1250.4500, 1890.1200\text{ cm}^{-1}$) | `-485.32` 正确收入 `imaginary_frequencies` 并触发过渡态提示 | **PASS** |
| **SCF 发散失败样例** (`scf_failed_reference.log`) | CLASS C (合成解析样例) | `B3LYP/6-31G(d) opt` | `Convergence failure -- run terminated.`, `Error termination via Lnk1e in l502.exe` | `normal_termination=False`，诊断输出 SCF 改进建议 | **PASS** |
| **苯 ($C_6H_6$) SMILES 3D 与真实日志** | CLASS B (RDKit) + CLASS A (本地外部 G16 日志) | `B3LYP/6-31G(d,p) opt` | RDKit 12 原子六元环共面；本地外部 G16 Rev A.03 日志 `HF = -232.2582019 Hartree` | SMILES 构象校验通过；若本地存在外部真实日志则全量比对 4 项收敛判据与能量 | **PASS** (本机有外部日志时完整验证) |

> 注：以上 CLASS C 样本详细起源、字段与外部 CLASS A 日志的可移植性限制均已准确记录在 `tests/fixtures/PROVENANCE.md`。

---

## 3. 端到端受控仿真科研闭环验证 (`tests/test_scientific_workflow.py`)

在 `mock_mode=True` 安全仿真模式下执行了完整闭环流水线并校验严格能量隔离：
1. **化学输入与 3D 构建**：`CCO` (乙醇 SMILES) 经 RDKit ETKDGv3 + MMFF94s 生成 9 原子 `.gjf`。
2. **只读预检**：`submit_gaussian_calculation(dry_run=True)` 验证语法与 9 原子规模，签发 `integrity_token` (`grants_human_approval=False`)。
3. **仿真调度与标识**：`mock_mode=True` 启动 `backend.mock_worker`，返回 `is_simulated=True`、`real_gaussian_result=False`、`execution_mode="mock_simulation"`。
4. **状态轮询与能量隔离**：`get_gaussian_job_status` 返回 `last_energy=None`，合成值仅写入 `simulated_energy`，并附带 `simulation_warning`。
5. **结果解析隔离**：`parse_gaussian_output` 解析仿真 `.log` 时提取 `normal_termination=True`、结构收敛状态及轨道能隙字段用于流水线验证，同时强制输出 `is_simulated=True`、`real_gaussian_result=False`、`energy_source="mock_simulation_placeholder"`、`final_energy=None`，模拟能量仅保留在 `simulated_energy`。
6. **失败诊断闭环**：苯 `fail_scf=True` 仿真日志准确触发 `status="failed"`、`error_message` 拦截并接入 `diagnose_gaussian_error` 自动生成修复方案。
