"""Gaussian 关键词参考库（基于 gaussian.com 官方文档整理，2026-10 核对）。

提供常用关键词的说明、用法、注意事项，以及常见错误诊断。
"""
from __future__ import annotations

from typing import Dict, List


# 关键词参考数据：category -> [{keyword, description, usage, notes}]
KEYWORD_REFERENCE: Dict[str, List[Dict]] = {
    "任务类型": [
        {"keyword": "sp", "description": "单点能计算（默认）", "usage": "# B3LYP/6-31G(d)", "notes": "不写任务类型时默认做单点能。"},
        {"keyword": "opt", "description": "几何优化", "usage": "# B3LYP/6-31G(d) opt", "notes": "默认 Berny 算法；大体系可用 opt=loose 或 opt=gdiis。"},
        {"keyword": "opt=calcfc", "description": "优化开始时计算解析 Hessian", "usage": "# B3LYP/6-31G(d) opt=calcfc", "notes": "大体系（>100原子）内存需求极大，15GB 机器可能爆炸；建议用 opt=calcall 或不加。"},
        {"keyword": "opt=modredundant", "description": "用冗余内坐标优化，可固定/扫描键长键角", "usage": "# B3LYP/6-31G(d) opt=modredundant\n...\nB 1 2 F\nB 1 3 S 10 0.1", "notes": "在坐标后写 ModRedundant 段：F=固定，S=扫描。"},
        {"keyword": "freq", "description": "频率分析与热化学", "usage": "# B3LYP/6-31G(d) freq", "notes": "要求输入结构已是驻点；有虚频说明不是极小点。"},
        {"keyword": "opt freq", "description": "优化后立即做频率", "usage": "# B3LYP/6-31G(d) opt freq", "notes": "优化和频率用同一方法基组；最常用组合。"},
        {"keyword": "td", "description": "TDDFT 激发态计算", "usage": "# B3LYP/6-31G(d) td=(nstates=10)", "notes": "默认单重态激发；三重态用 triplets；root=N 指定关注态。"},
        {"keyword": "irc", "description": "内禀反应坐标追踪", "usage": "# B3LYP/6-31G(d) irc=(rcfc,maxpoints=50,stepsize=10)", "notes": "需从过渡态出发；rcfc 在起点算 Hessian。"},
        {"keyword": "scan", "description": "势能面扫描", "usage": "# B3LYP/6-31G(d) scan\n...\nB 1 2 S 20 0.1", "notes": "配合 ModRedundant 段使用。"},
    ],
    "方法与泛函": [
        {"keyword": "HF", "description": "Hartree-Fock 方法", "usage": "# HF/6-31G(d)", "notes": "速度快但忽略电子相关，能量偏高。"},
        {"keyword": "B3LYP", "description": "Becke 三参数杂化泛函（最常用）", "usage": "# B3LYP/6-31G(d,p)", "notes": "有机分子几何优化首选；对弱相互作用需加色散校正。"},
        {"keyword": "wB97XD", "description": "范围分离杂化泛函（含经验色散）", "usage": "# wB97XD/6-31G(d,p)", "notes": "对电荷转移激发态、长程相互作用优于 B3LYP。"},
        {"keyword": "M062X", "description": "Minnesota 杂化 meta-GGA 泛函", "usage": "# M062X/6-31G(d,p)", "notes": "主族热化学、非共价相互作用表现好；积分格点需 ultrafine。"},
        {"keyword": "CAM-B3LYP", "description": "库仑衰减杂化泛函", "usage": "# CAM-B3LYP/6-31G(d,p)", "notes": "适合电荷转移激发态和长程体系。"},
        {"keyword": "PBE0", "description": "PBE 杂化泛函", "usage": "# PBE0/6-31G(d,p)", "notes": "固体和分子均常用。"},
        {"keyword": "MP2", "description": "二阶 Møller-Plesset 微扰", "usage": "# MP2/6-31G(d)", "notes": "含动态电子相关；计算量比 DFT 大，大体系慢。"},
        {"keyword": "CCSD(T)", "description": "耦合簇（金标准）", "usage": "# CCSD(T)/cc-pVTZ", "notes": "精度极高但计算量 O(N^7)，仅适用于小分子。"},
    ],
    "SCF 控制": [
        {"keyword": "scf=tight", "description": "更严格的 SCF 收敛判据（G16 默认）", "usage": "# B3LYP/6-31G(d) scf=tight", "notes": "Gaussian 16 默认即为 tight；G09 默认是常规。"},
        {"keyword": "scf=xqc", "description": "SCF 不收敛时自动切换算法重试", "usage": "# B3LYP/6-31G(d) scf=xqc", "notes": "难收敛体系推荐；xqc = extra QC。"},
        {"keyword": "scf=qc", "description": "强制使用 QC（二次收敛）算法", "usage": "# B3LYP/6-31G(d) scf=qc", "notes": "对极难收敛体系有效，但每步更慢。"},
        {"keyword": "scf=conventional", "description": "传统双电子积分（非 direct）", "usage": "# B3LYP/6-31G(d) scf=conventional", "notes": "小体系可加速；大体系磁盘需求大。"},
        {"keyword": "scf=maxcycle=N", "description": "设置最大 SCF 迭代次数", "usage": "# B3LYP/6-31G(d) scf=(maxcycle=200)", "notes": "默认 128；难收敛体系可加大。"},
        {"keyword": "scf=noincfock", "description": "禁用增量 Fock 矩阵", "usage": "# B3LYP/6-31G(d) scf=noincfock", "notes": "某些体系收敛问题的解决方案。"},
    ],
    "色散与格点": [
        {"keyword": "empiricaldispersion=gd3bj", "description": "Grimme D3 色散校正（Becke-Johnson 阻尼）", "usage": "# B3LYP/6-31G(d,p) empiricaldispersion=gd3bj", "notes": "有机分子弱相互作用、堆积体系推荐；GD3BJ 优于 GD3。"},
        {"keyword": "empiricaldispersion=gd3", "description": "Grimme D3 色散校正（零阻尼）", "usage": "# B3LYP/6-31G(d,p) empiricaldispersion=gd3", "notes": "部分文献用此版本；新计算推荐 gd3bj。"},
        {"keyword": "int=ultrafine", "description": "超精细积分格点（99,590）", "usage": "# B3LYP/6-31G(d,p) int=ultrafine", "notes": "M062X 等 meta-GGA 必须用；优化收敛更稳。"},
        {"keyword": "int=fine", "description": "精细积分格点（75,302）", "usage": "# B3LYP/6-31G(d,p) int=fine", "notes": "G16 默认即为 fine。"},
    ],
    "溶剂模型": [
        {"keyword": "scrf=(pcm,solvent=water)", "description": "PCM 隐式溶剂模型", "usage": "# B3LYP/6-31G(d) scrf=(pcm,solvent=water)", "notes": "常用溶剂：water, ethanol, methanol, acetonitrile, dichloromethane, chloroform, toluene, dmso。"},
        {"keyword": "scrf=(smd,solvent=water)", "description": "SMD 溶剂模型（适合溶解自由能）", "usage": "# B3LYP/6-31G(d) scrf=(smd,solvent=water)", "notes": "SMD 在溶解自由能计算上更准；几何优化也可用。"},
        {"keyword": "scrf=(cpcm,solvent=water)", "description": "CPCM 导体极化连续模型", "usage": "# B3LYP/6-31G(d) scrf=(cpcm,solvent=water)", "notes": "PCM 的变体。"},
    ],
    "波函数与布居": [
        {"keyword": "pop=nbo", "description": "NBO 自然键轨道分析", "usage": "# B3LYP/6-31G(d) pop=nbo", "notes": "输出 NBO 电荷、键级、给体-受体相互作用。"},
        {"keyword": "pop=full", "description": "输出完整轨道系数", "usage": "# B3LYP/6-31G(d) pop=full", "notes": "大体系输出量大。"},
        {"keyword": "gfinput", "description": "输出可被其他程序读取的轨道信息", "usage": "# B3LYP/6-31G(d) gfinput", "notes": "用于 Multiwfn 等后处理程序读取。"},
        {"keyword": "gfprint", "description": "打印完整轨道系数", "usage": "# B3LYP/6-31G(d) gfprint", "notes": "比 pop=full 更详细。"},
    ],
    "常见错误与解决方案": [
        {"keyword": "Convergence failure", "description": "SCF 收敛失败", "usage": "scf=xqc scf=(maxcycle=200) guess=read", "notes": "方案：①加 scf=xqc；②加大 maxcycle；③用 guess=read 从 chk 读初猜；④降低积分精度 int=fine；⑤小基组预优化。"},
        {"keyword": "Error termination in l101.exe", "description": "优化失败（通常是坐标问题或不收敛）", "usage": "opt=loose 或 opt=gdiis 或 opt=calcfc", "notes": "方案：①检查初始结构合理性；②用 opt=loose 放宽判据；③用 opt=gdiis 换算法；④小基组预优化。"},
        {"keyword": "Out-of-memory / 内存不足", "description": "内存超限", "usage": "%mem=12GB（不要超过物理内存）", "notes": "方案：①降低 mem（必须 < 物理内存）；②减少 nproc；③去掉 calcfc/calcall；④用 direct 模式减少磁盘；⑤大体系分步骤计算。"},
        {"keyword": "File operation error", "description": "文件读写错误（通常是 chk 或 rwf）", "usage": "%rwf=/path/to/scratch", "notes": "方案：①检查磁盘空间；②指定 %rwf 到有空间的盘；③删除旧 chk 重新开始；④检查文件名含特殊字符。"},
        {"keyword": "Basis set specification error", "description": "基组指定错误", "usage": "用 gen 关键字 + 附加段提供基组", "notes": "方案：①确认基组名拼写；②含重元素用 ECP（如 lanl2dz, sdd）；③自定义基组用 gen/genecp。"},
        {"keyword": "The combination of multiplicity and charge is inconsistent", "description": "电荷与自旋多重度不匹配", "usage": "检查 charge 和 multiplicity", "notes": "闭壳层 multiplicity=1；自由基 multiplicity=2；电子数 = 原子序数之和 - charge；multiplicity = 2S+1。"},
    ],
}


def search_keywords(query: str, limit: int = 30) -> List[Dict]:
    """搜索关键词参考。"""
    q = query.lower().strip()
    results = []
    for category, items in KEYWORD_REFERENCE.items():
        for item in items:
            score = 0
            if q == item["keyword"].lower():
                score += 100
            elif q in item["keyword"].lower():
                score += 50
            if q in item["description"].lower():
                score += 20
            if q in item.get("notes", "").lower():
                score += 10
            if q in category.lower():
                score += 5
            if score > 0:
                results.append({"score": score, "category": category, **item})
    results.sort(key=lambda x: -x["score"])
    return results[:limit]


def get_all_categories() -> List[str]:
    """获取所有分类。"""
    return list(KEYWORD_REFERENCE.keys())


def get_category(category: str) -> List[Dict]:
    """获取指定分类的所有关键词。"""
    return KEYWORD_REFERENCE.get(category, [])
