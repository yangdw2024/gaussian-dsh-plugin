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
| `sobko_search` / `sobko_fetch` | 检索本地 Sobko 知识库（思想家公社帖子 + Multiwfn 手册，BM25） |

> 共 **19 个工具**，与 `src/index.js` 注册集合、系统提示 `GAUSSIAN_GUIDANCE` 清单一一对应。
> RDKit 和 OpenBabel 已随插件打包，目标机**无需**单独安装。

## 前置条件 / Prerequisites

插件只是"调度者"，以下专业软件需要你自己装在本机：

- **Gaussian 16**（`g16.exe` + `formchk.exe`）
- **Multiwfn ≥ 3.8**（http://sobereva.com/multiwfn/ ，免费学术使用）
- **VMD**（https://www.ks.uiuc.edu/Research/vmd/ ）

> 硬件建议：8 核 CPU、16 GB 内存（插件默认 mem=12GB / nproc=8，串行跑）。

## 安装 / Installation

> **当前版本（v0.2.0，本地开发版）仅支持"本地目录安装"**：插件包未发布 npm registry、未建 GitHub Release，后端 onedir 运行时随包 `runtimes/` 目录携带，不存在"插件市场搜索安装"与"首次启动自动下载预编译包"链路。方式 A / B 是未来公开发布形态，当前不可用。

### 方式 A：从 DSH 插件市场装（规划中，当前不可用）

发布到 registry 后：在 DSH 客户端 → 插件 → 添加插件，搜索 `@gd/gp` 安装；后端随 onedir 包携带。当前版本请勿按此方式操作。

### 方式 B：下载预编译后端（规划中，当前不可用）

未来公开发布后：从 Releases 下载 `gaussian-backend-win32-x64.zip` 解压，再在「添加插件」里填本地插件目录路径。当前版本后端已在包内 `runtimes/win32-x64/`，无需单独下载。

### 方式 C：本地目录安装（当前实际形态）

1. 把本插件目录放到固定位置（不要放 C 盘），例如 `E:\YDW\ChemDatas\gaussian-dsh-plugin`。
2. 前端改动后先构建产物：

```bash
npm install                # 前端依赖
npm run build              # esbuild 编译 lib/index.js、lib/client.js
```

3. 后端两种模式二选一：
   - **managed（默认，推荐）**：插件启动时自行拉起包内 `runtimes/win32-x64/gaussian-backend/gaussian-backend.exe`；需在用户环境变量设置 `GAUSSIAN_BACKEND_EXE` 指向该 exe 绝对路径（见配置表）。
   - **external**：先手动起后端，再启动插件复用（设置 `GAUSSIAN_BACKEND_MODE=external`、`GAUSSIAN_BACKEND_URL=http://127.0.0.1:8765`）。
4. 在 DSH → 设置 → 插件 → 添加插件，输入本插件目录绝对路径；DSH 写入 profile 的 `dependencies` 与 `dsh.profile.bundles` 双侧清单后，**完全退出 DSH（托盘退出、进程结束）再重开**生效。

### 方式 D：从源码直接跑后端（开发调试用）

```bash
pip install -r requirements.txt   # 后端依赖（rdkit 建议 conda 装）
python -m backend.app            # 手动起后端（默认 127.0.0.1:8765）
```

## 配置 / Configuration

后端可执行文件路径默认写了本机常见位置，**不一致就用环境变量覆盖**（重启后端 / 完全退出重启 DSH 生效）。

### 前端插件层（`src/index.js`，DSH 启动后端前读取）

