if {[llength $argv] != 2} { error "Expected source-root new-output" }
lassign $argv root output
if {[file exists $output]} { error "Output already exists" }
file mkdir $output
create_project -in_memory -part xcvu9p-flga2104-2L-e
set common [file join $root hardware/fpga/ara_dsa_vcu118/rtl/common_cells]
set_property include_dirs [list [file join $common include]] [current_fileset]
set_property verilog_define {COMMON_CELLS_ASSERTS_OFF} [current_fileset]
foreach source {cf_math_pkg.sv onehot_to_bin.sv lzc.sv id_queue.sv} {
  read_verilog -sv [file join $common src $source]
}
read_verilog -sv [file join $root hardware/fpga/ara_dsa_vcu118/linux/diagnostics/id_queue_probe.sv]
synth_design -top id_queue_probe -flatten_hierarchy none -mode out_of_context
write_checkpoint [file join $output id_queue.dcp]
write_verilog -mode funcsim -include_xilinx_libs [file join $output id_queue.v]
