# -*- coding: utf-8 -*-
# 临时：解包 @deepseek-ai/dsh-tools 到 docs/_dsh_unpack（离线契约脚本会优先引用该目录）。
import struct, json, os

ASAR = r"E:\DSH\resources\app.asar"
OUT = r"E:\YDW\ChemDatas\gaussian-dsh-plugin\docs\_dsh_unpack\dsh\node_modules\@deepseek-ai\dsh-tools"

f = open(ASAR, "rb")
f.seek(12)
(hsize,) = struct.unpack("<I", f.read(4))
f.seek(16)
header = json.loads(f.read(hsize))
DS = 16 + hsize

prefix = "/dsh/node_modules/@deepseek-ai/dsh-tools"
saved = []
def walk(node, cur):
    for name, child in node.get("files", {}).items():
        path = cur + "/" + name
        if "files" in child:
            walk(child, path)
        elif path.startswith(prefix) and path.lower().endswith((".js", ".json")):
            off = int(child.get("offset", -1)); size = int(child.get("size", -1))
            f.seek(DS + off)
            data = f.read(size)
            rel = path[len(prefix):].lstrip("/")
            dst = os.path.join(OUT, rel.replace("/", os.sep))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "wb") as w:
                w.write(data)
            saved.append((rel, size))
walk(header, "")
for rel, size in saved:
    print(f"{size:8d}  {rel}")
print("saved:", len(saved))
