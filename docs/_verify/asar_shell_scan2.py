# -*- coding: utf-8 -*-
# 临时排查：解出 DSH Windows 命令执行相关包，定位 0xC0000142 根因。打包排除。
import struct, json, os, re

ASAR = r"E:\DSH\resources\app.asar"
OUT = r"E:\YDW\ChemDatas\gaussian-dsh-plugin\docs\_dsh_unpack\dsh"
f = open(ASAR, "rb")
f.seek(12)
(hsize,) = struct.unpack("<I", f.read(4))
f.seek(16)
header = json.loads(f.read(hsize))
DS = 16 + hsize

targets = [
    "/dsh/node_modules/@deepseek-ai/dsh-win32-process",
    "/dsh/node_modules/@deepseek-ai/dsh-subprocess-local",
    "/dsh/node_modules/@deepseek-ai/dsh-shell",
    "/dsh/node_modules/@deepseek-ai/dsh-shell-env",
    "/dsh/node_modules/@deepseek-ai/dsh-tool-terminal",
    "/dsh/node_modules/@deepseek-ai/dsh-terminal",
    "/dsh/node_modules/powershell-utils",
]

all_files = []
def walk(node, cur):
    for name, child in node.get("files", {}).items():
        path = cur + "/" + name
        if "files" in child:
            walk(child, path)
        else:
            all_files.append((path, int(child.get("size", -1)), int(child.get("offset", -1))))
walk(header, "")

saved = []
for p, s, o in all_files:
    if any(p.startswith(t) for t in targets) and p.lower().endswith((".js", ".json", ".mjs")):
        f.seek(DS + o)
        data = f.read(s)
        rel = p[len("/dsh/node_modules/"):]
        dst = os.path.join(OUT, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "wb") as w:
            w.write(data)
        saved.append(dst)
print("saved:", len(saved))

KW = ["powershell", "pwsh", "cmd.exe", "ComSpec", "SystemRoot", "3221225794", "0xC0000142",
      "STATUS_DLL", "spawn", "execFile", "exitCode", "node-pty", "windowsTerminal", "cwd", "env:",
      "process.env", "shellPath", "defaultShell", "powershell.exe"]
for dst in saved:
    txt = open(dst, encoding="utf-8", errors="replace").read()
    hits = {kw: len(re.findall(re.escape(kw), txt)) for kw in KW if re.search(re.escape(kw), txt, re.I)}
    if hits:
        print("\n###", os.path.relpath(dst, OUT))
        for k, v in hits.items():
            print(f"   {k} x{v}")
