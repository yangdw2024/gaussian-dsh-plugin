# orbital.tcl — 渲染分子轨道等值面
# 用法：vmd -dispdev text -e orbital.tcl -args orbital.cub output.tga isovalue
# argv:
#   0: orbital cube 文件路径
#   1: 输出 TGA 文件路径
#   2: 等值面值（如 0.02）

if {[llength $argv] < 3} {
    puts stderr "usage: orbital.tcl orbital.cub output.tga isovalue"
    exit 2
}

set cube   [lindex $argv 0]
set output [lindex $argv 1]
set iso    [expr {abs(double([lindex $argv 2]))}]
set negiso [expr {-$iso}]

set molid [mol new $cube type cube waitfor all]

# 删除 VMD 默认表示
mol delrep 0 $molid

# 分子骨架（Licorice）
mol representation Licorice 0.18 12.0 12.0
mol color Name
mol material Glossy
mol addrep $molid

# 正相位轨道（蓝色）
mol representation Isosurface $iso 0 0 0 1 1
mol color ColorID 0
mol material Glossy
mol addrep $molid

# 负相位轨道（红色）
mol representation Isosurface $negiso 0 0 0 1 1
mol color ColorID 1
mol material Glossy
mol addrep $molid

# 显示设置
color Display Background white
axes location Off
display projection Orthographic
display depthcue off
catch {display shadows on}
catch {display ambientocclusion on}

# 渲染（TachyonInternal 软件渲染，无 GUI）
render TachyonInternal $output

quit
