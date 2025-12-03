### area ##
set all_cells [dbGet top.insts.name * -p]
set all_cells_area 0
foreach cell $all_cells {
set cell_area [dbGet ${cell}.area]
set all_cells_area [expr $all_cells_area+$cell_area]
}
echo "The total area of all cells is $all_cells_area um^2."

set all_macros [dbGet top.insts.cell.subclass block -p2]
set all_macros_area 0
foreach macrocell $all_macros {
set macro_area [dbGet ${macrocell}.area]
set all_macros_area [expr $all_macros_area+$macro_area]
}
echo "The total area of all macro cells is $all_macros_area um^2."

set all_stdcells_area [expr $all_cells_area - $all_macros_area]
echo "The total area of all std cells is $all_stdcells_area um^2."

set total_estimate_area [expr $all_stdcells_area / 0.65 + $all_macros_area / 0.82]
echo "The estimated area is $total_estimate_area um^2."
