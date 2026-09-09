source [file join [file dirname [info script]] common.tcl]
require_vivado
if {[current_project -quiet] ne ""} { error "Close the current project first." }
if {[file exists $xpr_path]} {
    error "Project already exists: $xpr_path. Open it; do not recreate over existing runs."
}
set_param general.maxThreads $max_threads
set repos [get_param board.repoPaths]
set_param board.repoPaths [linsert $repos 0 [file join $package_root board_files]]
if {![llength [get_parts -quiet $fpga_part]]} {
    error "Install Vivado support for Virtex UltraScale+ ($fpga_part)."
}
if {![llength [get_board_parts -quiet $board_part]]} {
    error "VCU118 board definition was not found under package board_files."
}
source [file join $package_root scripts sources.tcl]
foreach path [concat $rtl_files $rtl_include_dirs] {
    if {![file exists [file join $package_root $path]]} { error "Missing package file: $path" }
}
create_project $project_name $build_dir -part $fpga_part
set_property board_part $board_part [current_project]
set_property target_language Verilog [current_project]
set_property simulator_language Mixed [current_project]
set_property XPM_LIBRARIES {XPM_MEMORY} [current_project]
set_property source_mgmt_mode None [current_project]
set abs_includes [list]
foreach path $rtl_include_dirs { lappend abs_includes [file join $package_root $path] }
set_property include_dirs $abs_includes [current_fileset]
set_property verilog_define $rtl_defines [current_fileset]
foreach path $rtl_files { add_files -norecurse [file join $package_root $path] }
set_property top ara_dsa_vcu118 [current_fileset]
set_property STEPS.SYNTH_DESIGN.ARGS.FLATTEN_HIERARCHY none [get_runs synth_1]
source [file join $package_root scripts create_ip.tcl]
add_files -fileset constrs_1 -norecurse [file join $package_root constraints board.xdc]
add_files -fileset constrs_1 -norecurse [file join $package_root constraints timing.xdc]
set cdc [file join $package_root constraints cdc.xdc]
add_files -fileset constrs_1 -norecurse $cdc
set_property USED_IN_SYNTHESIS false [get_files $cdc]
set_property PROCESSING_ORDER LATE [get_files $cdc]
file mkdir [file join $package_root reports]
report_ip_status -file [file join $package_root reports ip_status.rpt]
puts "Created: $xpr_path"
puts "No synthesis was launched. Next: source scripts/synth.tcl"
