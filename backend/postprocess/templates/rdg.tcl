# rdg.tcl — RDG/NCI 弱相互作用可视化
# 用法：vmd -dispdev text -e rdg.tcl -args signlambda2.cub rdg.cub output.tga
# argv:
#   0: sign(lambda2)rho cube 文件
#   1: RDG cube 文件
#   2: 输出 TGA 文件

if {[llength $argv] < 3} {
    puts stderr "usage: rdg.tcl signlambda2.cub rdg.cub output.tga"
    exit 2
}

set signrho [lindex $argv 0]
set rdg     [lindex $argv 1]
set output  [lindex $argv 2]

# Dataset 0 = sign(lambda2)rho
set molid [mol new $signrho type cube waitfor all]

# Dataset 1 = RDG
mol addfile $rdg type cube waitfor all $molid

# 删除默认表示
mol delrep 0 $molid

# 分子骨架
mol representation Licorice 0.15 12.0 12.0
mol color Name
mol material Glossy
mol addrep $molid

# RDG 等值面，用 sign(lambda2)rho 着色
# RDG 等值面值通常取 0.5
mol representation Isosurface 0.5 0 0 0 1 1
mol color Volume 0
mol material Glossy
mol addrep $molid

# 色标范围：-0.05 到 0.05（典型 NCI 范围）
mol scaleminmax $molid 1 -0.05 0.05
color scale method BWR

# 显示设置
color Display Background white
axes location Off
display projection Orthographic
display depthcue off
catch {display shadows on}
catch {display ambientocclusion on}

# 渲染
render TachyonInternal $output

quit
