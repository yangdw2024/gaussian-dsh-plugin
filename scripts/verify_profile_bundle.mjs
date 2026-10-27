// 离线复刻 DSH app-boot 的 bundle 解析链 + client-modules manifest 校验，
// 在不重启 DSH 的前提下确认本插件能被 profile 装载、client half 能被发现。
// 对应源码：@deepseek-ai/dsh-app-boot/lib/index.js（1016-1042 行 bundles 装载）、
// @deepseek-ai/dsh-client-modules/lib/index.js（resolveMeta 720-749 行 manifest 校验）。
//
// 用法：node scripts/verify_profile_bundle.mjs
// 可选环境变量：DSH_PROFILE_DIR（默认新布局 %APPDATA%\dsh-desktop\harness\profiles\web；旧布局传 .dsh\profiles\<name>）

import { createRequire } from "node:module";
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";

const profileDir = process.env.DSH_PROFILE_DIR || "C:/Users/Administrator/AppData/Roaming/dsh-desktop/harness/profiles/web";
const anchor = join(profileDir, "package.json");
const requireAnchor = createRequire(anchor);
const problems = [];

const pkgName = "@gd/gp";
const profile = JSON.parse(readFileSync(anchor, "utf8"));
const bundles = profile.dsh?.profile?.bundles ?? [];
console.log("profile bundles:", JSON.stringify(bundles, null, 0));
if (!bundles.includes(pkgName)) {
  problems.push(`${pkgName} 未列入 dsh.profile.bundles，自带 cordis.patch.yml 不会进入 host loader`);
}

// user layer 不得残留禁用段（纯文本检查，避免引入 YAML 依赖）
const patchPath = join(profileDir, "cordis.patch.yml");
if (existsSync(patchPath)) {
  const patchText = readFileSync(patchPath, "utf8");
  if (/- id:\s*gaussian\b/.test(patchText) && /disabled:\s*true/.test(patchText)) {
    problems.push("profile cordis.patch.yml 残留 `- id: gaussian / disabled: true`，entry 会被禁用");
  }
}

function checkManifest(name) {
  console.log(`\n=== ${name} ===`);
  let pkgJsonPath;
  try {
    pkgJsonPath = requireAnchor.resolve(`${name}/package.json`);
  } catch (e) {
    problems.push(`${name}: 无法解析 package.json — ${e.message}`);
    console.log("FAIL: cannot resolve package.json:", e.message);
    return;
  }
  console.log("package.json:", pkgJsonPath);
  const manifest = JSON.parse(readFileSync(pkgJsonPath, "utf8"));
  const pkgDir = dirname(pkgJsonPath);

  const bundle = manifest.dsh?.bundle;
  if (!bundle || typeof bundle.patch !== "string") {
    problems.push(`${name}: 缺少 dsh.bundle.patch 字符串`);
    console.log("FAIL: no dsh.bundle.patch");
    return;
  }
  const bundlePatch = join(pkgDir, bundle.patch);
  console.log("bundle.patch exists:", existsSync(bundlePatch));
  if (!existsSync(bundlePatch)) problems.push(`${name}: bundle.patch 文件不存在 ${bundlePatch}`);

  const client = manifest.dsh?.client;
  if (!client || client.platform !== "web") {
    problems.push(`${name}: dsh.client.platform 不是 web`);
    console.log("FAIL: dsh.client.platform != web:", client);
    return;
  }
  console.log("dsh.client.platform:", client.platform, "inject:", JSON.stringify(client.inject));

  const clientRel = manifest.exports?.["./client"];
  if (typeof clientRel !== "string") {
    problems.push(`${name}: exports["./client"] 缺失或非字符串`);
    return;
  }
  const clientPath = join(pkgDir, clientRel);
  console.log("client.js exists:", existsSync(clientPath));
  if (!existsSync(clientPath)) problems.push(`${name}: client 文件不存在 ${clientPath}`);

  const mainRel = manifest.main || "lib/index.js";
  const mainPath = join(pkgDir, mainRel);
  console.log("main exists:", existsSync(mainPath));
  if (!existsSync(mainPath)) problems.push(`${name}: 后端入口不存在 ${mainPath}`);
}

checkManifest(pkgName);

if (problems.length) {
  console.error("\nFAIL:");
  for (const p of problems) console.error("  -", p);
  process.exit(1);
}
console.log("\nPASS: profile bundle 注册与 manifest 解析链完整");
