# Route the isolated loader after opt_design. Never generate a bitstream here.
proc route_loader {output {tag ""} {board_repo ""}} {
    if {[version -short] ne "2020.1"} { error "Expected Vivado 2020.1" }
    if {![regexp {^_[A-Za-z0-9_]+$|^$} $tag]} { error "Invalid output tag" }
    if {$board_repo ne ""} {
        if {![file isdirectory $board_repo]} { error "Missing board repository: $board_repo" }
        set_param board.repoPaths [list [file normalize $board_repo]]
    }
    set checkpoint [file join $output loader_opt${tag}.dcp]
    if {![file isfile $checkpoint]} { error "Missing reviewed opt checkpoint: $checkpoint" }
    set routed [file join $output loader_routed${tag}.dcp]
    if {[file exists $routed]} { error "Routed checkpoint already exists: $routed" }
    open_checkpoint $checkpoint
    place_design
    write_checkpoint [file join $output loader_placed${tag}.dcp]
    phys_opt_design
    route_design
    write_checkpoint $routed

    report_route_status -file [file join $output route_status${tag}.rpt]
    report_io -file [file join $output io_routed${tag}.rpt]
    report_clocks -file [file join $output clocks_routed${tag}.rpt]
    report_clock_interaction -file [file join $output clock_interaction_routed${tag}.rpt]
    report_utilization -file [file join $output utilization_routed${tag}.rpt]
    report_timing_summary -delay_type min_max -report_unconstrained \
        -file [file join $output timing_routed${tag}.rpt]
    report_bus_skew -delay_type min_max -sort_by_slack -warn_on_violation \
        -file [file join $output bus_skew_routed${tag}.rpt]
    check_timing -verbose -file [file join $output check_timing_routed${tag}.rpt]
    report_cdc -details -file [file join $output cdc_routed${tag}.rpt]
    report_drc -name loader_drc -file [file join $output drc_routed${tag}.rpt]

    set report [open [file join $output route_gate${tag}.txt] {WRONLY CREAT EXCL}]
    set bad [get_nets -hier -quiet -filter {
        ROUTE_STATUS == UNROUTED || ROUTE_STATUS == PARTIAL ||
        ROUTE_STATUS == CONFLICTS || ROUTE_STATUS == ANTENNAS ||
        ROUTE_STATUS == NODRIVER || ROUTE_STATUS == UNPLACED
    }]
    set errors [get_drc_violations -quiet -name loader_drc -filter {SEVERITY == Error}]
    puts $report "BAD_ROUTES [llength $bad]"
    puts $report "DRC_ERRORS [llength $errors]"
    set timing_ok 1
    foreach type {max min} {
        set paths [get_timing_paths -delay_type $type -max_paths 1]
        if {[llength $paths] != 1} {
            puts $report "TIMING_$type MISSING"
            set timing_ok 0
        } else {
            set slack [get_property SLACK $paths]
            puts $report "TIMING_$type SLACK=$slack"
            if {![string is double -strict $slack] || $slack < 0} {
                set timing_ok 0
            }
        }
    }
    if {![llength $bad] && ![llength $errors] && $timing_ok} {
        puts $report "AUTOMATED_ROUTE_GATES_PASS MANUAL_CDC_IO_REVIEW_REQUIRED"
    } else {
        puts $report "AUTOMATED_ROUTE_GATES_FAIL NO_BITSTREAM"
    }
    close $report
    close_design
    puts "LOADER_ROUTE_REPORTS $output"
    puts "NOT_BITGEN_NOT_PROGRAMMED"
}

if {[llength $argv] < 1 || [llength $argv] > 3} {
    error "Usage: loader_bd_route.tcl OUTPUT ?OUTPUT_TAG? ?BOARD_REPO?"
}
if {[catch {route_loader {*}$argv} message options]} {
    puts stderr [dict get $options -errorinfo]
    exit 1
}
exit 0
