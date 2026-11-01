set rebuild_test_mode 1
source [file join [file dirname [info script]] .. ethernet rebuild_mainrtl_v3.tcl]
set design_top test_top
set calls {}
set missing_clock 0
foreach name {write_checkpoint report_timing_summary report_timing} {
    proc $name {args} {lappend ::calls [list [lindex [info level 0] 0] {*}$args]}
}
proc get_clocks {args} {
    if {$::missing_clock} {return {}}
    return [lindex $args end]
}
proc report_route_status {args} {
    lappend ::calls [list report_route_status {*}$args]
    if {[lindex $args 0] eq "-file"} {return}
    if {[lindex $args 1] eq "ROUTED_FULLY"} {return $::full}
    return $::errors
}
set root [lindex $argv 0]
if {$root eq "" || [file exists $root]} {error "Supply new output directory"}
foreach {full errors accepted} {1 0 1 0 0 0 1 1 0 invalid 0 0} {
    set calls {}
    set result [catch {rebuild_route_boundary $root case_${full}_${errors}} message]
    if {$result != !$accepted} {error "Incorrect route acceptance: $message"}
    if {[lindex [lindex $calls 0] 0] ne "write_checkpoint"} {error "Evidence must be saved first"}
    set scoped 0
    foreach call $calls {
        if {[lindex $call 0] eq "report_timing" && [lsearch -exact $call -from] >= 0} {incr scoped}
        if {[lindex $call 0] eq "report_route_status" && [lindex $call 1] eq "-boolean_check" && $scoped != 6} {
            error "Missing per-domain reports before route gate"
        }
    }
    if {$scoped != 6} {error "Expected three domains, max and min"}
}
set missing_clock 1
if {![catch {rebuild_domain_timing [file join $root missing]}]} {error "Missing Ara clock accepted"}
set body [info body rebuild_run]
set previous -1
foreach marker {
    {write_checkpoint [file join $out placed.dcp]}
    {rebuild_domain_timing [file join $out placed_domains]}
    {phys_opt_design -directive AggressiveFanoutOpt}
    {write_checkpoint [file join $out pre_route_fanout.dcp]}
    {rebuild_domain_timing [file join $out pre_route_domains]}
    {rebuild_stage $out incremental_routing}
    {rebuild_route_boundary $out first_route}
} {
    set position [string first $marker $body]
    if {$position <= $previous} {error "Incorrect/missing flow ordering: $marker"}
    set previous $position
}
puts "PASS: scoped evidence precedes strict route gates; pre-route fanout optimization is checkpointed"
