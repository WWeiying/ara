set ::locality_trial_library_only true
source [file join [file dirname [info script]] trial_dual_locality.tcl]
set out [lindex $argv 0]
if {$out eq "" || [file exists $out]} {error "Expected new output directory"}
file mkdir $out
foreach name {placed.dcp optimized.dcp dual_cdc_preflight.tcl} {
    close [open [file join $out $name] w]
}
proc set_param {args} {}
proc open_checkpoint {path} {lappend ::events open_[file tail $path]}
proc close_design {} {lappend ::events close}
proc dual_locality::plan {} {return {{example SLR1}}}
proc dual_locality::apply_plan {plan out} {lappend ::events apply}
proc dual_cdc_preflight {args} {
    lappend ::events exceptions
    if {$::scenario eq "bad_constraints"} {error "Missing CDC exception"}
}
proc place_design {args} {lappend ::events place}
proc write_checkpoint {args} {lappend ::events save}
foreach command {report_timing_summary report_timing report_utilization report_bus_skew} {
    proc $command {args} {lappend ::events report}
}
proc route_design {args} {error "Routing forbidden in placement trial"}
proc synth_design {args} {error "Synthesis forbidden in placement trial"}
foreach scenario {healthy bad_constraints} {
    set events {}
    set failed [catch {locality_trial [file join $out placed.dcp] \
        [file join $out optimized.dcp] $out $out} message]
    if {$scenario eq "healthy"} {
        if {$failed} {error $message}
        if {[lrange $events 0 6] ne {open_placed.dcp close open_optimized.dcp exceptions apply report place}} {
            error "Invalid experiment ordering: $events"
        }
        if {[lsearch -exact $events save]<0} {error "Missing trial checkpoint"}
    } else {
        if {!$failed || "apply" in $events || "place" in $events} {error "Failed to stop before placement"}
    }
    puts "PASS trial $scenario"
}