| 环境变量 | 默认 | 说明 |
|----------|------|------|
| `GAUSSIAN_BACKEND_MODE` | `managed` | `managed`=插件自行拉起后端；`external`=复用已运行的外部后端，不负责关闭 |
| `GAUSSIAN_BACKEND_URL` | `http://127.0.0.1:8765` | external 模式下连接的后端地址 |
| `GAUSSIAN_BACKEND_EXE` | 包内自定位 `runtimes/win32-x64/gaussian-backend/gaussian-backend.exe` | managed 模式后端 exe 绝对路径；显式设置且文件存在时优先采用 |
| `GAUSSIAN_DATA_DIR` | 后端默认 `C:\Users\Administrator\.gaussian-dsh` | 任务记录 / 后处理产物 / 日志目录（透传给后端） |
| `GAUSSIAN_STARTUP_TIMEOUT_MS` | `30000` | 等待后端 health ready 的超时 |
| `GAUSSIAN_SHUTDOWN_TIMEOUT_MS` | `5000` | 受控关闭等待 `waitForExit()` 的超时 |

### 后端层（`backend/config.py`，后端进程读取）

| 环境变量 | 默认 | 说明 |
|----------|------|------|
| `GAUSSIAN_EXE` | `D:\G16W\g16.exe` | Gaussian 主程序 |
| `FORMCHK_EXE` | `D:\G16W\formchk.exe` | chk → fchk |
| `MULTIWFN_EXE` | `D:\Multiwfn\Multiwfn_3.8_bin_Win64\Multiwfn.exe` | Multiwfn |
| `VMD_EXE` | `D:\VMD\vmd.exe` | VMD |
| `OBABEL_EXE` | 插件内嵌 thirdparty > 环境变量 > `E:\openbabel-install-msvc\bin\obabel.exe` | OpenBabel（一般不用设） |
| `GAUSSIAN_WORK_DIR` | `E:\YDW\ChemDatas\Gjf` | 输入 / 输出 / chk 工作目录 |
| `GAUSSIAN_DATA_DIR` | `%USERPROFILE%\.gaussian-dsh` | 任务数据库与日志目录 |
| `GAUSSIAN_DEFAULT_MEM` | `12GB` | Gaussian 内存预算（硬上限 12288 MB，超出拒绝） |
| `GAUSSIAN_DEFAULT_NPROC` | `8` | 核数（硬上限 8，串行，勿并行） |
| `GAUSSIAN_MAX_ATOMS` | `300` | 单任务原子数硬上限，超出提前拒绝 |
| `GAUSSIAN_BACKEND_HOST` / `GAUSSIAN_BACKEND_PORT` | `127.0.0.1` / `8765` | 后端监听地址与端口 |
| `GAUSSIAN_MANAGED_TOKEN` | 未配置 | 管理端点 Bearer token；未配置时仅放行回环来源，配置后强制校验 |
| `SOBKO_PROJECT_DIR` | `E:\YDW\Trae_Sob\Sobko_MCP_project-main` | Sobko 知识库目录 |
| `SOBKO_MODE` | `bm25_only` | `bm25_only` 轻量检索；`hybrid` 需 Ollama embedding + rerank |
| `MULTIWFN_EXPECTED_VERSION` | `3.8` | Multiwfn 版本一致性校验，不符即 fail-fast |
| `POSTPROCESS_MAX_GRID_POINTS` | `16000000` | 后处理 cube 网格点上限，超出拒绝 |
| `GC_ON_STARTUP` | `1` | 启动时是否执行产物 TTL 回收（cube 7 天 / 图片 30 天 / 日志 30 天，不删 chk/gjf） |

## 快速测试 / Quick test

装好后跟 DSH 说：

> 用 `gaussian_status` 查后端状态，再用 `postprocess_capabilities` 确认 Multiwfn/VMD 都就绪。然后用 SMILES `c1ccccc1`（苯）生成一个 B3LYP/6-31G(d,p) 的优化输入，先不要提交。

## 局限性 / Limitations

- 目前仅在 Windows + Gaussian 16 + Multiwfn 3.8 上测试过；
- 后处理出图主要在小体系上端到端验证，大体系（如 186 原子）建议先小测；
- Gaussian/Multiwfn/VMD 是商业/专有软件，本插件不包含它们。

## 许可 / License

[MIT](./LICENSE)。本插件本身开源，但调用的 Gaussian 归 Gaussian Inc.、Multiwfn 归 Tian Lu、VMD 归 UIUC，各自遵循其许可。
