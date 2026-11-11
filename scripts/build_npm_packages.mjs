#!/usr/bin/env node
/**
 * Build & package npm tarballs for Gaussian DSH Plugin:
 *   1. @yangdw2024/gp (primary public npm package)
 *   2. @gd/gp         (optional backward-compatible short-scope alias)
 *
 * Also validates Windows MAX_PATH (260) safety against a worst-case DSH generation root.
 */
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const rootDir = path.resolve(__dirname, "..");

const DSH_GENERATION_PREFIX =
  "C:\\Users\\Administrator\\AppData\\Roaming\\dsh-desktop\\harness\\profiles\\.generations\\live\\yangdw2024-gp+0.3.0+1234567890ab\\node_modules\\@yangdw2024\\gp\\";

function walkFiles(dir, base = dir, out = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      walkFiles(full, base, out);
    } else if (entry.isFile()) {
      out.push(path.relative(base, full).replace(/\\/g, "/"));
    }
  }
  return out;
}

function assertRuntimePathBudget() {
  const rtDir = path.join(rootDir, "runtimes", "win32-x64");
  const rjPath = path.join(rtDir, "runtime.json");
  if (!fs.existsSync(rjPath)) {
    throw new Error(`Missing runtime manifest: ${rjPath}`);
  }
  const rj = JSON.parse(fs.readFileSync(rjPath, "utf8").replace(/^\uFEFF/, ""));
  const pkg = JSON.parse(fs.readFileSync(path.join(rootDir, "package.json"), "utf8"));
  if (rj.version !== pkg.version) {
    throw new Error(`Version mismatch: runtime.json (${rj.version}) != package.json (${pkg.version})`);
  }
  const exePath = path.join(rtDir, rj.executable || "b/gaussian-backend.exe");
  if (!fs.existsSync(exePath)) {
    throw new Error(`Missing backend executable: ${exePath}`);
  }
  const relFiles = walkFiles(path.join(rootDir, "runtimes"), rootDir);
  let maxRel = 0;
  let maxFile = "";
  for (const rel of relFiles) {
    if (rel.length > maxRel) {
      maxRel = rel.length;
      maxFile = rel;
    }
  }
  const worstCaseFull = DSH_GENERATION_PREFIX.length + maxRel;
  console.log(`Runtime files scanned : ${relFiles.length}`);
  console.log(`Longest pkg rel path  : ${maxRel} chars (${maxFile})`);
  console.log(`Simulated DSH @yangdw2024/gp full path: ${worstCaseFull} chars (< 260)`);
  if (worstCaseFull >= 260) {
    throw new Error(`Windows MAX_PATH exceeded (${worstCaseFull} >= 260): ${maxFile}`);
  }
}

function runNpmPack(cwd, outDir) {
  const npmCmd = process.platform === "win32" ? "npm.cmd" : "npm";
  const stdout = execFileSync(npmCmd, ["pack", "--pack-destination", outDir], {
    cwd,
    encoding: "utf8",
    shell: process.platform === "win32",
  });
  return stdout.trim().split(/\r?\n/).pop().trim();
}

async function main() {
  const outArgIdx = process.argv.indexOf("--out");
  const outDir = path.resolve(
    rootDir,
    outArgIdx >= 0 && process.argv[outArgIdx + 1] ? process.argv[outArgIdx + 1] : "dist/release-candidate"
  );
  const skipCompat = process.argv.includes("--primary-only");

  fs.mkdirSync(outDir, { recursive: true });

  console.log("1. Rebuilding JS bundle...");
  execFileSync(process.execPath, [path.join(rootDir, "scripts", "build.mjs")], {
    cwd: rootDir,
    stdio: "inherit",
  });

  console.log("2. Auditing MAX_PATH budget...");
  assertRuntimePathBudget();

  console.log("3. Packing primary npm tarball (@yangdw2024/gp)...");
  const primaryTgz = runNpmPack(rootDir, outDir);
  console.log(`Primary tarball ready: ${path.join(outDir, primaryTgz)}`);

  if (!skipCompat) {
    console.log("4. Packing backward-compat alias (@gd/gp) in temp staging...");
    const stageDir = fs.mkdtempSync(path.join(os.tmpdir(), "gp-compat-stage-"));
    try {
      for (const item of ["package.json", "cordis.patch.yml", "README.md", "LICENSE", "src", "scripts", "lib", "runtimes"]) {
        const src = path.join(rootDir, item);
        if (fs.existsSync(src)) {
          fs.cpSync(src, path.join(stageDir, item), { recursive: true });
        }
      }
      const pkgPath = path.join(stageDir, "package.json");
      const pkgJson = JSON.parse(fs.readFileSync(pkgPath, "utf8"));
      pkgJson.name = "@gd/gp";
      fs.writeFileSync(pkgPath, JSON.stringify(pkgJson, null, 2) + "\n", "utf8");

      const patchPath = path.join(stageDir, "cordis.patch.yml");
      if (fs.existsSync(patchPath)) {
        fs.writeFileSync(
          patchPath,
          fs.readFileSync(patchPath, "utf8").replace("@yangdw2024/gp", "@gd/gp"),
          "utf8"
        );
      }
      const clientSrcPath = path.join(stageDir, "src", "client.js");
      fs.writeFileSync(
        clientSrcPath,
        fs.readFileSync(clientSrcPath, "utf8").replace('"@yangdw2024/gp"', '"@gd/gp"'),
        "utf8"
      );
      const nmSrc = path.join(rootDir, "node_modules");
      const nmDst = path.join(stageDir, "node_modules");
      if (fs.existsSync(nmSrc)) {
        fs.symlinkSync(nmSrc, nmDst, "junction");
      }
      execFileSync(process.execPath, [path.join(stageDir, "scripts", "build.mjs")], {
        cwd: stageDir,
        stdio: "inherit",
      });
      if (fs.existsSync(nmDst)) {
        fs.unlinkSync(nmDst);
      }
      const compatTgz = runNpmPack(stageDir, outDir);
      console.log(`Compat tarball ready: ${path.join(outDir, compatTgz)}`);
    } finally {
      fs.rmSync(stageDir, { recursive: true, force: true });
    }
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
