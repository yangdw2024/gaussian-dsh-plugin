# -*- coding: utf-8 -*-
# 临时：核验 dsh-subprocess-local 的 stdio 模式、targetEnv 合并、spawn/handle 契约
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

def read(path):
    node = find(header, "", path)
    f.seek(DS + int(node["offset"]))
    return f.read(int(node["size"])).decode("utf-8", "replace")

txt = read("dsh/node_modules/@deepseek-ai/dsh-subprocess-local/lib/index.js")
lines = txt.splitlines()
pats = re.compile(r"function runnerStdio|inherit|stdio\.|stdout|stderr|targetEnv|spec\.env|scrubbed|ignore|collect|pipe|graceMs|waitForExit|class .*Handle|spawn\(|resolveTargetEnv", re.I)
for i, l in enumerate(lines, 1):
    if pats.search(l):
        print(f"{i:4d}| {l[:155]}")
