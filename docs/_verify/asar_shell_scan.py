# -*- coding: utf-8 -*-
# 临时排查：列出 app.asar 结构，定位 shell/terminal 工具 spawn 实现。打包排除。
import struct, json, os, re

ASAR = r"E:\DSH\resources\app.asar"
f = open(ASAR, "rb")
f.seek(12)
(hsize,) = struct.unpack("<I", f.read(4))
f.seek(16)
header = json.loads(f.read(hsize))
DS = 16 + hsize

def walk(node, cur, out):
    for name, child in node.get("files", {}).items():
        path = cur + "/" + name
        if "files" in child:
            walk(child, path, out)
        else:
            out.append((path, int(child.get("size", -1)), int(child.get("offset", -1))))

all_files = []
walk(header, "", all_files)
print("===== root / lib top-level =====")
for p, s, o in all_files:
    if p.count("/") <= 2 and p.lower().endswith((".js", ".json", ".mjs")):
        print(f"{s:10d}  {p}")

# 找 shell/terminal/process 相关模块名
print("\n===== shell/terminal/process/cmd related paths =====")
for p, s, o in all_files:
    low = p.lower()
    if any(k in low for k in ("shell", "terminal", "process", "exec", "spawn", "cmd-", "command")):
        print(f"{s:10d}  {p}")

def read(path):
    for p, s, o in all_files:
        if p == path:
            f.seek(DS + o)
            return f.read(s).decode("utf-8", "replace")
    return None

# 在 lib/main.js 检索 spawn 命令关键词
main = read("/lib/main.js")
if main:
    print("\n===== main.js keyword hits =====")
    for kw in ["pwsh", "powershell", "cmd.exe", "3221225794", "0xC0000142", "STATUS_DLL", "spawn(", "execFile", "shell:", "SystemRoot", "process.env.ComSpec", "terminal"]:
        idxs = [m.start() for m in re.finditer(re.escape(kw), main)]
        if idxs:
            print(f"\n--- '{kw}' x{len(idxs)} ---")
            for i in idxs[:4]:
                seg = main[max(0, i-160):i+200].replace("\n", " ")
                print("  …" + seg + "…")
