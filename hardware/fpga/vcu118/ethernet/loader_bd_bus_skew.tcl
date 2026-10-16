# Read-only review of the bus-skew constraints in a routed checkpoint.
if {[llength $argv] != 3} {
    error "Usage: loader_bd_bus_skew.tcl OUTPUT TAG BOARD_REPO"
}
lassign $argv output tag board_repo
if {![regexp {^_[A-Za-z0-9_]+$} $tag] || ![file isdirectory $board_repo]} {
    error "Invalid output tag or missing board repository"
}
if {[catch {
    set_param board.repoPaths [list [file normalize $board_repo]]
    open_checkpoint [file join $output loader_routed${tag}.dcp]
    report_bus_skew -delay_type min_max -sort_by_slack -warn_on_violation \
        -file [file join $output bus_skew_routed${tag}.rpt]
    close_design
    puts "BUS_SKEW_REVIEW_REPORT_WRITTEN_NOT_BITGEN_NOT_PROGRAMMED"
} message options]} {
    puts stderr [dict get $options -errorinfo]
    exit 1
}
exit 0
