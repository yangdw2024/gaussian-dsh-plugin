# DeepSeek Harness（DSH）架构与第三方插件开发/安装参考

> **2026-10-26 更新指针**：DSH 0.12.1 新布局根为 `%APPDATA%\dsh-desktop\harness\`，活跃 profile 为 `profiles\web\`，generation 快照在 `profiles\.generations\live\<pkg>+<name>+<version>\`，web `node_modules\<pkg>` 为 Junction；旧路径 `C:\Users\Administrator\.dsh\profiles\desktop` 为历史遗留、不被当前版本读取。新布局三层模型（profile package.json dependencies + bundles、generation.json、shim manifest、Junction 联接）详见 `docs/PLUGIN_AUTHORING_WORKFLOW.md` 与 R17C 复核报告 `docs/R17C_RELEASE_RECHECK_20261026.md` §2.3；下方 2026-10-21 记录的旧 profile 路径、旧 app.asar 体积与旧布局装机包仅作历史过程保留。

> 整理日期：2026-10-21 ｜ 本机 DSH：Electron 桌面端，`E:\DSH\resources\app.asar`（182.8 MB，mtime 2026-10-17），profile 目录 `C:\Users\Administrator\.dsh\profiles\desktop`。
> 用途：把 DSH 的"进程分层、插件清单、装载链路、服务/事件、subprocess 契约、profile 与插件管理、排障决策"固化成可复用参考，后续新增/安装/排障 DSH 第三方插件直接对照本文，不再从零逆向。
> 资料分级：**【官方】**= 官方仓库/文档原文约定；**【本机实证】**= 解包本机 `app.asar` 读到的源码位置或实测行为；**【实测坑】**= gaussian 插件本轮真实踩过并修掉的问题，编号对应 `FIX_REPORT_20261020.md`。

---

## 0. 资料来源（2026-10-21 联网核对，时效性以官方 master 为准）

| 主题 | 官方地址 |
|------|----------|
| 总体架构（Cordis / profile / bundle / 层序 / 桌面端 / 核心包 / seam / 新行为归属） | https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/architecture.zh.md |
| Cordis 入门（插件对象、ctx、inject、事件分发、可逆副作用） | https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/cordis-primer.zh.md |
| 扩展实操手册（工具/钩子/UI/协议驱动，功能→机制映射表） | https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/cookbook/extension-cookbook.zh.md |
| 添加 workspace 包（manifest 不变式、locale meta、icon 回退规则） | https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/cookbook/adding-a-package.zh.md |
| 工具编写参考（defineTool、execute 约定、后台任务、策略钩子、UI 卡片） | https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/cookbook/adding-a-tool.zh.md |
| 配置表单卡片（Config volatile、plugins.detail.* 槽位、client 半侧挂载规则） | https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/cookbook/adding-a-settings-card.zh.md |
| 客户端模块系统（host 扫描、/plugins bundle、惰性 CJS factory、release 一致性、构建要求） | https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/client/modules/README.zh.md |
| 插件管理器（开关写哪、bundles 选择、兼容性检查、compatibility.json 豁免、HMR/重启、失败回滚） | https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/boot/plugin-manager/README.zh.md |
| 子进程 seam（spawn spec 全显式、stdio 处置、handle.terminate/waitForExit、DSH_* 环境命名空间） | https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/subsystems/subprocess.zh.md |
| 第一个插件 / 第一个工具（最小形态、patch insert、inject、对象形式插件） | `docs/user/develop/basic/index.zh.md`、`docs/user/develop/basic/tool.zh.md` |

> 官方文档面向仓库内第一方包；第三方本地/`file:` 插件在清单字段、patch 写法、构建产物上与第一方等价，区别只在"不由 `pnpm run build` 产出，需要作者自己产出 `lib/index.js`、`lib/client.js`"。

---

## 1. 一句话架构

**【官方】** DSH 是"一切皆插件"的 Cordis 应用：模型适配器、工具、会话、沙箱、存储、agent loop、UI 全是插件；扩展方式是把插件挂到其他插件旁边，不存在特权内核。插件通过 **服务（service）** 与 **类型化事件（event）** 协作；所有注册都是副作用，卸载时由框架撤销。

### 1.1 三个平面（Host / Web Client / Desktop 壳）

**【官方】**
- **Host 平面（Node 运行时）**：跑 Cordis 服务、工具注册表、会话日志、agent loop、subprocess 提供方等；面向模型的工具注册在 `ctx.tools`，提示词片段进 `ctx.systemPrompt`。
- **Web Client 平面（浏览器）**：渲染 GUI、聊天节点、插件管理页；通过 RPC/流与 Host 通信。浏览器半侧插件负责 UI 状态卡、聊天节点、设置表单等。
- **Desktop 壳（Electron）**：签名资源内带精确匹配的 dsh 生产运行时，拥有保留的 `$DSH_HOME/profiles/desktop`；Electron Node 模式启动私有 Desktop Host，Host 调共享 CLI profile runner 与完整 Web 应用；窗口先加载打包 Web 资源，**启动注入后在同一文档里激活客户端插件**；Node IPC 承载启动注入、就绪、致命错误、关闭。Desktop 与 npm CLI 共享产品数据，但包、启用选择、锁文件保持独立。

**【本机实证】** 本机即 Desktop 形态：
- Host 运行目录与 profile：`C:\Users\Administrator\.dsh\profiles\desktop\`
- 已安装第三方包快照：`node_modules\@aifs`、`@autorest`、`@gaussian`
- 崩溃日志分两类：`crash-*-host.log`（Host/Node 侧）、`crash-*-web-boot.log`（Web 引导/客户端装配侧），目录 `C:\Users\Administrator\AppData\Roaming\@deepseek-ai\dsh-desktop\logs\`。

### 1.2 Profile、组合包（bundle）与层序

**【官方】** 运行中的 `dsh` 是一棵插件树，启动时按序叠加各层：

1. 先按 profile `package.json` 的 `dsh.profile.bundles` **顺序**应用每个组合包自带的 `dsh.bundle.patch`（即包内 `cordis.patch.yml`）；
2. 再叠加 profile 自己的 `cordis.patch.yml`；
3. 再叠加 home 级 patch；
4. 最后是 `--patch` overlay。

一条 patch 按 `id` 定位某个条目，替换其整个 `config`，或插入新条目。组合包是 Cordis 配置项及其挂载代码的分发格式，插入的内容始终可被其上各层 patch 覆盖。

**【本机实证】** 本机 profile 三个关键文件：
- `profiles/desktop/package.json`：`dependencies`（安装了哪些包）+ `dsh.profile.bundles`（**启动时真正装载哪些包**）。两者是两份清单，只进 `dependencies` 不进 `bundles` 的包不会被加载（实测坑 R13a，见第 8 节）。
- `profiles/desktop/cordis.yml`：根条目列表，当前恒为 `[]`，文件头注释明确"编辑 `cordis.patch.yml`，不要改本文件"。
- `profiles/desktop/cordis.patch.yml`：用户/ profile patch 层，最后叠加；可按 id 覆盖 config、`disabled: true` 关闭条目、`- insert:` 插入新条目。
- `pnpm-lock.yaml`、`pnpm-workspace.yaml`（本机 `nodeLinker: hoisted`、`autoInstallPeers: false`）由 pnpm 与插件管理器维护，不要手改。

**【关键规则】**
- **只写进 `dependencies` 不等于激活**：第三方包必须出现在 `dsh.profile.bundles`，其 `cordis.patch.yml` 里的 `insert` 才会进入 host loader，否则后端 entry 不存在、客户端半侧也扫描不到（R13a）。
- **profile patch 最后叠加**：即使包已进 bundles，profile `cordis.patch.yml` 里残留 `- id: <插件id> / disabled: true` 会把该 entry 关掉（R13b）。
- 查看本机实际装配出的配置树：`dsh --profile web --dump-config`（桌面端等价于在 profile 目录读 `package.json` + 各层 patch）。

### 1.3 Cordis 最小模型

**【官方】**
- 插件是实现 Service 的对象：带可选 `inject` 与 `apply(ctx)` 的函数，或 Service 子类；生命周期由 Cordis 挂到当前上下文。
- **上下文 `ctx` 是服务容器**：服务占据稳定 `ctx.<key>`（`ctx.tools`、`ctx.llm`、`ctx.sessions`…），其他插件按 key 查找服务，不导入具体实现。
- **`inject` 声明服务依赖**：声明所需服务后，框架等这些服务就绪才启动插件；加载顺序由服务依赖表达，不靠手动编排。
- **类型化事件**：服务注册事件名，以 `emit / waterfall / parallel / serial / bail` 分发。`waterfall` 监听器收 `(...args, next)`，必须 `next()` 委托；`agent/turn-stopping` 是 `serial`，无 `next()`。
- **注册是可逆副作用**：提示词片段、工具 schema、适配器、提供方、监听器通过 `ctx.effect()` 或 `ctx.on()` 安装；`ctx.effect()` 返回的 disposer 在 reload/teardown 时撤销。需要手动清理的网络连接等，在 effect 里返回清理函数。

插件三种形态（官方示例）：
```ts
// 函数形式
export const name = 'my-plugin'
export const inject = ['tools']
export function apply(ctx: Context) { /* ... */ }

