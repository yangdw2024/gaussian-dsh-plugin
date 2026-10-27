// 模拟 DSH cordis-plugin-loader.unwrapExports + Cordis 读取 plugin.inject/apply/name
// 路径可由 DSH_PROFILE_DIR 覆盖（默认新布局 web profile），避免硬编码过期。
import { pathToFileURL } from "node:url";
import { join } from "node:path";

const profileDir =
  process.env.DSH_PROFILE_DIR ||
  "C:/Users/Administrator/AppData/Roaming/dsh-desktop/harness/profiles/web";
const file = pathToFileURL(join(profileDir, "node_modules/@gd/gp/lib/index.js")).href;
const ns = await import(file);

// 与 cordis-plugin-loader/lib/index.js unwrapExports 等价
let exports = ns.default ?? ns;
if (!exports.__esModule) exports = exports;
else exports = exports.default ?? exports;

const problems = [];
if (typeof exports.apply !== "function") problems.push("plugin.apply 不是函数");
if (!exports.name) problems.push("plugin.name 缺失");
if (!Array.isArray(exports.inject) || !exports.inject.includes("tools") || !exports.inject.includes("systemPrompt")) {
  problems.push("plugin.inject 未包含 tools/systemPrompt，实际=" + JSON.stringify(exports.inject));
}

console.log("plugin.name =", exports.name);
console.log("plugin.inject =", JSON.stringify(exports.inject));
console.log("plugin.apply =", typeof exports.apply);
if (problems.length) {
  console.error("FAIL:", problems.join("; "));
  process.exit(1);
} else {
  console.log("PASS: DSH 加载路径下 plugin 对象正确携带 inject/apply/name");
}
