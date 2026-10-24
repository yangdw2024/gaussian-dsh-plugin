# gaussian-dsh-plugin

> 一个在 [DSH (DeepSeek Harness)](https://github.com/) 客户端里运行的 Gaussian 16 计算辅助插件，把 Gaussian、RDKit、Multiwfn、VMD 串成一条 AI 可调用的工具链。
>
> A DSH (DeepSeek Harness) plugin that turns Gaussian 16, RDKit, Multiwfn and VMD into an AI-callable toolchain.

---

## 这是什么 / What it does

你用自然语言跟 DSH 说一句"帮我优化这个分子"，插件会自动：

- SMILES / ChemDraw 文件 → 3D 建模 → 生成 Gaussian `.gjf` 输入；
- 串行提交 Gaussian 计算（防止在多核机器上并行跑崩）；
- 解析 `.out/.log`（能量、收敛、HOMO-LUMO、偶极、频率、热力学量）；
- 算完自动调 Multiwfn + VMD 出 **HOMO/LUMO 轨道图、ESP 表面图、RDG/NCI 弱相互作用图**。

You just talk to DSH in natural language. The plugin handles:
SMILES/ChemDraw file → 3D geometry → Gaussian input → serial job →
output parsing → Multiwfn/VMD post-processing (orbitals / ESP / RDG).

## 功能工具 / Tools

| 工具 | 作用 |
|------|------|
| `gaussian_status` | 后端与 Gaussian 可执行文件状态 |
| `generate_gaussian_input` | 生成 `.gjf`（校验方法/基组） |
| `generate_gaussian_input_from_smiles` | SMILES → RDKit 3D → Gaussian 输入 |
| `extract_structure_from_file` | 从 `.mol/.cdxml/.gjf/.out/.log/.xyz/.pdb` 识别 SMILES |
| `submit_gaussian_job` / `get_gaussian_job` / `list_gaussian_jobs` / `stop_gaussian_job` | 任务管理（串行） |
| `parse_gaussian_output` | 解析能量/收敛/HOMO-LUMO/频率/热力学 |
| `search_basis_sets` / `get_basis_set` | BSE 官方基组库 |
| `search_gaussian_keywords` | Gaussian 关键词查询 |
| `diagnose_gaussian_error` | 常见报错诊断 |
| `postprocess_capabilities` | 探测 Multiwfn/VMD/formchk 是否就绪 |
| `create_postprocess_task` / `get_postprocess_task` / `list_postprocess_tasks` | 轨道/ESP/RDG 出图（异步） |

> RDKit 和 OpenBabel 已随插件打包，目标机**无需**单独安装。

## 前置条件 / Prerequisites

插件只是"调度者"，以下专业软件需要你自己装在本机：

- **Gaussian 16**（`g16.exe` + `formchk.exe`）
- **Multiwfn ≥ 3.8**（http://sobereva.com/multiwfn/ ，免费学术使用）
- **VMD**（https://www.ks.uiuc.edu/Research/vmd/ ）

> 硬件建议：8 核 CPU、16 GB 内存（插件默认 mem=12GB / nproc=8，串行跑）。

## 安装 / Installation

### 方式 A：下载预编译后端（推荐，Windows）

1. 去 [Releases](../../releases) 下载最新 `gaussian-backend-win32-x64.zip`，解压到任意目录；
2. 在 DSH 客户端「添加插件」里填本地插件目录路径（见下）。

### 方式 B：从源码运行

```bash
git clone https://github.com/<your-name>/gaussian-dsh-plugin.git
cd gaussian-dsh-plugin
npm install                      # 前端依赖
npm run build                    # 编译 lib/
pip install -r requirements.txt # 后端依赖（rdkit 建议 conda 装）
python -m backend.app            # 手动起后端（DSH managed 模式会自动拉起）
```

### 在 DSH 里加载插件

DSH → 设置 → 插件 → 添加插件 → 在最上面输入框填**本插件目录的绝对路径**：

```
C:\...\gaussian-dsh-plugin
```

## 配置 / Configuration

后端可执行文件路径默认写了常见位置，**不一致就用环境变量覆盖**（重启后端生效）：

| 环境变量 | 默认 | 说明 |
|----------|------|------|
| `GAUSSIAN_EXE` | `D:\G16W\g16.exe` | Gaussian 主程序 |
| `FORMCHK_EXE` | `D:\G16W\formchk.exe` | chk→fchk |
| `MULTIWFN_EXE` | `D:\Multiwfn\...\Multiwfn.exe` | Multiwfn |
| `VMD_EXE` | `D:\VMD\vmd.exe` | VMD |
| `OBABEL_EXE` | （插件内嵌，一般不用设） | OpenBabel |
| `GAUSSIAN_DEFAULT_MEM` | `12GB` | Gaussian 内存 |
| `GAUSSIAN_DEFAULT_NPROC` | `8` | 核数（**串行，勿并行**） |
| `GAUSSIAN_WORK_DIR` | 工作目录 | 输入/输出存放 |

## 快速测试 / Quick test

装好后跟 DSH 说：

> 用 `gaussian_status` 查后端状态，再用 `postprocess_capabilities` 确认 Multiwfn/VMD 都就绪。然后用 SMILES `c1ccccc1`（苯）生成一个 B3LYP/6-31G(d,p) 的优化输入，先不要提交。

## 局限性 / Limitations

- 目前仅在 Windows + Gaussian 16 + Multiwfn 3.8 上测试过；
- 后处理出图主要在小体系上端到端验证，大体系（如 186 原子）建议先小测；
- Gaussian/Multiwfn/VMD 是商业/专有软件，本插件不包含它们。

## 许可 / License

[MIT](./LICENSE)。本插件本身开源，但调用的 Gaussian 归 Gaussian Inc.、Multiwfn 归 Tian Lu、VMD 归 UIUC，各自遵循其许可。