// 对象形式（第三方本地打包最常用）
export default { name: 'my-plugin', inject: ['tools'], apply(ctx) { /* ... */ } }

// 类形式（需要向其他插件提供服务时用 Service 子类）
export default class MyService extends Service { static inject = ['tools']; constructor(ctx) { super(ctx, 'myService') } }
```

---

## 2. 第三方插件的双半侧与清单字段

### 2.1 Host 半侧与 Client 半侧

**【官方】** 仓库用相互隔离的 Host / Client 两个 aggregate 做类型检查；一个包只属于其中一个，拆分（`api/remotes` 等）除外。对外可观察地理解为：

| 半侧 | 产物 | 运行平面 | 能用的服务（典型） | 职责 |
|------|------|----------|-------------------|------|
| Host 半侧 | `./lib/index.js`（`main` / `exports["."]`） | Node Host | `tools`、`systemPrompt`、`subprocess`、`agents`、`sessions`、`llm`、`jobs`、`commands`、`configForms`… | 注册面向模型的工具、注入提示词片段、拉起/管理外部后端进程、提供 Host 服务、读写 Host 侧状态 |
| Client 半侧 | `./lib/client.js`（`exports["./client"]`，`dsh.client.platform === "web"`） | 浏览器 Web Client | `slots`、`locale`、`configForms`、`timer`、`modules`… | 注入 UI 状态卡、聊天节点、设置表单、按钮徽标等界面内容 |

**【本机实证】** gaussian 插件即双半侧：`lib/index.js` 在 Host 注册 `tools` + `systemPrompt`，`inject=["tools","systemPrompt"]`，managed 模式 `ctx.inject(["subprocess"], ...)` 拉起后端；`lib/client.js` 在浏览器向 `plugins.item` 槽位注册状态卡，`inject=["slots","locale"]`。

### 2.2 package.json 清单字段对照表（第三方本地插件必备）

| 字段 | 作用 | 不满足的后果 | 官方依据 |
|------|------|--------------|----------|
| `"type": "module"` | ESM，与 Host 模块解析一致 | 导出/动态 import 形态错乱 | adding-a-package 不变式 |
| `"main": "./lib/index.js"` | Host 半侧入口 | Host 找不到插件 | 同上 |
| `"exports"` | `".": "./lib/index.js"`、`"./client": "./lib/client.js"`、`"./package.json": "./package.json"` | client 半侧不被发现；包元信息读不到 | client/modules、adding-a-settings-card |
| `"dsh.bundle.patch": "./cordis.patch.yml"` | 组合包 patch 文件路径，bundle layer 按此插入 entry | app-boot 抛 "no dsh.bundle"，bundle 进 `skippedBundles` | architecture §Profile 与组合包 |
| `"dsh.client.platform": "web"` | 声明这是浏览器半侧包；非 web 静默跳过 | client-modules 不扫描本包 client | adding-a-settings-card、client-modules |
| `"dsh.client.inject": ["<宿主提供的客户端服务包名>", ...]` | client 启动图等待的基座客户端服务包（如 `@deepseek-ai/dsh-client-ui-plugin-manager`、`@deepseek-ai/dsh-client-locale`） | 对应服务缺失时 client fiber pending/失败 | client-modules §声明客户端插件 |
| `engines.dsh` 或 `peerDependencies` 中 `@deepseek-ai/dsh*` | DSH 运行时版本兼容要求 | 不满足且未豁免会在安装/启动前被拒 | plugin-manager §版本兼容性 |
| `engines.node` | 仅 Node 下限，**不参与 DSH 兼容判断** | — | 本机实证 evaluatePluginCompatibility 只读 `engines.dsh` 与 dsh peer |

**【本机实证】** 兼容性函数 `evaluatePluginCompatibility(manifest, exemptions, runtimeVersion)`：先看 `engines.dsh`（存在才比对）；否则遍历 `peerDependencies`，只校验 `@deepseek-ai/dsh` 与 `@deepseek-ai/dsh-*` 范围；两者都没有 → requirements 为空 → 直接放行。豁免存于 profile `compatibility.json`，键为精确 `package-name@version`，值为精确 DSH 运行时版本列表；升级插件或 DSH 后豁免不继承。

### 2.3 cordis.patch.yml（bundle patch）的 entry 写法

**【官方】** 组合包 patch 以 id 定位条目；第三方包通常在包内 `cordis.patch.yml` 用 `- insert:` 注册自己的 Host 插件行，把包目录作为模块名指向 Host 入口：

```yaml
- insert:
  id: gaussian                      # 条目稳定 id（profile patch 按此 id 覆盖/禁用）
  name: "@gaussian/dsh-plugin-gaussian"   # 模块说明符，解析到包的 Host 入口
  config: { /* 传给插件 Config 的默认值，可选 */ }
