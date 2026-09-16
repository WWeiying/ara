# Exercise the real full-design gate with Vivado command substitutes.
set package [file normalize [lindex $argv 0]]
set directory [file normalize [lindex $argv 1]]
if {[llength [info commands try]]} { rename try {} }
source [file join $package scripts common.tcl]
proc assert {condition message} {
    if {![uplevel 1 [list expr $condition]]} { error "ASSERT: $message" }
}
proc report_drc {args} {
    assert {$args eq [list -checks MDRV-1 -name ara_drivers -force -file \
        [file join $::directory $::scenario multiple_drivers.rpt]]} "exact driver report"
    if {$::scenario eq "report_error"} { error "injected report error" }
    set ::reported 1
}
proc get_drc_violations {args} {
    assert {$::reported} "query only after a successful report"
    assert {$args eq {-name ara_drivers MDRV*}} "query the named driver report"
    if {$::scenario eq "query_error"} { error "injected query error" }
    if {$::scenario eq "violation"} { return {MDRV-1#1} }
    return {}
}
foreach scenario {healthy violation report_error query_error} {
    set reported 0
    set code [catch {require_no_multiple_drivers [file join $directory $scenario]} message]
    assert {$code == ($scenario ne "healthy")} "$scenario must fail closed: $message"
    switch $scenario {
        violation { assert {[string match {Multiple drivers remain;*} $message]} "driver finding preserved" }
        report_error { assert {$message eq "injected report error"} "report error propagated" }
        query_error { assert {$message eq "injected query error"} "query error propagated" }
    }
    puts "PASS driver gate $scenario"
}
proc set_msg_config {args} { lappend ::messages $args }
set messages {}
source [file join $package scripts synth_pre.tcl]
assert {$messages eq {{-id {Synth 8-6858} -new_severity ERROR} {-id {Synth 8-6859} -new_severity ERROR}}} \
    "the synthesis worker must reject constant-driver substitution"
puts "PASS driver gate synthesis hook"
