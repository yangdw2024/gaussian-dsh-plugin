# -*- coding: utf-8 -*-
# 临时：核验官方 dsh-client-connection 的服务名与 fetch.register 注册形态
import struct, json, re

ASAR = r"E:\DSH\resources\app.asar"
f = open(ASAR, "rb")
f.seek(12)
(hsize,) = struct.unpack("<I", f.read(4))
f.seek(16)
header = json.loads(f.read(hsize))
DS = 16 + hsize

def find(n, p, t):
    for k, c in n.get("files", {}).items():
        q = (p + "/" + k) if p else k
        if q == t:
            return c
        if "files" in c:
            r = find(c, q, t)
            if r is not None:
                return r

node = find(header, "", "dsh/node_modules/@deepseek-ai/dsh-client-connection/lib/index.js")
f.seek(DS + int(node["offset"]))
txt = f.read(int(node["size"])).decode("utf-8", "replace")
for i, line in enumerate(txt.splitlines(), 1):
    if re.search(r"super\(ctx|connection|Service\(|fetch =|register:|this\.fetch", line):
        print(f"{i:4d}| {line[:150]}")
