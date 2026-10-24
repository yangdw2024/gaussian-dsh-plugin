# esp_surface.tcl — 电子密度表面映射静电势
# 用法：vmd -dispdev text -e esp_surface.tcl -args density.cub esp.cub output.tga rhoiso vmin vmax
# argv:
#   0: 电子密度 cube 文件
#   1: ESP cube 文件
#   2: 输出 TGA 文件
#   3: 密度等值面值（如 0.001）
#   4: ESP 色标最小值（如 -0.05）
#   5: ESP 色标最大值（如 0.05）

if {[llength $argv] < 6} {
    puts stderr "usage: esp_surface.tcl density.cub esp.cub output.tga rhoiso vmin vmax"
    exit 2
}

set density [lindex $argv 0]
set esp     [lindex $argv 1]
set output  [lindex $argv 2]
set rhoiso  [expr {abs(double([lindex $argv 3]))}]
set vmin    [expr {double([lindex $argv 4])}]
set vmax    [expr {double([lindex $argv 5])}]

if {$vmin >= $vmax} {
    puts stderr "vmin must be smaller than vmax"
    exit 2
}

# Dataset 0 = 电子密度
set molid [mol new $density type cube waitfor all]

# Dataset 1 = ESP（必须在同一个 molecule 中）
mol addfile $esp type cube waitfor all $molid

# 删除默认表示
mol delrep 0 $molid

# 分子骨架
mol representation Licorice 0.15 12.0 12.0
mol color Name
mol material Glossy
mol addrep $molid

# 密度等值面，用 ESP dataset #1 着色
mol representation Isosurface $rhoiso 0 0 0 1 1
mol color Volume 1
mol material Glossy
mol addrep $molid

# 固定色标范围
# rep 0 = Licorice, rep 1 = ESP-colored surface
set surface_rep 1
mol scaleminmax $molid $surface_rep $vmin $vmax

# 色标：红-白-蓝（RWB）
color scale method RWB

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
