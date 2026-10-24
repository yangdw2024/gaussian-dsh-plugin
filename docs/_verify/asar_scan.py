# -*- coding: utf-8 -*-
# 临时：遍历 app.asar 文件树，定位 connection / subprocess 服务相关源码路径（只读，不落地大文件）
import struct, json, sys

ASAR = r"E:\DSH\resources\app.asar"
f = open(ASAR, "rb")
f.seek(12)
(hsize,) = struct.unpack("<I", f.read(4))
f.seek(16)
header = json.loads(f.read(hsize))

hits = []
def walk(node, prefix):
    files = node.get("files", {})
    for name, child in files.items():
        path = prefix + "/" + name
        if "files" in child:
            walk(child, path)
        else:
            low = path.lower()
            if ("connection" in low or "subprocess" in low) and low.endswith((".js", ".mjs", ".ts")):
                hits.append(path)

walk(header, "")
for h in hits:
    print(h)
print("---- total hits:", len(hits))
