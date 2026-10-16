# Reopen one routed checkpoint and optimize the measured small setup tail.
proc stage {dir name} {
    set f [open [file join $dir stage.txt] w]
    puts $f $name
    close $f
    puts "POSTROUTE_STAGE $name"
    flush stdout
}

proc require_route {dir} {
    report_route_status -file [file join $dir route_status.rpt]
    foreach check {ROUTED_FULLY ERRORS_IN_ROUTES} expected {1 0} {
        set actual [report_route_status -boolean_check $check]
        if {![string is boolean -strict $actual] || [expr {!!$actual}] != $expected} {
            error "Route integrity failed: $check=$actual"
        }
    }
}

proc initial_setup {dir} {
    set report [report_timing_summary -return_string -file [file join $dir before_timing.rpt]]
    set header false
    foreach line [split $report \n] {
        if {!$header} {
            if {[regexp {^\s*WNS\(ns\).*WHS\(ns\).*WPWS\(ns\)} $line]} { set header true }
            continue
        }
        set fields [regexp -all -inline {\S+} $line]
        if {[llength $fields] != 12 || ![string is double -strict [lindex $fields 0]]} { continue }
        set wns [lindex $fields 0]
        set failing [lindex $fields 2]
        if {$wns >= 0 || $wns < -0.2 || $failing < 1 || $failing > 200} {
            error "Checkpoint is not the reviewed small setup tail: WNS=$wns endpoints=$failing"
        }
        puts "BEFORE WNS=$wns SETUP_ENDPOINTS=$failing"
        return
    }
    error "Initial timing summary could not be parsed"
}

if {[catch {
    if {[llength $argv] != 3} { error "Expected checkpoint output package" }
    lassign $argv checkpoint out package
    if {![file isfile $checkpoint] || ![file isdirectory $out]} { error "Missing input or output" }
    source [file join $package scripts run_support.tcl]
    set_param general.maxThreads 8
    set_param board.repoPaths [linsert [get_param board.repoPaths] 0 [file join $package board_files]]
    if {[llength [get_board_parts -quiet xilinx.com:vcu118:part0:2.4]] != 1} {
        error "Frozen VCU118 board definition is unavailable"
    }
    set_msg_config -id {Board 49-67} -new_severity ERROR
    set_msg_config -id {Constraints 18-638} -new_severity ERROR
    stage $out opening
    open_checkpoint $checkpoint
    require_route $out
    initial_setup $out
    stage $out optimizing
    phys_opt_design -directive Explore
    if {![report_route_status -boolean_check ROUTED_FULLY]} {
        stage $out rerouting
        route_design
    }
    stage $out checking
    require_route $out
    fpga_run::require_timing $out
    set result [file join $out ara_dsa_vcu118_routed.dcp]
    if {[file exists $result]} { error "Refusing to replace existing checkpoint" }
    write_checkpoint $result
    fpga_run::nonempty $result
    stage $out timing_passed_needs_full_audit
} message]} {
    puts stderr $::errorInfo
    if {[llength $argv] == 3 && [file isdirectory [lindex $argv 1]]} {
        stage [lindex $argv 1] failed
    }
    exit 1
}
exit 0
