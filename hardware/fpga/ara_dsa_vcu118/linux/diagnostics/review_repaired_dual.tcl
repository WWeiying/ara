# Read-only comparison of C2's remaining estimates against C1 in the same netlist.
if {[catch {
    if {[llength $argv] != 4} {error "Expected package output token timing_report"}
    lassign $argv package out token timing
    if {[file exists $out] || ![regexp {^[a-f0-9]{12}$} $token]} {error "New output/token required"}
    file mkdir $out
    source [file join $package scripts common.tcl]
    source [file join $package scripts run_support.tcl]
    set_param general.maxThreads 4
    open_package_project
    set name synth_$token
    if {[get_property STATUS [get_runs $name]] ne "synth_design Complete!"} {error "Synthesis incomplete"}
    open_run $name
    set f [open [file join $out clocks.tsv] w]
    puts $f "clock\tsource\tperiod"
    foreach clock [get_clocks] {
        foreach pin [get_property SOURCE_PINS $clock] {
            puts $f "[get_property NAME $clock]\t$pin\t[get_property PERIOD $clock]"
        }
    }
    close $f
    set f [open [file join $out pins.tsv] w]
    puts $f "port\tpin\tbank"
    foreach port {sys_clk_p sys_clk_n c2_sys_clk_p c2_sys_clk_n} {
        set pin [get_property PACKAGE_PIN [get_ports $port]]
        puts $f "$port\t$pin\t[get_property BANK [get_package_pins $pin]]"
    }
    close $f
    set f [open [file join $out paths.tsv] w]
    puts $f "from\tto\tslack\tsource\tdestination"
    foreach from {c2_sys_clk sys_clk mmcm_clkout0 mmcm_clkout0_1} \
            to {c2_sys_clk sys_clk mmcm_clkout6 mmcm_clkout6_1} expected {16 16 1 1} {
        set paths [get_timing_paths -delay_type min -from [get_clocks $from] -to [get_clocks $to] \
            -slack_lesser_than 0 -nworst 1 -max_paths 1000]
        if {[llength $paths] != $expected} {error "Changed endpoint count: $from -> $to"}
        foreach path $paths {
            puts $f "$from\t$to\t[get_property SLACK $path]\t[get_property STARTPOINT_PIN $path]\t[get_property ENDPOINT_PIN $path]"
        }
        report_timing -delay_type min -from [get_clocks $from] -to [get_clocks $to] \
            -slack_lesser_than 0 -nworst 1 -max_paths 1000 -path_type full_clock_expanded \
            -file [file join $out ${from}_to_${to}.rpt]
    }
    close $f
    # Representative paths for every remaining hold group; summary keeps counts.
    report_timing_summary -report_unconstrained -file [file join $out timing.rpt]
    set f [open [file join $out completed.txt] {WRONLY CREAT EXCL}]
    puts $f $token
    close $f
    close_project
} message]} {
    puts stderr $::errorInfo
    exit 1
}
exit 0
