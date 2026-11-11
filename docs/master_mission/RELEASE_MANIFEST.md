# Release Manifest — `gaussian-dsh-plugin` `v0.3.0` (`READY_FOR_APPROVAL`)

本清单记录由 `scripts/assemble_release_candidate.py --version 0.3.0` 构建并经独立 SHA-256 核验通过的 `dist/release-candidate/` 全部发布产物。

## 1. 产物清单、体积与 SHA-256 校验值

| 产物相对路径 (`dist/release-candidate/`) | 大小 (Bytes) | SHA-256 (`SHA256SUMS.txt` 实测值) | 用途与目标平台 |
| :--- | ---: | :--- | :--- |
| `yangdw2024-gp-0.3.0.tgz` | `64,695,136` | `01e184a9e669eac91755cbf110f7d25f6b79332139a79f834249f0705ab5f510` | **主 npm 发布包** (`@yangdw2024/gp`, `1158` files, Win x64 运行时 + DSH 插件) |
| `gd-gp-0.3.0.tgz` | `64,695,141` | `98d10eaacd40d0fad1d228c1dc4207749099ebc42438e2605f96ff3bc7fbac44` | 向后兼容短包名 (`@gd/gp`, `1158` files) |
| `gaussian-backend-0.3.0-win32-x64.zip` | `64,053,516` | `a54d55d483f5e8c6daa28c472e193fa87cbd673985441a7601ca94a0496d2e8e` | 独立 Windows x64 编译后后端 (`b/gaussian-backend.exe` + Open Babel `3.2.1` + `runtime.json`) |
| `gaussian-mcp-server-0.3.0-src.zip` | `135,504` | `7beabd87e6a5f607ccdd6fd18315f01feb34066e0222ad7aaf2059cab97776a1` | 便携纯源码 Python MCP Server 包 (`47` clean files, 无 `__pycache__/`) |
| `requirements-mcp.txt` | `479` | `f4f9795c368787f5f193c3274168c56fa57417c6708f453a5992f4ef8e84f873` | 精确锁版本的 Python 3.12 MCP 依赖列表 |
| `agensi/gaussian-job-setup-v0.3.0.zip` | `7,573` | `f89952ed9a8d395746166e3fe204c18eb321fe5e951be8486ab50b4c656be609` | Agensi Skill 1（含 `SKILL.md` 根目录 + `gjf_helper.py`） |
| `agensi/gaussian-output-analysis-v0.3.0.zip` | `6,653` | `812a75dbbb9425a49b7fb173a8ed8f4735f088a167e31ac95cb41962f11eb952` | Agensi Skill 2（含 `SKILL.md` 根目录 + `log_analyzer.py`） |
| `agensi/gaussian-postprocessing-v0.3.0.zip` | `5,610` | `466f8833af4884f01d631860e1cabcb74f8f5f481787a6f49c1925e107bf523e` | Agensi Skill 3（含 `SKILL.md` 根目录 + `multiwfn_recipe.py`） |
| `RELEASE_NOTES.md` | `1,186` | `db1124c9181bda748185429ad8194dd581c651e4faa50d917fb39c9782fadeb3` | GitHub Release 草案说明 |
| `SHA256SUMS.txt` | — | *(校验文件本身，含上述 9 项全量摘要)* | 全量 Release Candidate 校验清单一键核对 |

## 2. 发布校验指标汇总

- **全量测试结果（最后一次代码与构建变更后运行）**：`Ran 110 tests in 34.319s — OK` (`EXIT=0`)
- **Windows `MAX_PATH < 260` 指标**：
  - `runtimes/win32-x64` 文件总数：`1064`；包内最长相对路径：`96` 字符 (`runtimes/win32-x64/b/rdkit.libs/RDKitEnumerateStereoisomers-ed3221ec6868a1fd4f3cf031a2164a74.dll`)
  - 模拟 DSH `147` 字符 `@yangdw2024/gp` 安装路径计算：`243 < 260`
  - 隔离 `153` 字符深度 DSH 前缀 `npm install --offline` 实测解压最长路径：`249 < 260`，且深度目录下 `b/gaussian-backend.exe` 在 `0.5s` 内拉起 (`version=0.3.0`) 并成功完成 `/v1/molecules/from-smiles` (`c1ccccc1`) 与 `/v1/admin/shutdown`
- **密钥与敏感路径扫描**：`git ls-files` 全仓秘密扫描 `0 hits`；Agensi 3 个 ZIP 零私人绝对路径/零凭证校验通过；`MCP_SRC_ZIP` 含 `47` 干净文件（无 `__pycache__`/`.pyc`/`.bak`）。
