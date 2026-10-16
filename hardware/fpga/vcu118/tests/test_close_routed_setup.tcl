# Offline control-flow test; it does not claim physical timing closure.
set here [file dirname [info script]]
set tool [file normalize [file join $here .. scripts close_routed_setup.tcl]]
set package [file normalize [file join $here ..]]
set root [file normalize [lindex $argv 0]]
if {$root eq "" || [file exists $root]} { error "Supply a new test directory" }
file mkdir $root

proc exit {code} {error "EXIT:$code"}
proc set_param {args} {}
proc open_checkpoint {path} {if {![file isfile $path]} { error "No checkpoint" }}
proc report_route_status {args} {
    if {[lindex $args 0] eq "-file"} {
        set f [open [lindex $args 1] w]
        puts $f "ROUTED_FULLY=1 ERRORS_IN_ROUTES=0"
        close $f
        return
    }
    return [expr {[lindex $args 1] eq "ROUTED_FULLY"}]
}
proc report_timing_summary {args} {
    set before [expr {[lsearch -exact $args -file] >= 0 &&
        [string match *before_timing.rpt [lindex $args [expr {[lsearch -exact $args -file] + 1}]]]}]
    set wns [expr {$before ? $::initial_wns : $::final_wns}]
    set failing [expr {$wns < 0 ? ($before ? $::initial_endpoints : 2) : 0}]
    set report "WNS(ns) TNS(ns) Failing Total WHS(ns) THS(ns) Failing Total WPWS(ns) TPWS(ns) Failing Total\n$wns 0 $failing 100 0.01 0 0 100 0.005 0 0 100\n"
    set f [open [lindex $args [expr {[lsearch -exact $args -file] + 1}]] w]
    puts $f $report
    close $f
    return $report
}
proc get_timing_paths {args} {return path}
proc phys_opt_design {args} {
    if {$args ne "-directive Explore"} { error "Unexpected optimizer settings" }
    incr ::opt_calls
}
proc write_checkpoint {path} {
    set f [open $path w]
    puts $f checkpoint
    close $f
}

foreach scenario {pass still_fails too_many} {
    set out [file join $root $scenario]
    file mkdir $out
    set checkpoint [file join $root $scenario.dcp]
    set f [open $checkpoint w]
    puts $f input
    close $f
    set argv [list $checkpoint $out $package]
    set opt_calls 0
    set initial_wns -0.014
    set initial_endpoints [expr {$scenario eq "too_many" ? 201 : 16}]
    set final_wns [expr {$scenario eq "pass" ? 0.006 : -0.003}]
    set caught [catch {source $tool} message]
    set expected [expr {$scenario eq "pass" ? 0 : 1}]
    if {!$caught || $message ne "EXIT:$expected"} {
        error "$scenario result=$message expected=EXIT:$expected"
    }
    if {$opt_calls != ($scenario eq "too_many" ? 0 : 1)} {error "$scenario optimizer calls=$opt_calls"}
    if {[file exists [file join $out ara_dsa_vcu118_routed.dcp]] != ($scenario eq "pass")} {
        error "$scenario output gate failed"
    }
}
puts "PASS: post-route closure control tests"
