/**
 * Gaussian DSH Plugin 前端打包脚本
 *
 * 用 esbuild 将 src/index.js 和 src/client.js 打包到 lib/。
 * 参考 AIFS 插件的打包方式（esbuild 0.28.2）。
 *
 * 用法：node scripts/build.mjs [--watch]
 */

import { build } from "esbuild";
import { fileURLToPath } from "url";
import { dirname, resolve } from "path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = resolve(__dirname, "..");

const watch = process.argv.includes("--watch");

const commonOptions = {
  bundle: true,
  target: "es2022",
  logLevel: "info",
  // DSH 运行时提供的外部依赖 + Node 内置，不打包
  external: ["react", "react-dom", "@deepseek-ai/*", "node:fs", "node:path", "node:os", "node:url", "node:crypto"],
};

async function buildIndex() {
  const options = {
    ...commonOptions,
    entryPoints: [resolve(root, "src/index.js")],
    outfile: resolve(root, "lib/index.js"),
    format: "esm",
    platform: "neutral",
    sourcemap: false,
    minify: false,
  };
  if (watch) {
    const ctx = await build({ ...options, watch: true });
    return ctx;
  }
  await build(options);
}

async function buildClient() {
  const options = {
    ...commonOptions,
    entryPoints: [resolve(root, "src/client.js")],
    outfile: resolve(root, "lib/client.js"),
    format: "iife",
    platform: "browser",
    sourcemap: false,
    minify: false,
    // client.js 用了 window.__ModuleLoader__，不需要 bundle 外部
    banner: { js: "/* Gaussian DSH Plugin client */" },
  };
  if (watch) {
    const ctx = await build({ ...options, watch: true });
    return ctx;
  }
  await build(options);
}

async function main() {
  console.log("Building Gaussian DSH Plugin...");
  console.log("  root:", root);
  await Promise.all([buildIndex(), buildClient()]);
  console.log("Build complete. Output:");
  console.log("  lib/index.js");
  console.log("  lib/client.js");
}

main().catch((err) => {
  console.error("Build failed:", err);
  process.exit(1);
});
