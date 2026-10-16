if {[llength $argv] != 2} { error "Expected source-root new-output" }
lassign $argv root output
if {[file exists $output]} { error "Output already exists" }
file mkdir $output
create_project -in_memory -part xcvu9p-flga2104-2L-e
set r [file join $root hardware/fpga/ara_dsa_vcu118/rtl]
set_property include_dirs [list [file join $r common_cells/include] [file join $r ara/hardware/include]] [current_fileset]
foreach source {
 common_cells/src/cf_math_pkg.sv axi/src/axi_pkg.sv
 cva6/core/include/config_pkg.sv cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv
 cva6/core/include/riscv_pkg.sv ara/hardware/include/rvv_pkg.sv
 fpnew/src/fpnew_pkg.sv ara/hardware/include/ara_pkg.sv
 cva6/core/include/ariane_pkg.sv cva6/core/lsu_bypass.sv
} { read_verilog -sv [file join $r $source] }
read_verilog -sv [file join $root hardware/fpga/ara_dsa_vcu118/linux/diagnostics/lsu_bypass_probe.sv]
synth_design -top lsu_bypass_probe -mode out_of_context -flatten_hierarchy rebuilt
write_verilog -mode funcsim -include_xilinx_libs [file join $output lsu_bypass.v]
