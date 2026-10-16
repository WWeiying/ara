# Import the checked BD into a fresh project, register OOC runs, export BSP metadata.
# Never launches synthesis, implementation or board commands.
if {[llength $argv] != 3} { error "Expected BD OUTPUT BOARD_REPO" }
lassign $argv input output boards
if {[version -short] ne "2020.1" || ![file isfile $input] || [file exists $output]} {
    error "Expected Vivado 2020.1, an existing BD and a new output directory"
}
set_param board.repoPaths [list [file normalize $boards]]
create_project eth_loader_bd [file join $output project] -part xcvu9p-flga2104-2L-e
set_property board_part xilinx.com:vcu118:part0:2.4 [current_project]
import_files -norecurse $input
set bd [get_files -quiet */loader_bd.bd]
if {[llength $bd] != 1} { error "Expected one imported BD" }
open_bd_design $bd
validate_bd_design
if {[llength [get_bd_cells -quiet -hier -filter {VLNV =~ xilinx.com:ip:ddr4:*}]]} {
    error "Imported loader contains a second MIG"
}
set_property synth_checkpoint_mode Singular $bd
generate_target all $bd
add_files -norecurse [make_wrapper -files $bd -top]
set_property top loader_bd_wrapper [current_fileset]
create_ip_run $bd
set run [get_runs -quiet loader_bd_synth_1]
if {[llength $run] != 1 || [get_property STATUS $run] ne "Not started"} {
    error "Unexpected BD synthesis run contract: $run"
}
write_hw_platform -fixed -file [file join $output loader_no_bitstream.xsa]
set report [open [file join $output import_check.txt] w]
puts $report "BD $bd"
puts $report "OOC_RUN $run STATUS [get_property STATUS $run]"
puts $report "CHECKPOINT_EXPECTED [file join [get_property DIRECTORY $run] loader_bd.dcp]"
puts $report "M_DDR [report_property -return_string [get_bd_intf_ports M_DDR]]"
close $report
close_project
puts "ARA_IMPORT_CHECK_PASSED_NO_SYNTHESIS_LAUNCHED $output"
exit 0