```

- `id` 是后续 profile patch、client 状态页、开关状态共用的稳定标识，不要随版本改。
- `name` 是模块说明符；**client 半侧只挂在"说明符恰为裸包名"的那一行**。把一个包拆成多行时，半侧留在根行；需要在其他行关闭后仍保留页面的子插件应作为独立包发布（官方 adding-a-settings-card §5）。
- `- id: <existing> / config: {...}` 是覆盖已有条目配置；`- id: <x> / disabled: true` 关闭条目。

### 2.4 展示元信息（标题/描述/图标回退）

**【官方】** 标题、描述可由 `locale/<lang>.json` 的 `meta.title`、`meta.description` 提供；回退链：
- 标题：locale `meta.title` → 包根 `package.json.name` → 完整 Cordis 插件名。
- 描述：locale `meta.description` → 包根 `package.json.description` → 不显示描述。
- 图标：清单顶层 `"icon": "./icon.svg"` 或导出 `"./icon"`；仅支持 ≤256 KiB 的 SVG/PNG/JPEG/WebP，必须自包含、位于包内；解析到包外的绝对路径/URL/符号链接被拒。缺失时用默认插画，不影响激活。
- 清单需导出 `./package.json` 供回退读取；`./locale/*.json` 按需导出。字段缺失允许回退，JSON 损坏或字段无效时显示单条诊断。

### 2.5 Config 与 volatile 用户数据

**【官方】** Host 插件可暴露一个 `Config`（schemastery schema）；`apply(ctx, config)` 在 Host 侧先解析 schema 默认值 → profile patch（用户层），再交给插件。用户可改字段用 `.volatile()` 声明，设置页读写这些字段，Host 校验后写回 profile `cordis.patch.yml`；浏览器半侧通过 `configForms.get('<entry-id>')` 读同一解析值。凭据类字段用 `role('secret')` 阻止进入表单响应。

---

## 3. 装载链路（从启动到卡片可见，逐层对应排查点）

### 3.1 Host 侧装配

**【官方 + 本机实证】**

1. Desktop Host 以 `$DSH_HOME/profiles/desktop` 初始化 profile：读 `package.json` 的 `dsh.profile.bundles`。
2. app-boot 逐个解析 bundle 目录 → 读 `dsh.bundle.patch` → 读 `dsh` 元数据 → 把 patch 组成 layer；未列入 bundles 的依赖只是普通 npm 包，自带 patch 不进 host loader；读取/兼容失败记入 `skippedBundles`。
3. 叠加 profile `cordis.patch.yml`（user layer，最后）；按 id 覆盖 config、`disabled`、`insert`。
4. Loader 为每个启用 entry 创建 fiber；Cordis 读取插件对象上的 `inject`，等待对应服务就绪后执行 `apply(ctx, config)`；`ctx.effect()` 内注册工具/提示词/监听器，返回 disposer。
5. 兼容性预检：`engines.dsh` / dsh peer 不满足且未豁免 → 拒绝加载（`incompatible-version`）。

**【本机实证关键源码位置（解包 `E:\DSH\resources\app.asar`，`@deepseek-ai/dsh-app-boot/lib/index.js`）】**
- profile bundles 读取与 layer 组成：1016 行 `bundles = manifest.dsh.profile.bundles ?? []`；1020–1034 行逐 bundle 解析目录/读 patch 组 layer；1035–1039 行失败进 `skippedBundles`；1042 行叠加 user patch。
- 层序注释：491–497 行。
- 兼容检查：311–326 `evaluatePluginCompatibility`；279–298 `unmetRequirements`（只认 `engines.dsh`、`@deepseek-ai/dsh*` peer）。

### 3.2 Client 半侧发现与下发

**【官方】** `dsh-client-modules` 把包的 `dsh.client` 声明变成可加载浏览器 bundle：
- Host 半侧扫描**已启用的 Loader 条目**，找出声明了 `dsh.client` 的包；`entry.fiber === void 0 || entry.disabled` 即跳过，不扫描 client half。
- 宿主把每份声明变成 `/plugins` 下的 bundle；Web 载体通过 `/plugins` 提供每个 bundle，shell 持有的载体通过 `fetchBundle()` 分派相同响应；浏览器按需惰性加载。
- bundle 是**惰性 CJS factory**：application combo 脚本启动时只注册一次 factory，模块主体副作用（含 CSS）在首次 import/物化时才运行。
- 图携带 Host `release` 身份（版本 + client 构建固化的源码 commit）；两字段相等才应用图与 rebuilt 帧；Host release 不一致期间不应用对方模块。
- **构建要求**：Host 提供的是已构建客户端 bundle，启动前必须已产出 `lib/client.js`；缺失 bundle 明确导致激活失败并给出包/路径列表。

**【本机实证（`@deepseek-ai/dsh-client-modules/lib/index.js`）】** 855 行 `processOne`：fiber 空或 disabled 直接跳过；720–749 `resolveMeta`：`platform !== "web"` 静默返回 null，`exports["./client"]` 缺失抛错。

### 3.3 浏览器物化与 fiber 激活

**【官方】** 浏览器 `window.__ModuleLoader__` 持有 queue facade；bootstrap combo 脚本注册各包 factory，宿主向 `<head>` 注入启动图。`factory(require) → 导出` 在 `loadCache` 记忆化；依赖未物化模块时递归物化，require 循环抛错。client fiber 同样按插件对象 `inject` 等待浏览器服务（slots、locale、configForms 等），就绪后执行浏览器 `apply(ctx)`，在 `ctx.effect()` 内 `slots.inject(...)`、`locale.register(...)` 注册 UI；卸载时按 disposer 撤销。

**【本机实证（`@deepseek-ai/dsh-cordis-client-runner`）】** client half 返回 undefined、声明的服务不可用都会被守卫拒绝并记入条目失败；`slots.onEntryError` 捕获渲染崩溃并记 failures，页面插件列表按条目报告同步失败，可单独重试而不改 Host 启用状态。

### 3.4 内置区 / 已安装区数据来源

**【本机实证（`@deepseek-ai/dsh-client-ui-plugin-manager`）】**
- 内置区（`plugins.item` 槽位 entries）：`ctx.slots.entries("plugins.item")`，由各 client 半侧在 `ctx.effect(() => ctx.slots.inject("plugins.item", () => ctx.slots.register(meta, Component)))` 注入。
- 已安装区：`renderSlot("plugins.item", { view: "summary" }, { only: item.id })`，每个条目用 summary 组件返回一句描述；Host 未激活/无 client 半侧时，这里只显示包名与 `package.json.description`。
- 因此"内置区出现中文卡"= Host entry 已启用 + client 半侧被发现 + `plugins.item` 注册成功；三者任一断链，卡片都不会出现。

---

## 4. 核心服务、事件与工具契约速查

### 4.1 Host 侧常用 ctx 键（官方 architecture 核心包表 + capability seam）

| 目标 | 机制 / ctx 键 | 说明 |
|------|---------------|------|
| 面向模型的工具 | `ctx.tools` | 作用域化工具注册表 + 带把关执行流水线；`ctx.tools.register(tool)`，schema 自动流入提示词组装 |
| 系统提示词片段 | `ctx.systemPrompt` | `section({ name, order, text, interpolate })` 注入分段；顺序号决定排列 |
| agent / 会话 | `ctx.agents`、`ctx.sessions`、`ctx.agentLoop` | 活跃 agent 注册表、追加式 `SessionEvent` 日志、默认驱动器 |
| 模型流式词汇 | `ctx.llm` | 消息与流式词汇、适配器 seam |
| 子进程 | `ctx.subprocess` | 见第 5 节 |
| 同源 HTTP 路由 | `ctx.connection.fetch.register` | 见第 5.4 节；浏览器 renderer 经 `/api/xxx` 同源访问 host，禁止直连后端端口 |
| 后台任务 | `ctx.jobs` | `start({ kind, label, owner, run })`；后台工具配套 `run_in_background` |
| 用户命令 | `ctx.commands` | 无需模型轮次即可分派 |
| 文件系统 / 沙箱 / 审批 | `ctx.fs`、`ctx.sandbox`、`ctx.approval` | seam 三角色（Definition/Provider/Consumer） |
| 配置表单 | `configForms`（经 `ctx.inject`） | 读取/写入 entry volatile 配置，Host 校验后落 profile patch |

### 4.2 事件域与分发模式

- **会话事件**：追加到日志并经 `session/event` 广播的持久事实（`system/message`、`user/message`、`assistant/message`、`tool/*`、`turn/start|end`、`step/start|end` 等），重载后仍在。
- **Agent 事件**（`agent/*`）：携带活跃 Agent，观察/拦截进行中工作。
- **能力事件**：向 `fs/*`、`tools/*`、`telemetry/*` 等 seam 附加策略与适配器。
- 分发模式：`emit`（观察，无返回）、`waterfall`（包装，有返回，必须 `next()`）、`parallel`（await，并行）、`serial`（await，按序）、`bail`（停在首个 bail 值）。
- 工具流水线钩子顺序：`tools/pre-execute`（策略决策：allow/deny/ask，waterfall）→ `tools/execute`（包裹分发：超时/重试/指标，可替换 `exec.signal`）→ `tools/post-execute`（替换展示或结果）→ `tools/result`（观测不可变权威结果，只读）。单调最终拒绝用 `ctx.tools.guard()`。

### 4.3 工具最小契约（官方 adding-a-tool，真源）

```ts
import type { Context } from '@deepseek-ai/cordis'
import { defineTool } from '@deepseek-ai/dsh-tools'

export const name = 'my-tool'
export const inject = ['tools']
export function apply(ctx: Context) {
  ctx.tools.register(defineTool({
    name: 'read_file',
    description: 'Read a file from disk.',          // 模型可见
    parameters: {
      path: { type: 'string', required: true, description: 'Absolute path' },
      limit: { type: 'number' },                     // 缺省即可选
    },
    output: {
      schema: { type: 'string' },
      render: (_args, value) => [{ type: 'text', text: value }],
    },
    async execute(args, exec) {
      return readFile(args.path, { encoding: 'utf8', signal: exec.signal })
    },
  }))
}
```

硬性约定：
- `defineTool` 在 `execute` 前按 schema 校验参数；schema DSL 表达不了的约束（非空、正数、跨字段）在 `execute` 内自查。直接注册原始 JSON Schema 的工具自行负责校验。
- `execute` 返回 `output.schema` 声明的规范 JSON 值；不要返回内容块，也不要让调用方从自然语言解析 id/字段；基础设施故障抛异常（注册表收敛为 `isError`），成功的不理想领域结果写入规范值并由 renderer 解释。
- 必须遵守 `exec.signal`；`exec` 携带不可变身份（token、callId、name、arguments、agent、signal、可选 parent），args 视为只读。
- 长时间工作：配 `run_in_background`，用 `ctx.jobs.start()`，取消走任务自有信号而非 `exec.signal`。
- UI 卡片由 `presentCall` / `presentResult` / `presentationMeta` 另算，纯函数、不做 I/O；**内置 Web Client 不消费 `presentCall`/`presentResult`**，要专用 Web 卡片需在 client 侧 `tool.call.toolview` 槽位按 wire 工具名注册组件。
- 注册借用只读定义，注册后不要改 schema 或替换回调；热替换需 dispose 对应 effect 后重注册。

#### 4.3.1 新版 register 校验实测契约（R14 从解包源码实证，2026-10-21）

`@deepseek-ai/dsh-tools` 的 `tools.register(definition)` 在注册前做硬性校验（源码 `lib/types/index.js:471–481`、`lib/index.js:2977–2982`），任一项不满足都会让整个插件 entry 在该工具处中断、报错 `tool "<name>" must declare output { schema, render, presentationMeta? }`：

- `output` 必须是**对象**；缺了整个 `output` 字段直接被拒。
- `output.render` 必须是**函数**；`output.presentationMeta` 若存在也必须是函数（不存在则允许）。
- `output.schema` 必须通过 `assertSupportedJsonSchema` 校验；执行期返回值还会再按 schema 做一次结构校验，违规抛 `ToolOutputError`。
- `timeoutMs` 若存在必须为正有限数；工具名 `run_code` 保留。

schema 子集（`lib/types/json-schema.js`）实测允许：
- 标量 `type` 仅 `object / array / string / number / integer / boolean / null`，**没有 `type: "json"`**；
- 空对象 `schema: {}` 是 annotation-only，等于"任意可无损 JSON"，用于不约束输出的工具；
- 允许关键字：`type / oneOf / properties / required / additionalProperties / items / enum / const` 加注释类 `description / title / default / examples`；`type` 与 `oneOf` 不能并存。

render / presentationMeta 契约（`lib/index.js:3637–3667` 执行期）：
- `render(args, value)` 返回的内容要经过 snapshot 投影、可无损 JSON 序列化；标准文本块形态 `[{ type: "text", text: JSON.stringify(value) }]`。
- `presentationMeta(args, value)` 可选，返回独立投影；两者都必须是纯函数、不做 I/O。
- **勘误（R16 复核后纠正，勿再沿用旧判断）**：`parameters` 与 `output.schema` 虽是两套规范，但 `parameters` 发给模型网关时**必须是 object-root JSON Schema** `{type:"object", properties, required?}`；扁平参数表顶层无 `type` 会被网关判成 `type: null` 拒绝（详见 4.3.2）。官方 `defineTool` 内部先把扁平 spec 编译成 object root；自研工厂若绕过官方 `defineTool`，必须自己复刻这层编译，不能把扁平表原样透传。

最小兜底写法（工厂层统一处理，避免每个工具重复；R16 起 parameters 经编译函数转 object root）：

```js
const defaultRenderJson = (_args, value) => [{ type: "text", text: JSON.stringify(value) }];

// 把官方扁平参数 spec 编译成模型网关要求的 object-root schema
function compileParameterSchema(spec) {
  const properties = {};
  const required = [];
  for (const [key, node] of Object.entries(spec ?? {})) {
    const compiled = compileValueNode(node);
    properties[key] = compiled;
    if (node?.required === true) required.push(key);
  }
  const out = { type: "object", properties };
  if (required.length) out.required = required;
  return out;
}

function defineTool(options) {
  return {
    name: options.name,
    description: options.description,
    parameters: compileParameterSchema(options.parameters),
    timeoutMs: options.timeoutMs,
    output: {
      schema: compileOutputSchema(options.output?.schema),
      render: typeof options.output?.render === "function" ? options.output.render : defaultRenderJson,
      ...(typeof options.output?.presentationMeta === "function"
        ? { presentationMeta: options.output.presentationMeta } : {}),
    },
    execute: options.execute,
  };
}
```

#### 4.3.2 `parameters` 必须编译为 object-root（R16 从模型网关报错实证，2026-10-22）

- **现象**：插件启动无报错、状态卡正常、output 契约离线 18/18 PASS，但新对话里模型工具层报 `Invalid schema for function 'create_postprocess_task': schema must be a JSON Schema of 'type: "object"', got 'type: null'`；报错只点第一个被遍历到的工具，实际全部工具同构。
- **机制**：OpenAI/DeepSeek function calling 规范要求 `parameters` 顶层为标准根对象 `{type:"object", properties:{...}, required:[...]}`；作者侧扁平表 `{ kind: {type:"string", required:true}, ... }` 顶层没有 `type`，网关读 `parameters.type` 得 undefined，按 null 拒绝。官方 `defineTool`（`dsh-tools/lib/types/schema.js:238–247` `parameterSchemaSpecToJsonSchema`、`:274–304` 注册入口）在注册前先完成这层编译；自研工厂直接透传扁平表就绕过了它。
- **两套 schema 边界**：`parameters`（入参，发给模型，强制 object root）；`output.schema`（出参契约，DSH 内部 `assertSupportedJsonSchema` 校验，允许 annotation-only 空 `{}` 任意 JSON）。两者不要混为一谈。
- **离线先验**：契约脚本除 output 子集白名单外，必须硬断言每个工具 `parameters.type === "object"`、`properties` 为对象、`required` 为字符串数组且键全部命中 properties、子节点递归过子集白名单；再用诊断脚本实跑 `apply(ctx)` 收集工具，打印 `parameters.type`、properties 键数、required 与一个完整样本人工核对。旧脚本只校验 output.schema 是 R16 暴露的校验盲区。
- **不引运行时依赖**：第三方插件 `build.mjs` 通常把 `@deepseek-ai/*` 列为 external，运行时不保证解析该作用域包；像官方范本 aifs 一样在插件内联复刻官方编译函数的最小子集，而不是运行时 import。

离线先验：重启 DSH 前可 mock `ctx.tools.register` 走真实 `plugin.apply(ctx)` 收集工具，复用 dsh-tools 自带 `assertSupportedJsonSchema` 逐个复核 output 对象/render/presentationMeta/schema，并按 4.3.2 复核 parameters object-root；实跑一次默认 render 确认可序列化；不要靠反复重启 DSH 碰运气。

### 4.4 浏览器侧常用服务与槽位

**【官方】**
- `locale`：`locale.register(ns, { zh, en })`、`locale.bind(ns)` 得到 `t(key)`；插件标题/描述/卡片文本走同一语言链。
- `slots`：`slots.inject(slotName, () => slots.register(meta, Component))`；`meta` 含 `name`、`id`、`order`、`label`、`locale`、`inject`。
- `configForms`：`get('<entry-id>')` 读表单状态 `{ getSnapshot(), value, status, subscribe, set, unset, mutate(ops, expectedRevision) }`。
- 已知槽位：`plugins.item`（内置插件状态卡行）、`plugins.detail.actions`（页头控件）、`plugins.detail.badge`（标题旁标签）、`plugins.detail.section`（详情页底部区块）、`settings.section`（设置页分区）、`conversation.chat.node`（聊天业务节点）、`tool.call.toolview`（专用工具卡片）。组件按 `subject` 匹配，不属于自己的 subject 返回 `null`。

---

## 5. subprocess 托管外部后端契约（managed 模式真源）

**【官方 subprocess.zh.md】** 子进程 seam 分 Service Definition（`dsh-subprocess`，`ctx.subprocess`）与 Provider（`dsh-subprocess-local`）；其他后端、LSP、PTY、ACP 都是 Consumer。

### 5.1 spawn spec 完全显式，框架不补默认值

```ts
interface SubprocessSpawnSpec {
  argv: readonly string[]   // argv[0] 是程序，绝不经过 shell 解释
  cwd: string               // 工作目录，必须是合法字符串
  stdio: {
    stdin: 'ignore' | 'pipe' | { data: string }
    stdout: 'pipe' | 'inherit' | SubprocessCollect
    stderr: 'pipe' | 'inherit' | SubprocessCollect
    control?: 'pipe'
  }
  graceMs: number           // 有限毫秒宽限，给分阶段终止排空收集管道
  signal?: AbortSignal
  env?: NodeJS.ProcessEnv
}
```

- `stdout/stderr`：`pipe`=原始管道供协议分帧；`inherit`=直通父描述符（诊断落到 harness 自身流）；`SubprocessCollect`=有界内存收集 + 可选 spill 文件。
- `DSH_*` 是归 Harness 所有的子进程事实；合并显式 `env` 前先丢弃环境中已有的 `DSH_*`；显式 `undefined` 作为 tombstone 删除普通环境中的同名值。
- `resolveExecutable`：绝对路径校验存在；裸名称走清理后 PATH 加有意覆盖；含分隔符的相对路径直接拒绝（fail loud，不猜解析基）。

### 5.2 句柄与退出判定（owned/reuse/orphan 的依据）

```ts
interface SubprocessHandle {
  readonly done: Promise<SubprocessOutcome>   // 只带 exitCode/signal，不带原因分类
  terminate(): void                           // 启动 provider 记录的分级终止；幂等
  waitForExit(signal?): Promise<boolean>       // true=受管范围已空；false=信号先中止；抛错=provider 无法再观察
}
```

- `done` 是 Node close 事件词汇，**不携带超时/取消分类、不携带输出**；收集流在结算后仍可经 `handle.collected.readFrom(0)` 读取。
- **受控关闭阶梯**：先发送应用层 HTTP shutdown → `terminate()` → `waitForExit()`；只有 `waitForExit() === true` 才确认受管范围清空、可清 ownership。不能把"Promise/句柄存在"当成退出事实；未确认退出时保留 handle、保持 owned、标 orphan，不伪造 stopped。
- 服务 teardown 会终止所有仍在运行的受管进程并等待退出；Provider 文档应说明分阶段还是立即终止及其可观察性限制。

### 5.3 第三方托管后端的通用生命周期（本插件实践对齐官方语义）

1. **probe**：先对已知 `baseUrl` 探活；探活成功 = 已有外部后端 → reuse，`owned=false`，dispose 时不得关闭它。
2. **managed spawn**：无活后端时按 spec 显式 argv/cwd/stdio/env 拉起；轮询 health 直到 ready；记录 handle 与 `owned=true`。
3. **dispose**：先受控应用层 shutdown，再 `terminate()`，`waitForExit()===true` 才清 ownership；reuse 路径完全不碰外部进程。
4. **并发竞态**：`_waitReady` 期间被 dispose，直接走受控 stop 分支，不留下 `owned=true + handle=null` 的不一致终态；不主动杀业务子进程树（如后台正在跑的计算任务），留给后续 reconcile 接管。

### 5.4 connection 同源代理：状态卡为什么不能在浏览器直连后端（R15 实证）

**结论先行**：插件状态卡需要展示后端状态时，**浏览器 renderer 不直接 `fetch("http://127.0.0.1:<port>/...")`**；正确做法是 host 经 `connection` 服务注册 `/api/<ns>/*` 同源路由，renderer 用相对路径 `/api/<ns>/status` 访问，host Node 侧再去连自己托管的后端。

**官方契约（解包 `@deepseek-ai/dsh-client-connection` 实证）**：
- `HostConnectionService extends Service`，服务名 `"connection"`；`this.fetch = { register: (route) => this.registerFetchRoute(owner, route) }`。
- 路由字段：`path`（必须以 `/api` 开头）、`methods`（`GET`/`POST`…，非空且不重复）、`requestBody`（`"buffered"`）、`fetch: async (request) => Response.json(...)`。
- 分发按 `url.pathname` 精确匹配、`route.methods.has(method)` 后调用 `route.fetch(request)` 返回 `Response`；host 在 webServer 注册 `/api` 总路由与 `/connect`，renderer 相对路径 `/api/xxx` 走同源分发，**没有跨域、不需要 CORS 头**。
- `registerFetchRoute` 返回 `owner.effect(...)` 的注销函数；disposer 里依次调用注销，避免重复注册（重复 path 会抛 `exact Fetch route ... already registered`）。
- 顶层 `inject` 列表不必列 `connection`；在 `apply(ctx)` 内子 `ctx.inject(["connection"], child => child.effect(() => { const dispose = child.connection.fetch.register({...}); return dispose; }))` 即可，与 `subprocess` 的子注入方式一致（范本 aifs 即此写法）。

**host 侧典型形态（本插件 R15 落地）**：
```js
apply(ctx) {
  let subprocessService = null;
  ctx.inject(["subprocess"], (child) => {
    subprocessService = child.subprocess;
    void manager.start(subprocessService);
  });
  ctx.inject(["connection"], (child) => {
    const disposeStatus = child.connection.fetch.register({
      path: "/api/gaussian/status", methods: ["GET"],
      fetch: async () => Response.json(await manager.snapshot()),
    });
    const disposeRetry = child.connection.fetch.register({
      path: "/api/gaussian/retry", methods: ["POST"],
      fetch: async () => { if (subprocessService) await manager.start(subprocessService); return Response.json(await manager.snapshot()); },
    });
    return async () => { await disposeStatus(); await disposeRetry(); };
  });
}
```
- `manager.snapshot()` 返回 host 视角状态：`{ state, version, mode, owned, ready, baseUrl, dataDir, error, backend }`；仅 `state === "ready"` 才在 host Node 内去拉后端 `/v1/status` 摘要放进 `backend`，失败置 `null`。这样卡片拿到的是 host 真实 state/error/owned/orphan，而不是浏览器猜测。
- retry 路由在 host 内触发幂等 `manager.start(subprocessService)`，等价于范本 aifs 的「重试启动」按钮在 host 侧调 `runtime.start()`。

**实机验证边界（2026-10-22 重启 DSH 记录）**：上述同源链路在真实 DSH 内验证通过——卡片「可用」、版本、后端地址、数据目录、Gaussian 路径/可用、工作目录、默认内存/核数、Sobko 状态、运行中任务均由 host snapshot + 后端摘要渲染。external reuse、controlled dispose、orphan/dispose race、对话内工具注册可见性不在本次启动态观察范围内，仍属待实机确认项；证据分层纪律见 `LESSONS_LEARNED.md` 第 35 条与通用技能 `dsh-plugin-toolkit` 4.5 节、K12。

**为什么不能 renderer 直连后端**：
1. 后端未拉起时直接 `fetch(127.0.0.1:8765/...)` 立即 `TypeError: Failed to fetch`，卡片拿不到 host 归类的失败原因（无 subprocess / exe 定位 null / spawn 崩溃 / waitReady 超时）。
2. renderer origin 为 `dsh-app://app`，不在后端 CORS 回环正则内，即使后端在线也会被浏览器跨域拦截。
3. 卡片无法触发 host 侧 retry/spawn，也拿不到 owned/orphan 等 host 生命周期事实。

**包内 exe 自定位（不依赖环境变量）**：环境变量 `GAUSSIAN_BACKEND_EXE` 存在且文件存在才优先用；否则用 `fileURLToPath(new URL("../runtimes/", import.meta.url))` 解析包内 `runtimes/<platform>-<arch>/runtime.json`，校验 `target/version`、executable 自身 sha256，拒绝绝对路径与 `..` 越界；`runtime.json` 可能带 UTF-8 BOM，Node 解析前必须 `.replace(/^\uFEFF/,"")` 剥离，否则 `JSON.parse` 抛 BOM 语法错误、被 catch 吞成 null。

---

## 6. Profile 与插件管理器：开关、bundles、兼容豁免、重启语义

### 6.1 两类开关写在不同文件（最容易混淆）

**【官方 plugin-manager】**
- **组合包开关（bundle 级，决定加载不加载）**：写 profile `package.json` 的 `dsh.profile.bundles` 有序列表；关闭=从列表移除，开启=追加到列表末尾（可能改变层优先级）。关闭保留依赖；安装新组合包默认启用。
- **单条目开关（entry 级，包已加载但关闭某一行）**：只更新 profile `cordis.patch.yml` 中最后一条匹配 id 覆盖项的 `disabled`；无匹配则追加；若 bundle 层与其余 patch 已使条目处于请求状态，仅含 `id`+`disabled` 的覆盖项会被移除，profile patch 只记录与组合包不同的设置。匹配依据是 entry id 与覆盖项声明的模块名；比较不计 home 与单次启动 patch。

### 6.2 安装 spec 与本地目录插件

- 命令：`dsh plugin --profile <name> add <spec>`；spec 可以是 npm 包名/版本、`github:owner/repo`、绝对路径、本地 tgz；`file:`/`link:` 路径相对 profile 目录解析为绝对路径，`~` 展开为主目录。
- `inspect(spec)` 在安装前读出名称、版本、描述、是否声明 bundle、registry 或问题码（`invalid-spec`/`already-installed`/`not-found`/`not-a-package`/`not-a-bundle`/`network`/`unknown`）。
- 本机 `file:E:/YDW/...` 即本地目录/压缩包安装；pnpm 会把包装入 `node_modules` 快照（**本机实测为复制快照，不是软链**：改源码目录后必须覆盖快照 `lib/`，DSH 才读新版）。
- 未声明 bundle patch 的 profile 依赖在管理页可见、可删，但**不能启用**（`not-a-bundle`）。

### 6.3 兼容性检查与豁免

- 安装 `add`（含带 spec 的 install）在 pnpm 前先做版本检查：本地路径直接读 `package.json`，registry spec 经 `pnpm view`；不满足的 DSH 要求会在下载/构建脚本前拒绝。git/tarball 必须先抓取，安装后才判定，失败时恢复清单与锁文件并重装。
- 豁免保存在 profile `compatibility.json`（与 `package.json`、`cordis.patch.yml` 并列）：精确 `package-name@version` → 精确 DSH 运行时版本列表；写豁免不改依赖、bundle 选择或 patch 层；插件升级、DSH 升级都不继承授权。CLI：`dsh plugin --profile <p> version-exemptions`、`allow-version <pkg@ver> --dsh-version <runtime> --accept-risk`、`revoke-version <pkg@ver> --dsh-version <runtime>`。
- 错误码 `incompatible-version`，携带 name/version/runtimeVersion/未满足 requirements（键为 `engines.dsh` 或 dsh peer 包名）。

### 6.4 HMR 与重启

- profile 启用 HMR 时，配置变化立即生效；未启用 HMR 时，运行中的组合保留到重启。
- 没有 HMR：安装新包、启用 bundle、删除成功后发布 profile runtime resolution；被取消选入的启动组合包仍在运行时，后续操作保留整张当前表并报告 `restart-required`。
- 有 HMR：安装要求 spec 已是已安装包，否则先卸载再安装；运行 pnpm 之后才能确定包名的 git/tarball 在无 HMR 时报 `restart-required`，有 HMR 则由重新组合替换已加载文件变化的运行中插件。
- 替换版本导入/启动失败：保留旧版本不再运行，每次操作再次导入它；文件/依赖修正后即启动；未变化的导入失败作为警告报告。
- `restart-required` 原因：`no-hmr`、`package-moved`，或只有重启后才能加载的已变化模块的 HMR 待处理原因。

### 6.5 失败回滚与诊断

- 安装：pnpm 执行或 bundle 校验失败 → 恢复 pnpm 运行前快照的 `package.json` 与 `pnpm-lock.yaml`；已下载文件可能残留，报告安装失败。
- 启用：保存选择或加载失败 → 保留已安装依赖与已保存选择，报告启用失败，允许修正/停用/卸载。
- 包操作成功后解析表发布失败 → 保留磁盘改动与上一张运行时表，报告 `application: 'failed'` 及发布诊断；**pnpm 零退出码不代表发布成功**。
- 卸载：先从 bundles 移除 → 卸载运行时贡献 → `pnpm remove` → 发布 runtime resolution；任一步失败不继续后续步骤。
- 诊断日志：profile `.plugin-manager/logs/<operation-id>/pnpm.log`；每个操作记录 `.plugin-manager/run.json`，结束即删；持有进程退出的锁由下一个写入方接管，发现记录后最多等 5 秒让记录中的 pnpm 进程停止。

### 6.6 本机固定路径（Desktop profile）

| 用途 | 路径 |
|------|------|
| profile 根 | `C:\Users\Administrator\.dsh\profiles\desktop\` |
| profile 包清单 | `profiles\desktop\package.json`（dependencies + dsh.profile.bundles） |
| 用户 patch 层 | `profiles\desktop\cordis.patch.yml`（写配置覆盖 / entry disabled） |
| 根条目列表（勿手改） | `profiles\desktop\cordis.yml`（恒 `[]`） |
| 包快照 | `profiles\desktop\node_modules\<pkg>\`（复制快照，改完源码要覆盖） |
| 锁文件 / workspace | `pnpm-lock.yaml`、`pnpm-workspace.yaml`（pnpm 维护） |
| 插件管理日志 | `profiles\desktop\.plugin-manager\logs\` |
| Desktop 崩溃日志 | `C:\Users\Administrator\AppData\Roaming\@deepseek-ai\dsh-desktop\logs\crash-*-host.log`、`crash-*-web-boot.log` |
| DSH 程序资源 | `E:\DSH\resources\app.asar`（内置 Cordis、boot、client-modules、plugin-manager、subprocess 等全部子系统） |

### 6.7 profile 隔离与 disabled 写入路径（R17 解包实证，2026-10-22）

- **profile 之间完全隔离**：每个 profile 目录独立持有 `package.json`（dependencies + `dsh.profile.bundles`）与 `cordis.patch.yml`；DSH 按启动时指定的 profile 只加载该 profile bundles 内的包，配置、`node_modules` 快照、patch 互不影响。`desktop`/`web`/`acp`/`headless` 是并列实例；排查故障先读故障会话对应 profile 的三份文件，再判断故障是否由已安装插件引起——空依赖 profile 里出现的问题不可能由另一个 profile 的插件造成。
- **`disabled: true` 的唯一写入入口是 UI 单条目开关**：`setPluginEnabled(id, enabled)` → `writePluginEnabled(profile, id, name, enabled)`（解包 `@deepseek-ai/dsh-plugin-manager` 实证）。插件 entry 激活失败只产生黄条或写 crash 日志，框架**不存在**"激活失败自动回写 disabled"的代码路径；手动关闭后的状态持久化到 patch，下次启动沿用。
- **bundle 选择是与 disabled 并列的第二个独立开关**：`selectBundle(name, enabled)`（`plugin-manager/lib/index.js:2280–2305`）写 `package.json` 的 `dsh.profile.bundles` 数组——`enabled=false` 时 `previous.filter(item => item !== name)` 摘除目标名并 `saveManifest` 原子回写，**不碰 `cordis.patch.yml`、不删 dependencies**。现场"dependencies 保留、bundles 缺目标包、patch 时间戳未变"即对应这条路径；崩溃恢复 `disableAllPlugins() → sanitizeProfile`（`lib/main.js:3531–3546、3585–3587`）则会先把 patch 改名备份为 `.bak-<毫秒时间戳>` 再把 bundles 覆盖为 `WEB_PROFILE.bundles`，两条路径凭"patch 是否被改名备份"区分。`reconcile()` 只在 install/remove 后按 manifest 存在性过滤，`listBundles()` 兼容性不通过只在 UI 行标错、不回写 bundles 数组，启动期不存在自动摘除已声明 bundle 的路径。
- **安装命令必须带 `--profile <name>`**：不带 profile 参数的默认目标取决于启动命令；装错 profile 会在另一个 profile 会话里看不到插件，排查"插件没出现"先核对命令目标 profile 与当前会话 profile 是否一致。
- **一次性 shell 命令链路（0xC0000142 排查定位用）**：`dsh-tool-pwsh`（工具注册/参数/渲染）→ `ctx.shell.resolve/execute` → `dsh-pwsh-local`（解析 pwsh 路径、拼 argv、组 spawnSpec）→ `dsh-subprocess-local`（Windows 先拉起独立 Node runner bootstrap，runner 内经 `dsh-win32-process` koffi `CreateProcessW` 挂起创建 → AssignProcessToJobObject → ResumeThread 拉起目标 `powershell.exe`）。退出码由 runner 透传；`3221225794`（0xC0000142 = STATUS_DLL_INIT_FAILED）无法仅凭退出码区分失败在 runner bootstrap 自身还是目标进程，需分层抓证据，详见 `docs/R17_DIAGNOSIS_20261022.md` 第 3 节。本机前置复测（2026-10-22 晚）：未装 PowerShell 7 属预期，执行器按设计回退 System32 WindowsPowerShell 5.1；系统 `powershell.exe` 5.1（10.0.19041.1）与 `cmd.exe` 绝对路径独立启动 `echo hello` 均 exitCode=0，系统 shell 本体健康已排除；`pwsh` 在普通终端报 CommandNotFound 不是损坏证据。
- **会话级权限档位独立于 profile bundles**：`read-only` / `workspace-write` / `danger-full-access` 由会话选择器决定，走 `@deepseek-ai/dsh-sandbox-windows-acl` 的受限令牌路径与否。官方包 README 载明：受限令牌下 `CREATE_NO_WINDOW` / `CREATE_NEW_CONSOLE` 创建的子进程在 DLL 初始化阶段死亡即报 0xC0000142；这是 Windows 上该错误码的首要已知主因，排查先核对档位，`danger-full-access` 不套沙箱。profile bundles 里没装第三方插件 ≠ 当前会话不是受限档位。

---

## 7. 本机实测坑位索引（与 FIX_REPORT 编号对应）

> 下列为 gaussian 插件在本机真实踩到并已修掉的问题；新增插件按此清单逐项自查，避免重复踩坑。

| 编号 | 现象 | 根因 | 正确做法 |
|------|------|------|----------|
| R12a | Host 激活报 `cannot get property "tools" without inject` | 只在模块里 `export const inject`；Cordis loader 取 `module.default` 作为插件对象，从该对象读 `inject`，named export 被忽略 | `export default { name, inject, apply }`，inject 必须进 default 对象；named export 可保留但不能只靠它 |
| R12b | web boot 崩 `duplicate factory registration` | 后端 `name="gaussian-dsh"` 与 client.js 模块 id 同名，重复注册 factory | client 模块 id 用完整包名 `@gaussian/dsh-plugin-gaussian`，与 host 内部服务名区分开 |
| R13a | 开关已开但内置区不出现中文状态卡，仅"已安装插件"显示包名+英文 description | 包只在 `dependencies`，未列入 `dsh.profile.bundles`；自带 `cordis.patch.yml` 没进 host loader → 无 Host entry → client-modules 扫不到 client half | 把包名追加进 profile `package.json` 的 `dsh.profile.bundles`；安装第三方插件后核对这一份清单 |
| R13b | 补进 bundles 后 entry 仍被关 | profile `cordis.patch.yml` 残留 `- id: gaussian / disabled: true`，user layer 最后叠加把条目关掉 | 删除残留 disabled 段；插件交付/排障时先查这份 patch |
| R14 | 卡片已进内置区，但黄条 `tool "<name>" must declare output { schema, render, presentationMeta? }`，第一个工具中断、整 entry 工具全部未注册 | 工具对象缺新版强制要求的 `output` 对象，render 必须为函数，schema 要落在受支持子集 | 在 `defineTool` 工厂层统一兜底 `output = { schema: {}, render: defaultRenderJson, ...presentationMeta? }`；详见 4.3.1；离线契约自测逐个工具复核 |
| R14c | 工具已注册成功、无报错，但模型从不主动调用某几个工具 | 系统提示 `section` 手写的工具清单漏列这些工具；注册与提示词是两条独立链路，漏写不阻断加载 | 把注册名集合与提示词文本工具名集合做差集，补全漏列；新增/改名工具时同步更新提示词（本插件漏列 4 个后处理工具） |
| R15 | 卡片标题/描述已渲染，状态区 `TypeError: Failed to fetch`、一直「正在读取服务状态…」 | renderer 直连后端 127.0.0.1:port，host 未注册同源路由；后端未拉起或 `dsh-app://app` 不在 CORS 内；卡片拿不到 host state/error | host `ctx.inject(["connection"])` 注册 `/api/<ns>/status`、`/api/<ns>/retry` 同源路由，renderer 只走相对路径；详见 5.4；另注意 `runtime.json` BOM 会让 Node `JSON.parse` 失败、包内 exe 自定位被吞成 null |
| R16（技能 K13） | 启动无黄条、卡片正常，新对话模型层报 `Invalid schema for function '<name>': schema must be a JSON Schema of 'type: "object"', got 'type: null'` | 自研 `defineTool` 把扁平参数表直接透传，`parameters` 顶层缺 `type:"object"`；模型网关读顶层 type 得 undefined 按 null 拒绝；旧离线契约只校验 output.schema、漏检 parameters 结构 | 工厂复刻官方 `parameterSchemaSpecToJsonSchema`，产出 `{type:"object", properties, required?}`；离线契约硬断言 parameters object-root 并递归子集白名单；详见 4.3.2，通用技能 `dsh-plugin-toolkit` 坑位 K13 |
| R17（技能 K14） | 空依赖 profile 的 shell 命令全部退出 `3221225794`（0xC0000142），模型与文件工具仍可用；或插件被 `disabled:true` 后被误判为"插件代码把 DSH 搞坏" | profile 隔离未先核对；0xC0000142 在 Windows 首要已知主因是会话级 read-only/workspace-write 受限令牌（受限令牌 + CREATE_NO_WINDOW/无控制台致 DLL 初始化失败），属内置 shell/sandbox/runner 层；disabled 由 UI 开关写入、框架不自动禁用 | 先读故障 profile 的 dependencies/bundles/patch 定归属；0xC0000142 第一步核对会话权限档位，再按 6.7 分层排除、未复现候选标待实机；disabled 先查 UI 开关/持久化回写；内置子系统问题不进插件修复边界，详见 6.7 与 `docs/R17_DIAGNOSIS_20261022.md` |
| R17c（技能 K15） | 重启后插件不加载：dependencies 三项全保留、bundles 只剩官方 base/web-app，`cordis.patch.yml` 时间戳未变、无 disabled 残留 | bundle 选择开关 `selectBundle(false)`（`plugin-manager/lib/index.js:2280–2305`）只从 bundles 数组过滤目标名并回写，不碰 patch、不删 dependencies；与 disabled 开关是两条独立路径。`reconcile()` manifest 存在性过滤、`listBundles()` 兼容性展示均不会自动回写 bundles | 先按"patch 是否被改名 `.bak-<毫秒>`"区分 `selectBundle(false)` 与崩溃恢复 `disableAllPlugins()`；备份摘除后 `package.json.bak-<日期>-rNN` → bundles 补回目标包 → JSON 双侧断言 + toolkit manifest 离线校验 → 完全退出重启并复查 bundles 是否再次被摘；详见架构 6.7 与诊断 4.5 |
| 快照坑 | 改了源码目录，DSH 行为不变 | pnpm 把包复制进 `node_modules` 快照（非软链） | 改完 `lib/` 必须同步覆盖快照 `lib/index.js`、`lib/client.js`，并 `node --check`；源码改动后先跑构建产物再覆盖 |
| 构建坑 | client 半侧缺失 bundle 导致激活失败 | 未先产出 `lib/client.js` 就启动 | 第三方本地包作者自己复刻构建（esbuild/tsdown clientBundle preset），启动前确认 `lib/index.js`、`lib/client.js` 在位 |
| 后端后端契坑 | managed 模式拉起失败/状态假报 | spawn spec 不完整、cwd 非字符串、退出只看 Promise 存在性 | 见第 5 节：argv 不经 shell、cwd 必填字符串、stdio 显式、`waitForExit()===true` 才清 owned、未确认退出保留 handle 标 orphan |
| GJF 边界（业务侧示例） | Gaussian `End of file in ZSymb` | 写盘时吞掉坐标块后空行 | 写盘前 `content.rstrip("\n") + "\n\n"`；属于业务插件自身校验，不影响 DSH 装载契约 |

---

## 8. 排障决策树（按报错现象定位层）

### 8.1 启动即崩溃 / 弹窗 "web boot: 1 entry did not activate"

1. 读最新 `crash-*-web-boot.log`：找插件包名与错误类名。
2. `import failed` / `duplicate factory registration`：看 client 模块 id 是否重复、`exports["./client"]` 是否可解析；对照 R12b。
3. `cannot get property "tools" without inject`：Host 插件对象缺 `inject`；按 R12a 检查 default 对象。
3b. `tool "<name>" must declare output { schema, render, presentationMeta? }`：工具缺 output 对象/render 函数/合法 schema；按 R14 与 4.3.1 检查工厂兜底。
4. `Failed to load plugins` 且 client entry `pending (waiting for service: <svc>)`：client `dsh.client.inject` 列的基座服务包名不存在或版本不匹配；核对官方 client 包名清单。
5. 崩溃在 host 侧（`crash-*-host.log`）：Host `apply(ctx)` 抛错、`inject` 服务未注册、Config schema 校验失败；打开快照 `lib/index.js` 与 traceback 定位。

### 8.2 插件在"已安装插件"可见，但内置区没有卡片

按第 3.4 节三段链路逐段查：
1. **bundles**：profile `package.json` 的 `dsh.profile.bundles` 是否含本包名（R13a）。
2. **disabled**：profile `cordis.patch.yml` 是否残留本包 id 的 `disabled: true`（R13b）。
3. **manifest**：`exports["./client"]` 存在、`dsh.client.platform === "web"`、`lib/client.js` 文件在位、内容是惰性 CJS factory（`window.__ModuleLoader__.load({ id, factory })`）。
4. **host entry 状态**：Host entry 未激活（fiber 空/disabled）时 client-modules 直接跳过；先确认 Host 侧工具/服务已注册。
5. **release 一致性**：Host release（版本 + commit）与页面启动图不一致时不应用模块；重启页面/Host 对齐构建产物。
6. **快照新鲜度**：`node_modules\<pkg>\lib\client.js` 是否为最新构建（R 快照坑）。

### 8.3 工具在对话中不可见（Host 工具未注册）

1. Host `inject` 是否含 `tools`；`ctx.tools.register(...)` 是否在 `ctx.effect()` 内、disposer 返回正确。
2. 工具名/schema 是否经 `defineTool` 或合法原始 JSON Schema；`parameters` 必填键标注。
2b. **对话内报 `Invalid schema for function '<name>': schema must be a JSON Schema of 'type: "object"', got 'type: null'`**：启动无黄条、卡片正常，问题在 `parameters` 顶层未编译成 object root（见 4.3.2）；离线契约必须同时校验 parameters 结构，不能只查 output.schema。
3. 新工具需新开一轮对话才会进入提示词组装（提示词/工具 schema 按轮次装配）。
4. `tools.restrict()` 或作用域 preset 是否把本工具排除；agent preset 条目只读。

### 8.4 managed 后端未拉起 / 状态假报成功

1. 后端 exe/路径：`resolveExecutable` 拒绝相对路径；绝对路径必须存在。
2. env：`DSH_*` 命名空间会被清理；业务自定义环境变量走 `env` 显式条目；`undefined` 会删除普通环境同名值。
3. 退出判定：只读 `waitForExit()===true`；`done` Promise resolve 不等于受管范围清空；reuse 的外部后端 `owned=false`，dispose 不关闭。
4. 后端自身 `/health` 返回的 service 名、version 要与插件期望一致，避免误认其他进程。

### 8.5 本机一键离线自检（新装/改动后先跑）

```powershell
# 1) Host 插件形状：default 对象必须带 name/inject/apply
node <plugin>\scripts\verify_plugin_shape.mjs
# 2) profile 装载链：bundles 含本包、user patch 无 disabled、bundle.patch/client.js/main 在位
node <plugin>\scripts\verify_profile_bundle.mjs
# 3) 语法
node --check <snapshot>\lib\index.js
node --check <snapshot>\lib\client.js
# 4) 清单可解析
node -e "JSON.parse(require('fs').readFileSync('<snapshot>\\package.json','utf8'))"
```

### 8.6 命令速查

| 操作 | 命令/位置 |
|------|-----------|
| 安装本地目录插件 | `dsh plugin --profile desktop add E:/path/to/plugin-dir`（等价手动写 dependencies + bundles + pnpm install） |
| 安装本地 tgz | `dsh plugin --profile desktop add ./pkg.tgz` |
| 列出 bundles 与条目 | `dsh plugin --profile desktop list`（管理页或 `plugin_manager` 工具） |
| 查看实际装配配置树 | `dsh --profile desktop --dump-config` |
| 版本豁免 | `dsh plugin --profile desktop allow-version <pkg@ver> --dsh-version <runtime> --accept-risk` |
| 只读 profile patch | 编辑 `profiles\desktop\cordis.patch.yml`；不要改 `cordis.yml` |
| 重启生效 | 未启用 HMR 时完全退出 DSH（托盘退出，进程结束）再打开；改动 bundles/disabled 后必须重启验证 |

---

## 9. 第三方插件上线检查清单（交付前逐项打勾）

### 9.1 清单与产物
- [ ] `package.json`：`type: module`、`main`、`exports["."]`、`exports["./client"]`、`exports["./package.json"]`、`dsh.bundle.patch`、`dsh.client.platform=web`、`dsh.client.inject` 齐全。
- [ ] `cordis.patch.yml`：`- insert: { id, name }`，id 稳定、name 为裸包名模块说明符。
- [ ] `lib/index.js`（Host）、`lib/client.js`（浏览器，惰性 CJS factory）已构建并在快照内为最新。
- [ ] 标题/描述：locale `meta.title/description` 或 `package.json.name/description` 回退成立；图标按清单规范放置。
- [ ] 未声明 `engines.dsh`/dsh peer 时确认不需要版本门槛；需要时写范围或准备豁免。

### 9.2 Host 半侧
- [ ] `export default { name, inject, apply }`，inject 列出的服务都存在于 Host。
- [ ] 工具注册在 `ctx.effect()` 内，返回 disposer；`defineTool` schema 合法，`execute` 返回规范 JSON、遵守 `exec.signal`。
- [ ] 每个工具都带 `output { schema, render, presentationMeta? }`：output 为对象、render 为函数、schema 落在受支持子集（任意输出用 `{}`），render 返回可无损序列化投影；见 4.3.1。
- [ ] `parameters` 编译为 object-root：`{type:"object", properties, required?}`，仅 `required===true` 入 required 数组；扁平表直接透传会被模型网关判 `type: null` 拒绝；离线契约必须硬断言 parameters 结构，见 4.3.2。
- [ ] 提示词片段经 `ctx.systemPrompt.section`，带稳定 `name` 与 `order`；片段里手写的工具名清单必须与 `buildTools` 注册名一一对应（漏写不阻断加载，但模型不会主动调用该工具，见 R14c）。
- [ ] 外部后端按第 5 节 managed 契约：probe/reuse、显式 spawn spec、受控 shutdown → `waitForExit()===true`、orphan 保留 handle。

### 9.3 Client 半侧
- [ ] factory 内 `locale.register(ns, {zh,en})`、`slots.inject(...)` 都在 `ctx.effect()` 内。
- [ ] 组件纯函数渲染；`view==="summary"` 返回一句话描述；不属于自己的 subject 返回 `null`。
- [ ] 不 import Host 工具实现；浏览器侧只经 `ctx.remote`/`configForms`/RPC 取 Host 数据。
- [ ] 状态卡需要后端状态时，renderer 只 `fetch("/api/<ns>/status")` 同源路由，**不直连后端 `127.0.0.1:port`**；host 侧 `connection.fetch.register` 提供路由并透传 host snapshot（见 5.4）。

### 9.4 profile 与重启
- [ ] 本包名已进 `dsh.profile.bundles`；`cordis.patch.yml` 无残留 `disabled: true`。
- [ ] 改动前备份 `package.json`、`cordis.patch.yml`；回滚用备份。
- [ ] 完全退出 DSH 再启动，核对：内置区卡片出现、Host 工具可见、managed 后端按预期拉起/退出。

### 9.5 gaussian 插件在本架构中的位置（对照实例）

| 架构层 | gaussian 插件对应物 |
|--------|---------------------|
| Host `tools` | `submit_gaussian_job`、`gaussian_status`、`list_jobs`、`stop_job`、SMILES→输入、后处理任务等工具 |
| Host `systemPrompt` | GAUSSIAN_GUIDANCE 提示词分段（order 85） |
| Host `subprocess` | BackendManager：probe health → reuse/external；managed spawn onedir `gaussian-backend.exe`；受控 dispose |
| Host `connection` | `GET /api/gaussian/status` 返回 host snapshot + 后端摘要；`POST /api/gaussian/retry` 触发幂等重启（5.4） |
| Host 外部后端 | FastAPI `http://127.0.0.1:8765`，Python onedir，串行 lease、PID 三态、recover 接管 |
| Client `slots["plugins.item"]` | "Gaussian 计算助手"状态卡（order 75，namespace `gaussian.status`） |
| Client `locale` | zh/en 标题、描述、状态字段词典 |
| bundle patch | 包内 `cordis.patch.yml` 注册 entry `id: gaussian`，name=`@gaussian/dsh-plugin-gaussian` |
