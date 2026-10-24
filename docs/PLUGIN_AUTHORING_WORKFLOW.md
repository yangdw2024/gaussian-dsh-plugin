# DSH 本地插件标准制作流程（实战版）

> 本文来自 `gaussian-dsh-plugin` 一次完整排障：插件能构建、能手动运行，但 DSH 里装不上、加载失败、后端起不来。
> 最终定位到 **4 个独立根因**，全部修复。这里把它们固化成可复用的流程与检查清单，供其他 agent 定制任何"带二进制运行时"的 DSH 插件。

---

## 0. 先认清 DSH 插件的三层模型

一个本地（out-of-tree）DSH 插件在运行时会涉及三份东西，**任何一份不同步都会导致加载失败**：

| 层 | 位置 | 作用 |
|---|---|---|
| **A. 源码项目** | 你写的目录，如 `E:\...\gaussian-dsh-plugin` | `package.json`、`src/`、`lib/`、`runtimes/`、`cordis.patch.yml` |
| **B. generation 快照** | `%APPDATA%\dsh-desktop\harness\profiles\.generations\live\<generationId>\` | DSH 从 A 复制出来的只读快照，含 `source/<name>/` 与 `node_modules/<name>/` |
| **C. profile 装配区** | `%APPDATA%\dsh-desktop\harness\profiles\web\` | DSH 真正 import 的入口，`node_modules/<name>` 必须指向 B |

> `generationId = <包名去@并把/换成+> + "+" + <version> + "+" + <lockfile sha256 前12位>`
> 例：`@gd/gp` + `0.2.0` → `gd+gp+0.2.0+<hash>`

**关键点：C 里的 `node_modules/<name>` 必须能解析到 B 里一个带 `package.json` 的真实目录。** DSH 的解析函数（`dsh-app-boot` 的 `resolveBundleDir`）逻辑是：

```js
for (const anchor of [installAnchor, join(profileDir, "package.json")]) {
  for (const searchPath of createRequire(anchor).resolve.paths(packageName) ?? []) {
    const candidate = join(searchPath, packageName);
    if (existsSync(join(candidate, "package.json"))) return candidate;
  }
}
throw new Error(`${binName}: cannot resolve profile bundle ${JSON.stringify(packageName)} ...`);
```

它**不看 `exports` 字段**，只看目录 + `package.json` 是否存在。所以符号链接/junction 完全可用。

---

## 1. 标准制作流程（8 步）

### 步骤 1｜确定包名，越短越好（重要）

Windows 上 `MAX_PATH = 260`。`generationId` 目录名会直接嵌进最终 exe 的路径里，包名越长，越容易触发长路径故障（见第 3 节）。

- ❌ `@gaussian/dsh-plugin-gaussian` → 目录名 33+ 字符
- ✅ `@gd/gp` → 目录名 11 字符

**规则：本地插件包名控制在 10 字符以内。** 短包名不会让 DSH 去 registry 查找——DSH 只看 `profiles/web/node_modules/` 下有没有对应目录。

### 步骤 2｜`package.json` 必备字段

```json
{
  "name": "@gd/gp",
  "version": "0.2.0",
  "type": "module",
  "main": "./lib/index.js",
  "private": true,
  "dsh": { "bundle": { "patch": "./cordis.patch.yml" } }
}
```

- `dsh.bundle.patch` 必须存在，否则报 `profile bundle X declares no dsh.bundle in its package.json`。
- 客户端入口（若有）通过 `window.__ModuleLoader__.load({ id: "<包名>", ... })` 注册，**id 必须等于包名**。

### 步骤 3｜`cordis.patch.yml` 的 name 必须等于包名

```yaml
- insert:
    - id: gaussian
      name: '@gd/gp'          # ← 必须与 package.json name 完全一致
      config:
        backendMode: !!js process.env.GAUSSIAN_BACKEND_MODE ?? 'managed'
        baseUrl: !!js process.env.GAUSSIAN_BACKEND_URL ?? 'http://127.0.0.1:8765'
