# Control-flow tests only; native Vivado is required for actual checkpoint checks.
if {[llength [info commands try]]} { rename try {} }
source [file join [file dirname [info script]] .. scripts common.tcl]
source [file join [file dirname [info script]] .. scripts audit_support.tcl]
if {[llength $argv] != 1 || [file exists [lindex $argv 0]]} {
    error "Pass a new temporary directory"
}
set sandbox [file normalize [lindex $argv 0]]
file mkdir $sandbox
proc assert {condition message} {
    if {![uplevel 1 [list expr $condition]]} { error "ASSERT: $message" }
}
proc put {path text} {
    file mkdir [file dirname $path]
    set out [open $path w]; puts -nonewline $out $text; close $out
}
proc current_project {args} { return $::project }
proc open_checkpoint {path} {
    assert {$path eq $::checkpoint} "open only the specified old checkpoint"
    incr ::opened
    set ::project archived
    if {$::scenario eq "open_error"} { error "checkpoint unreadable" }
}
proc close_project {} {
    incr ::closed
    set ::project {}
    if {$::scenario eq "close_error"} { error "close failed" }
}
foreach forbidden {create_project open_project open_run open_package_project
    configure_package_constraints read_xdc read_verilog read_vhdl read_checkpoint
    synth_design opt_design place_design phys_opt_design route_design launch_runs
    reset_run reset_target set_property write_checkpoint write_bitstream} {
    proc $forbidden {args} { error "Forbidden mutation in checkpoint audit: [lindex [info level 0] 0]" }
}
proc report_route_status {args} {
    if {[lindex $args 0] eq "-file"} { put [lindex $args 1] "route evidence"; return }
    assert {[lindex $args 0] eq "-boolean_check"} "use native boolean route status"
    set check [lindex $args 1]
    if {$::scenario eq "route_query_error"} { error "route status query failed" }
    if {$::scenario eq "route_empty"} { return {} }
    if {$::scenario eq "route_invalid"} { return unknown }
    if {$check eq "ERRORS_IN_ROUTES"} { return [expr {$::scenario eq "route_errors"}] }
    assert {$check eq "ROUTED_FULLY"} "do not mistake has_routing for full routing"
    if {$::scenario eq "boolean_words"} { return TRUE }
    return [expr {$::scenario ne "unrouted"}]
}
proc require_no_multiple_drivers {dir} {
    incr ::driver_checks
    if {$::scenario eq "drivers"} { error "Multiple drivers remain" }
}
proc write_reports {name routed} {
    assert {$name eq "audit_012345abcdef" && $routed} "run full routed boundary checks, not inspect mode"
    incr ::reports
    put [file join $::package_root reports $name boundary_checks.rpt] "boundary evidence"
    if {$::scenario eq "boundary_error"} { error "Physical boundary checks failed" }
}
proc get_timing_paths {args} {
    assert {[lindex $args 0] eq "-delay_type" && [lrange $args 2 end] eq {-max_paths 1}} "worst path query"
    set kind [lindex $args 1]
    lappend ::timed $kind
    if {$::scenario eq "${kind}_missing"} { return {} }
    if {$::scenario eq "${kind}_multiple"} { return {path1 path2} }
    return $kind
}
proc get_property {property path} {
    assert {$property eq "SLACK"} "only slack queried"
    if {$::scenario eq "${path}_negative"} { return -0.001 }
    if {$::scenario eq "${path}_empty"} { return {} }
    if {$::scenario eq "${path}_inf"} { return inf }
    if {$::scenario eq "${path}_nan"} { return NaN }
    if {$::scenario eq "scientific"} { return 2.3e-2 }
    return 0.01
}
set scenarios {healthy boolean_words scientific bad_token missing_dcp empty_dcp wrong_extension
    missing_session existing_project existing_reports existing_marker open_error close_error
    route_query_error route_empty route_invalid unrouted route_errors drivers boundary_error}
foreach kind {max min} {
    foreach fault {missing multiple negative empty inf nan} { lappend scenarios ${kind}_$fault }
}
foreach scenario $scenarios {
    set package_root [file join $sandbox $scenario]
    set session [file join $package_root session]
    set checkpoint [file join $package_root old old_routed.dcp]
    set marker [file join $session completed_audit.txt]
    set token 012345abcdef
    set project {}; set opened 0; set closed 0; set reports 0; set driver_checks 0; set timed {}
    file mkdir $session
    put $checkpoint "old checkpoint"
    put [file join $package_root reports impl_old boundary_checks.rpt] "old report"
    put [file join $package_root build managed latest_synth.json] "old synthesis"
    switch -- $scenario {
        bad_token { set token ../impl_old }
        missing_dcp { file delete $checkpoint }
        empty_dcp { put $checkpoint {} }
        wrong_extension { file rename $checkpoint $checkpoint.txt; append checkpoint .txt }
        missing_session { file delete $session }
        existing_project { set project user_project }
        existing_reports { file mkdir [file join $package_root reports audit_$token] }
        existing_marker { put $marker "old marker" }
    }
    set channels [lsort [chan names]]
    set failed [catch {fpga_audit::execute $checkpoint $session $token} message]
    set success [expr {$scenario in {healthy boolean_words scientific}}]
    assert {$failed != $success} "$scenario unexpected result: $message"
    assert {[lsort [chan names]] eq $channels} "no leaked report handles"
    assert {$opened == $closed} "close the opened design even after failures"
    assert {[file exists $marker] == ($success || $scenario eq "existing_marker")} "no success marker after failures"
    if {$success} {
        assert {$reports == 1 && $driver_checks == 1 && $timed eq {max min}} "all gates executed exactly once"
        assert {[string trim [fpga_checks::read_report $marker]] eq "audit_$token"} "correct completion record"
    }
    if {$scenario eq "existing_project"} { assert {$project eq "user_project"} "do not close another project" }
    if {$scenario eq "existing_marker"} { assert {[fpga_checks::read_report $marker] eq "old marker"} "preserve old marker" }
    if {$scenario ni {missing_dcp empty_dcp}} {
        assert {[fpga_checks::read_report $checkpoint] eq "old checkpoint"} "old DCP unchanged"
    }
    assert {[fpga_checks::read_report [file join $package_root reports impl_old boundary_checks.rpt]] eq "old report"} "old report unchanged"
    assert {[fpga_checks::read_report [file join $package_root build managed latest_synth.json]] eq "old synthesis"} "synth parent unchanged"
    assert {![file exists [file join $session completed_flow.json]]} "do not claim full flow completion"
    puts "PASS audit $scenario"
}
puts "PASS: [llength $scenarios] checkpoint audit scenarios"
