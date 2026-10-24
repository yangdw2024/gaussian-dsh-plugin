// R14: 把 gaussian bundle 重新登记进 profile dsh.profile.bundles（内置模板项保留在前）。
// 不改动 aifs/autorest，不重写其他 manifest 字段；JSON 以 2 空格缩进落盘。
import { readFileSync, writeFileSync } from "node:fs";

const profileDir = "C:/Users/Administrator/.dsh/profiles/desktop";
const pkgPath = `${profileDir}/package.json`;
const PKG = "@gaussian/dsh-plugin-gaussian";

const manifest = JSON.parse(readFileSync(pkgPath, "utf8"));
manifest.dsh ??= {};
manifest.dsh.profile ??= {};
const bundles = manifest.dsh.profile.bundles ?? [];
if (!bundles.includes(PKG)) bundles.push(PKG);
manifest.dsh.profile.bundles = bundles;

writeFileSync(pkgPath, JSON.stringify(manifest, null, 2) + "\n", "utf8");
console.log("bundles:", JSON.stringify(bundles, null, 2));