```

**改包名时，这是最容易漏的一处。** 漏了会报 `cannot resolve profile bundle "@gd/gp"`，因为 patch 里 insert 的还是旧名。

### 步骤 4｜profile 侧四处同步

`%APPDATA%\dsh-desktop\harness\profiles\web\package.json`：

1. `dependencies["@gd/gp"] = "0.2.0"`
2. `dsh.profile.bundles` 数组里包含 `"@gd/gp"`
3. `dsh.desktop.generationProjection.plugins` 里登记 generation 名
4. `pnpm.overrides["@gd/gp"] = "link:../.generations/live/@gd+gp+0.2.0/node_modules/@gd/gp"`

外加 `.generations/desired.json`（纯字符串数组）里也要有对应 generation 名。

### 步骤 5｜建立 C→B 的联接

假设 DSH 生成的 generation 快照只给了 shim 包（缺 `runtimes/`），把你项目的完整目录接上去：

```powershell
# PowerShell 里用 cmd /c mklink 才稳定（git-bash 下引号会崩）
cmd /c mklink /J "C:\...\profiles\web\node_modules\@gd\gp" "C:\...\.generations\live\@gd+gp+0.2.0\node_modules\@gd\gp"
```

验证：

```powershell
(Get-Item "...\node_modules\@gd\gp").LinkType   # 应为 Junction
(Get-ChildItem "...\node_modules\@gd\gp").Count  # 应等于源项目条目数
```

### 步骤 6｜写"从 DSH 真实入口自定位"的验证脚本

**不要用项目路径验证，必须用 DSH 实际 import 的路径。** 否则你验证的是另一份文件。

```js
// scripts/verify_installed_runtime.mjs
const ENTRY = 'C:/Users/<user>/AppData/Roaming/dsh-desktop/harness/profiles/web/node_modules/@gd/gp/lib/index.js'
const metaUrl = pathToFileURL(ENTRY).href
const runtimesDir = fileURLToPath(new URL('../runtimes/', metaUrl))
// 然后逐项断言：runtime.json 存在、target 匹配、exe 存在、sha256 与清单一致、
// 关键 Python 包（如 pydantic_core）文件齐全
```

**8 项断言全 PASS 才算装好。** 本项目实测输出：

```
[1] runtimes 目录存在 true
[2] runtime.json 存在 true  (version 0.2.0 / target win32-x64)
[3] exe 路径长度 148 PASS
[4] exe 存在 true
[5] exe sha256 e75fbdc99d...010c
[6] manifest 条目 gaussian-backend/gaussian-backend.exe
[7] sha256 一致 PASS
[8] pydantic_core 完整 PASS
```

### 步骤 7｜打包必须走项目自带脚本（不要手敲命令）

conda 环境常带 `pathlib` 后门包，会让 PyInstaller 直接报：

```
ERROR: The 'pathlib' package is an obsolete backport ... incompatible with PyInstaller
```

规避方式是构建前把 `pathlib-1.0.1.dist-info` 临时改名，`finally` 里恢复——**这必须写在脚本里**：

```powershell
& $PythonPath -m PyInstaller --clean -y --distpath dist packaging\<name>.spec
```

### 步骤 8｜重启 DSH 并验证端口

重启后必须验证**服务真的来自新进程**，否则会被旧进程冒充：

```bash
netstat -ano | grep ':8765'
tasklist //FI "PID eq <pid>"      # 确认占用者是新 exe，不是遗留 python.exe
curl http://127.0.0.1:8765/v1/status
```

---

## 2. 四个真实根因（现象 → 诊断 → 修复）

### 根因 1：`runtimes/` 没进 DSH 真正加载的包

**现象**：DSH 里插件工具不出现。
**诊断**：`profiles/web/node_modules/@gd/gp/` 只有入口文件，没有 `runtimes/`（DSH 的 shim 包）。
**修复**：第 5 步 junction。
**判据**：插件代码用 `new URL('../runtimes/', import.meta.url)` 自定位二进制，包位置变了路径就变了。

### 根因 2：PyInstaller onedir 里 `pydantic_core` 是空壳

**现象**：exe 一启动就崩：

```
ModuleNotFoundError: No module named 'pydantic_core._pydantic_core'
[PYI-316:ERROR] Failed to execute script 'entrypoint' due to unhandled exception!
```

**诊断**：`_internal/pydantic_core/` 里**只有一个** `.pyd`，缺 `__init__.py` / `core_schema.py` / `.pyi` / `py.typed`（对照 site-packages 是 6 个条目）。
**机制**：conda 版 `__init__.py` 被判为纯模块塞进 PYZ 归档，onedir 只落了二进制 → 空壳包遮蔽 PYZ 子模块。
**修复**：spec 里显式收集

```python
hiddenimports += collect_submodules("pydantic_core", on_error="raise")
datas += collect_data_files("pydantic_core", include_py_files=True)
binaries += collect_dynamic_libs("pydantic_core")
```

### 根因 3：MAX_PATH 长路径（最隐蔽）

**现象**：**同一个 exe、同一个 sha256**，从短路径启动成功，从 DSH 的 205 字符路径启动报根因 2 的同一个错。

**决定性对照实验**：

| 路径长度 | 结果 |
|---|---|
| 58 字符（`dist/`） | ✅ 成功 |
| 8 字符（`C:/tmpgb/gb`） | ✅ 成功 |
| 205 字符（DSH generation） | ❌ ModuleNotFoundError |
| 221 字符（人造深目录） | ❌ 同样报错（该目录下最长文件全路径 314 字符） |

**结论：这是路径长度问题，不是代码或打包问题。** PyInstaller bootloader 在长路径下无法把 `_internal/<pkg>` 正确加入 `sys.path`。

**修复**：缩短 `generationId`（第 1 步短包名）。本项目从 79 字符降到 11 字符，exe 全路径 174 字符，一次通过。
**无效方案**：仅开注册表 `LongPathsEnabled` 不够——bootloader 是 C 层实现，不走 Node/Python 的长路径前缀。

### 根因 4：改包名后 `cordis.patch.yml` 没同步

**现象**：DSH 日志刷

```
warn hmr: Error: dsh: cannot resolve profile bundle "@gd/gp" from the dsh installation or
...\profiles\web; run 'dsh plugin --profile web install' if its dependency is not installed
warn hmr: Error: dsh: failed to prepare profile bundle @gd/gp
```

**诊断**：日志里 `resolveBundleDir` 抛错 ⇒ profile 的 `node_modules/@gd/gp/package.json` 不存在**或** `dsh.profile.bundles` 没登记。本项目实际是插件自带 patch 仍以旧名 insert。
**修复**：第 3 步 + 第 4 步全量同步包名。

---

## 3. Windows 环境踩坑清单

| 坑 | 表现 | 对策 |
|---|---|---|
| PowerShell 读无 BOM 的 UTF-8 `.ps1` | 按 GBK 解码，中文注释破坏语法 → `UnexpectedToken 'Building'` | 所有 `.ps1` 用 `encoding='utf-8-sig'` 写入（首 3 字节 `EF BB BF`） |
| `cmd //c mklink /J` 在 git-bash | 「文件名、目录名或卷标语法不正确」 | 改用 PowerShell 里的 `cmd /c mklink /J`，或 `New-Item -ItemType Junction` |
| `robocopy` 复制含 `@` 的目录 | `node_modules\@gd\gp` 变成 `node_modules\gd\gp`（`@` 被吃） | 复制后用 `python -X utf8 -c "print(repr(os.listdir(p)))"` 核对；或同卷直接 `os.rename` |
| `shutil.copytree` 复制深路径 | `[WinError 3] 系统找不到指定的路径` | 用 robocopy；删除用 `robocopy /MIR 空目录` 镜像而非 `Remove-Item` |
| 旧进程冒充服务 | `/v1/status` 返回 200，但其实是旧的 `python.exe` | `tasklist //FI "PID eq <pid>"` 确认占用者身份；`/health` 404 也是线索 |
| bash 工具里的 python 写项目目录 | `PermissionError` | 用 `edit` / `write` 文件工具改源码，python 只用于读和改 `%APPDATA%` |
| 自己重启 DSH | kill 主进程后新实例 `render-process-gone: crashed`，留下孤儿 GPU/renderer 进程 | **让用户手动完全退出 DSH 再启动**，不要从脚本里的子进程 `Start-Process` 拉起 |

