# Restricted VMUL queue probe, no board connection or full-design changes.
if {[llength $argv] != 2} { error "Expected source-root new-output" }
lassign $argv root output
if {[file exists $output]} { error "Output already exists" }
file mkdir $output
create_project -in_memory -part xcvu9p-flga2104-2L-e
set r [file join $root hardware/fpga/ara_dsa_vcu118/rtl]
set_property include_dirs [list [file join $r common_cells/include] \
  [file join $r ara/hardware/include]] [current_fileset]
foreach source {
  common_cells/src/cf_math_pkg.sv axi/src/axi_pkg.sv
  cva6/core/include/config_pkg.sv cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv
  cva6/core/include/riscv_pkg.sv ara/hardware/include/rvv_pkg.sv
  fpnew/src/fpnew_pkg.sv ara/hardware/include/ara_pkg.sv cva6/core/include/ariane_pkg.sv
  cva6/core/include/build_config_pkg.sv
  common_cells/src/spill_register_flushable.sv common_cells/src/spill_register.sv
  tech_cells_generic/src/fpga/tc_clk_xilinx.sv
  common_cells/src/lzc.sv cva6/core/serdiv.sv
  ara/hardware/src/lane/power_gating_generic.sv ara/hardware/src/lane/simd_mul.sv
  ara/hardware/src/lane/simd_div.sv ara/hardware/src/lane/vmfpu.sv
} { read_verilog -sv [file join $r $source] }
set p [file join $root hardware/fpga/ara_dsa_vcu118]
source [file join $p scripts sources.tcl]
foreach source $rtl_files {
  if {(([string match rtl/fpnew/* $source] || [string match rtl/fpu_div_sqrt_mvp/* $source]) &&
       ![string match *fpnew_pkg.sv $source]) ||
       $source in {rtl/common_cells/src/rr_arb_tree.sv rtl/common_cells/src/fifo_v3.sv}} {
    read_verilog -sv [file join $p $source]
  }
}
read_verilog -sv [file join $p linux/diagnostics/mfpu_queue_probe.sv]
# Queue-mapping experiment, not a DSP implementation-equivalence claim.
synth_design -top mfpu_queue_probe -flatten_hierarchy rebuilt -mode out_of_context -max_dsp 0
write_checkpoint [file join $output mfpu.dcp]
write_verilog -mode funcsim -include_xilinx_libs [file join $output mfpu.v]
report_utilization -file [file join $output utilization.rpt]
