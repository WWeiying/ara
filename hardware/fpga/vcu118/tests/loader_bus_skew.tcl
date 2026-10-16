# Routed DDR bus-skew review; read-only and independent of bitstream generation.
if {[llength $argv] != 3} {
    error "Usage: loader_bus_skew.tcl ROUTED_DCP BOARD_REPO REPORT"
}
lassign $argv checkpoint board_repo report
if {[version -short] ne "2020.1"} { error "Expected Vivado 2020.1" }
if {![file isfile $checkpoint] || ![file isdirectory $board_repo] ||
    [file exists $report]} { error "Missing input or report already exists" }
set_param board.repoPaths [list [file normalize $board_repo]]
open_checkpoint $checkpoint
report_bus_skew -file $report
close_design
puts "BUS_SKEW_REPORT $report"
exit 0