---

## 4. 验收检查表（照着打勾）

```
[ ] 包名 ≤10 字符，且 6 处一致：package.json / cordis.patch.yml / profile bundles /
    profile dependencies / pnpm.overrides / generation.json
[ ] profile/node_modules/<name>/package.json 存在（junction 也可）
[ ] 从 DSH 真实入口自定位到 exe，路径 <260 字符
[ ] exe sha256 与 runtime.json 清单一致
[ ] PyInstaller 关键包文件齐全（如 pydantic_core 5 个条目）
[ ] 直接跑部署路径 exe：/v1/status 返回 status ok
[ ] 8765 端口干净（无遗留 python.exe / 旧 exe）
[ ] 手动完全重启 DSH 后，插件工具出现、后端自动监听 8765
[ ] harness.log 无 "cannot resolve profile bundle" / "failed to prepare profile bundle"
```

---

## 5. 排障顺序（从快到慢）

1. `tail harness.log | grep -i plugin` —— 有 `cannot resolve` 就是配置/包名问题；有 `failed to prepare` 就看 cause。
2. `node scripts/verify_installed_runtime.mjs` —— 从 DSH 真实入口验 8 项。
3. 直接跑部署路径的 exe —— 报 `ModuleNotFoundError: No module named 'pydantic_core.*'` 时，**先换短路径试**，一步区分"打包问题"还是"路径问题"。
4. 只有第 3 步在短路径也失败，才回头查 spec 与构建链。

**这个顺序能省掉 80% 的无用排查。**
