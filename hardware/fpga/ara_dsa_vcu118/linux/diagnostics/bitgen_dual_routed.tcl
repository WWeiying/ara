# Reuse immutable routed evidence; this is a test artifact, not CDC signoff.
if {[catch {
    if {[llength $argv] != 4} {error "Expected package checkpoint output audit"}
    lassign $argv package checkpoint output audit
    set ::env(ARA_FPGA_PROFILE) dual_ddr_ethernet
    source [file join $package scripts common.tcl]
    if {[llength [fpga_checks::ddr_channels]] != 4} {error "Dual DDR audit coverage missing"}
    foreach {name command} {cdc.rpt cdc_failures bus_skew.rpt skew_failures} {
        set report [fpga_checks::read_report [file join $audit $name]]
        if {$command eq "skew_failures"} {
            set failures [fpga_checks::$command $report true]
        } else {
            set failures [fpga_checks::$command $report]
        }
        if {[llength $failures]} {error "$name failed: $failures"}
    }
    set_param general.maxThreads 8
    set_param board.repoPaths [linsert [get_param board.repoPaths] 0 [file join $package board_files]]
    set argv [list $checkpoint $output audited]
    source [file join $package scripts write_profile_bit.tcl]
} message]} {
    puts stderr $::errorInfo
    exit 1
}
exit 0
