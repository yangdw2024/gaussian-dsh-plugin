"""RDKit SMILES → 3D 结构生成器。

流程：
1. 解析 SMILES 并规范化
2. 拒绝默认多片段体系（盐等）
3. 检查未指定的手性中心（返回 warning）
4. AddHs（显式氢）
5. 推断电荷与自旋多重度（保守策略：可靠时自动，否则报错）
6. ETKDGv3 生成多构象（默认 24 个，单线程）
7. 检查 MMFF94s 参数完整性（不自动 fallback UFF）
8. MMFF94s 优化所有构象
9. 选出能量最低构象，导出 Gaussian 坐标

注意：
- MMFF energy 只用于同一分子的构象排序，不等于 Gaussian 电子能
- 多片段体系（盐）默认拒绝，因为 MMFF 忽略片段间非键相互作用
- 过渡金属/多自由基/模糊电子组态不自动推断自旋，要求显式指定
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from rdkit import Chem
from rdkit.Chem import AllChem

from .models import (
    AmbiguousSpinError,
    AtomCoordinate,
    DisconnectedMoleculeError,
    MMFFParamError,
    Smiles3DRequest,
    Smiles3DResponse,
)

# 过渡金属和 f 区元素的原子序数
_TRANSITION_METAL_NUMBERS = set(range(21, 31)) | set(range(39, 49)) | set(range(72, 81))
_F_BLOCK_NUMBERS = set(range(57, 72)) | set(range(89, 103))
_METAL_NUMBERS = _TRANSITION_METAL_NUMBERS | _F_BLOCK_NUMBERS


def _infer_multiplicity(
    mol: Chem.Mol,
    charge: int,
    override: Optional[int],
) -> Tuple[int, str]:
    """保守推断自旋多重度。

    Returns:
        (multiplicity, inference_reason)
        inference_reason: closed_shell_singlet / single_radical_doublet / user_override

    Raises:
        AmbiguousSpinError: 无法可靠推断
    """
    # 用户显式指定
    if override is not None:
        electron_count = (
            sum(a.GetAtomicNum() for a in mol.GetAtoms()) - charge
        )
        # 检查电子数和多重度奇偶是否匹配
        # multiplicity = 2S+1，S = (electron_count - core_electrons)/2
        # 简化判断：(electron_count - (multiplicity - 1)) 应该是偶数
        if (electron_count - (override - 1)) % 2 != 0:
            raise AmbiguousSpinError(
                f"电子数 ({electron_count}) 与指定的多重度 ({override}) 奇偶不匹配"
            )
        return override, "user_override"

    # 检查是否含金属
    atomic_numbers = {a.GetAtomicNum() for a in mol.GetAtoms()}
    if atomic_numbers & _METAL_NUMBERS:
        raise AmbiguousSpinError(
            "过渡金属/金属络合物的自旋无法从 SMILES 可靠推断，请显式指定 multiplicity"
        )

    # 计算总电子数（加 H 后）
    electron_count = (
        sum(a.GetAtomicNum() for a in mol.GetAtoms()) - charge
    )

    # 检查自由基电子
    n_rad = sum(a.GetNumRadicalElectrons() for a in mol.GetAtoms())

    # 闭壳层单重态
    if n_rad == 0 and electron_count % 2 == 0:
        return 1, "closed_shell_singlet"

    # 单自由基二重态
    if n_rad == 1 and electron_count % 2 == 1:
        return 2, "single_radical_doublet"

    # 其他情况（多自由基、模糊组态）——不猜
    raise AmbiguousSpinError(
        f"无法可靠推断自旋：电子数={electron_count}, 自由基电子={n_rad}。"
        f"请显式指定 multiplicity。"
    )


def _check_stereochemistry(mol: Chem.Mol) -> List[str]:
    """检查未指定的手性中心，返回警告列表。"""
    warnings = []
    # 查找潜在手性中心（4 个不同取代基的碳）
    chiral_centers = Chem.FindMolChiralCenters(mol, includeUnassigned=True)
    unassigned = [c for c in chiral_centers if c[1] == "?"]
    if unassigned:
        warnings.append(
            f"SMILES 含 {len(unassigned)} 个未指定手性中心，生成的构型仅代表其中一种立体异构体。"
        )
    return warnings


def smiles_to_3d(req: Smiles3DRequest) -> Smiles3DResponse:
    """从 SMILES 生成 3D 结构。

    Raises:
        ValueError: SMILES 无效
        DisconnectedMoleculeError: 多片段体系（盐等）需要显式确认
        AmbiguousSpinError: 自旋无法可靠推断
        MMFFParamError: MMFF94s 参数不完整
    """
    warnings: List[str] = []

    # Step 1: 解析与规范化
    mol = Chem.MolFromSmiles(req.smiles)
    if mol is None:
        raise ValueError(f"无效的 SMILES：{req.smiles}")

    canonical = Chem.MolToSmiles(mol, isomericSmiles=True)
    charge = Chem.GetFormalCharge(mol)

    # Step 2: 拒绝默认多片段体系
    n_frags = len(Chem.GetMolFrags(mol))
    if n_frags > 1 and not req.allow_disconnected:
        raise DisconnectedMoleculeError(
            f"SMILES 包含 {n_frags} 个片段（盐/共晶等）。"
            f"MMFF 默认忽略片段间非键相互作用，阴阳离子相对位置无物理意义。"
            f"如确需处理，请设置 allow_disconnected=true。"
        )

    # Step 3: 检查立体化学
    stereo_warnings = _check_stereochemistry(mol)
    warnings.extend(stereo_warnings)

    # Step 4: 补 H
    mol = Chem.AddHs(mol)

    # Step 5: 推断电荷与 multiplicity
    try:
        multiplicity, spin_reason = _infer_multiplicity(mol, charge, req.multiplicity)
    except AmbiguousSpinError:
        raise

    # Step 6: ETKDGv3 生成多构象
    params = AllChem.ETKDGv3()
    params.randomSeed = req.random_seed
    params.numThreads = 1  # 单线程，保证资源可预测
    params.enforceChirality = True
    params.pruneRmsThresh = -1.0  # 不做 RMS pruning，保留所有构象

    conf_ids = list(
        AllChem.EmbedMultipleConfs(
            mol,
            numConfs=req.num_conformers,
            params=params,
        )
    )

    # 如果一个构象都没生成，用随机坐标重试一次
    if not conf_ids:
        params.useRandomCoords = True
        conf_ids = list(
            AllChem.EmbedMultipleConfs(
                mol,
                numConfs=req.num_conformers,
                params=params,
            )
        )

    if not conf_ids:
        raise ValueError("无法生成任何 3D 构象，SMILES 可能过于复杂或不合理")

    # Step 7: 确认 MMFF 参数完整
    if not AllChem.MMFFHasAllMoleculeParams(mol):
        raise MMFFParamError(
            "MMFF94s 参数不覆盖此分子（含未知元素或特殊官能团）。"
            "不自动 fallback UFF，请手动构建结构。"
        )

    # Step 8: MMFF94s 优化所有构象
    results = AllChem.MMFFOptimizeMoleculeConfs(
        mol,
        numThreads=1,
        maxIters=req.max_iterations,
        mmffVariant="MMFF94s",
    )

    # Step 9: 选出能量最低的收敛构象
    candidates = [
        (cid, status, energy)
        for cid, (status, energy) in zip(conf_ids, results)
        if status == 0  # status=0 表示收敛
    ]

    if not candidates:
        raise ValueError("所有 MMFF94s 构象优化均未收敛")

    best_id, _, best_energy = min(candidates, key=lambda item: item[2])

    # Step 10: 导出 Gaussian 坐标
    conf = mol.GetConformer(best_id)
    atoms: List[AtomCoordinate] = []
    for index, atom in enumerate(mol.GetAtoms()):
        pos = conf.GetAtomPosition(index)
        atoms.append(AtomCoordinate(
            element=atom.GetSymbol(),
            x=float(pos.x),
            y=float(pos.y),
            z=float(pos.z),
        ))

    return Smiles3DResponse(
        canonical_smiles=canonical,
        charge=charge,
        multiplicity=multiplicity,
        spin_inference=spin_reason,
        atoms=atoms,
        generated_conformers=len(conf_ids),
        converged_conformers=len(candidates),
        selected_conformer=best_id,
        mmff_energy=float(best_energy),
        warnings=warnings,
    )
