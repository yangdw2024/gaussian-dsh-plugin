# -*- coding: utf-8 -*-
# 临时：列出 asar 内与 agent/model/provider/llm 相关的包目录名（只读清单）。
import struct, json

ASAR = r"E:\DSH\resources\app.asar"
f = open(ASAR, "rb")
f.seek(12)
(hsize,) = struct.unpack("<I", f.read(4))
f.seek(16)
header = json.loads(f.read(hsize))

pkgs = set()
def walk(node, prefix):
    for name, child in node.get("files", {}).items():
        path = prefix + "/" + name
        if "files" in child:
            walk(child, path)
        else:
            parts = path.split("/")
            if len(parts) >= 5 and parts[1] == "node_modules":
                scope = parts[2] if parts[2].startswith("@") else ""
                pkg = parts[3] if scope else parts[2]
                pkgs.add(scope + "/" + pkg if scope else pkg)
walk(header, "")
for p in sorted(pkgs):
    low = p.lower()
    if any(k in low for k in ["agent", "model", "llm", "provider", "tool", "chat", "completion", "openai", "deepseek", "anthropic", "gateway", "runtime"]):
        print(p)
