# -*- coding: utf-8 -*-
# 临时：从 app.asar 提取官方 connection/subprocess 包，核验 fetch.register 与 spawn 契约
import struct, json, re

ASAR = r"E:\DSH\resources\app.asar"
f = open(ASAR, "rb")
f.seek(12)
(hsize,) = struct.unpack("<I", f.read(4))
f.seek(16)
header = json.loads(f.read(hsize))
DATA_START = 16 + hsize

def find(node, prefix, target):
    for name, child in node.get("files", {}).items():
        path = (prefix + "/" + name) if prefix else name
        if path == target:
            return child
        if "files" in child:
            r = find(child, path, target)
            if r is not None:
                return r
    return None

def extract(path):
    node = find(header, "", path)
    if not node:
        return None
    off = int(node["offset"]); size = int(node["size"])
    f.seek(DATA_START + off)
    return f.read(size).decode("utf-8", errors="replace")

targets = [
    "dsh/node_modules/@deepseek-ai/dsh-client-connection/lib/index.js",
    "dsh/node_modules/@deepseek-ai/dsh-subprocess/lib/index.js",
]
for t in targets:
    txt = extract(t)
    print("=" * 25, t, "len=", len(txt) if txt else "MISSING")
    if txt:
        for i, line in enumerate(txt.splitlines(), 1):
            if re.search(r"fetch\.register|register\(|/api/|path:|methods|spawn\(|waitForExit|name\s*:|provide|class |service|route", line):
                print(f"{i:4d}| {line[:170]}")
