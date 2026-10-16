# Standalone functional synthesis only, without board access or implementation.
if {[llength $argv] != 2} { error "Expected source-root new-output" }
lassign $argv root output
if {[file exists $output]} { error "Output already exists" }
file mkdir $output
create_project -in_memory -part xcvu9p-flga2104-2L-e
set_property include_dirs [list [file join $root hardware/deps/common_cells/include]] [current_fileset]
foreach source {
  hardware/deps/common_cells/src/cf_math_pkg.sv
  hardware/deps/axi/src/axi_pkg.sv
  hardware/deps/cva6/core/include/config_pkg.sv
  hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv
  hardware/deps/cva6/core/include/riscv_pkg.sv
  hardware/include/rvv_pkg.sv
  hardware/deps/fpnew/src/fpnew_pkg.sv
  hardware/include/ara_pkg.sv
  hardware/deps/common_cells/src/spill_register_flushable.sv
  hardware/deps/common_cells/src/spill_register.sv
  hardware/src/lane/fixed_p_rounding.sv
  hardware/src/lane/simd_alu.sv
  hardware/src/lane/valu.sv
  hardware/fpga/ara_dsa_vcu118/linux/diagnostics/valu_synth_top.sv
} { read_verilog -sv [file join $root $source] }
synth_design -top valu_synth_top -flatten_hierarchy none -mode out_of_context
write_checkpoint [file join $output valu.dcp]
write_verilog -mode funcsim -include_xilinx_libs [file join $output valu.v]
report_utilization -file [file join $output utilization.rpt]
