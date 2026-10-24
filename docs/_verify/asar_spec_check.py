# -*- coding: utf-8 -*-
# 临时：在 asar 文件树中定位 validateSubprocessSpec / targetEnvironment / runnerStdio 定义并打印
import struct, json, re

ASAR = r"E:\DSH\resources\app.asar"
f = open(ASAR, "rb")
f.seek(12)
(hsize,) = struct.unpack("<I", f.read(4))
f.seek(16)
header = json.loads(f.read(hsize))
DS = 16 + hsize

files = {}
def walk(node, prefix):
    for name, child in node.get("files", {}).items():
        path = (prefix + "/" + name) if prefix else name
        if "files" in child:
            walk(child, path)
        else:
            files[path] = child
walk(header, "")

def read(node):
    f.seek(DS + int(node["offset"]))
    return f.read(int(node["size"])).decode("utf-8", "replace")

needles = ["validateSubprocessSpec", "function targetEnvironment", "function runnerStdio", "function childEnv"]
for path, node in files.items():
    if not path.endswith(".js"):
        continue
    if "@deepseek-ai/dsh-subprocess" not in path and "subprocess-local" not in path:
        continue
    txt = read(node)
    hit = [n for n in needles if n in txt]
    if hit:
        print("####", path, hit)
        for i, line in enumerate(txt.splitlines(), 1):
            if any(n in line for n in ["validateSubprocessSpec", "targetEnvironment", "runnerStdio", "childEnv"]) or re.search(r"inherit|ignore|collect|pipe|cwd|argv|stdio\.|requestBody|methods", line) and i < 0:
                pass
        # 只打印定义函数体附近
        for n in hit:
            m = re.search(re.escape(n) + r".*", txt)
            if m:
                idx = txt.find(n)
                print(txt[max(0, idx-200): idx+1600])
                print("-" * 60)
