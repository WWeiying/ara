set ::fanout_library_only true
source [file join [file dirname [info script]] optimize_dual_fanout.tcl]
set out [lindex $argv 0]
if {$out eq "" || [file exists $out]} {error "Expected new output"}
file mkdir $out
close [open [file join $out dual_cdc_preflight.tcl] w]
proc set_param {args} {}
proc open_checkpoint {args} {}
proc close_design {} {}
proc dual_cdc_preflight {args} {
    incr ::checks
    if {$::scenario eq "invalid"} {error "Invalid CDC exception"}
}
proc phys_opt_design {args} {
    if {$args ne {-directive AggressiveFanoutOpt}} {error "Unexpected optimization"}
    incr ::optimizations
}
foreach cmd {write_checkpoint report_timing_summary report_timing report_bus_skew report_drc} {
    proc $cmd {args} {}
}
proc route_design {args} {error "Routing forbidden"}
proc get_timing_paths {args} {return timing_path}
proc get_property {args} {return $::slack}
foreach scenario {negative positive invalid} {
    set slack [expr {$scenario eq "positive" ? 0.1 : -0.3}]
    set checks 0
    set optimizations 0
    set failed [catch {optimize_dual_fanout checkpoint $out $out} message]
    if {$scenario eq "invalid"} {
        if {!$failed || $optimizations!=0} {error "Invalid constraints allowed"}
    } else {
        if {$failed || $optimizations!=1 || $checks!=2} {error "Invalid flow: $message"}
        set f [open [file join $out stage.txt]]
        set stage [string trim [read $f]]
        close $f
        set expected [expr {$slack<0 ? "remaining_setup_violation_no_route" : "setup_nonnegative_pending_report_review_no_route"}]
        if {$stage ne $expected} {error "Wrong completion status"}
    }
    puts "PASS fanout $scenario"
}
