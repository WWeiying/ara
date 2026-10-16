# Standalone functional synthesis. No board access or changes to the Ara build.
if {[llength $argv] ni {2 3}} { error "Expected source-root new-output ?vldu|sldu?" }
lassign $argv root output probe
if {$probe eq ""} { set probe vldu }
if {$probe ni {vldu sldu}} { error "Unknown probe" }
if {[file exists $output]} { error "Output already exists" }
file mkdir $output
create_project -in_memory -part xcvu9p-flga2104-2L-e
set_property include_dirs [list [file join $root hardware/deps/common_cells/include] [file join $root hardware/include]] [current_fileset]
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
} { read_verilog -sv [file join $root $source] }
if {$probe eq "vldu"} {
  read_verilog -sv [file join $root hardware/src/vlsu/vldu.sv]
} else {
  foreach source {lzc.sv popcount.sv} {
    read_verilog -sv [file join $root hardware/deps/common_cells/src $source]
  }
  foreach source {p2_stride_gen.sv sldu_op_dp.sv sldu.sv} {
    read_verilog -sv [file join $root hardware/src/sldu $source]
  }
}
read_verilog -sv [file join $root hardware/fpga/ara_dsa_vcu118/linux/diagnostics/${probe}_queue_probe.sv]
synth_design -top ${probe}_queue_probe -flatten_hierarchy none -mode out_of_context
write_checkpoint [file join $output $probe.dcp]
write_verilog -mode funcsim -include_xilinx_libs [file join $output $probe.v]
report_utilization -file [file join $output utilization.rpt]
