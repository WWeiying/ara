set script [file join [file dirname [info script]] trial_fifo_select_placement.tcl]
set root [lindex $argv 0]
if {$root eq "" || [file exists $root]} {error "Expected new output directory"}
file mkdir $root
proc set_param {args} {}
proc open_checkpoint {args} {}
proc close_design {} {}
proc get_cells {args} {
    set filter [lindex $args end]
    if {[string match {NAME == *} $filter]} {
        return "handle|[string range $filter 8 end]"
    }
    set cells {}
    for {set i 0} {$i<32} {incr i} {lappend cells handle|selector$i}
    return $cells
}
proc get_property {prop obj} {
    if {$obj ne "net" && ![string match {handle|*} $obj]} {error "Unresolved cell: $obj"}
    switch $prop {
        ASYNC_REG {return [expr {$::scenario eq "synchronizer"}]}
        DONT_TOUCH {return 1}
        NAME {return [lindex [split $obj |] end]}
        default {error "Unexpected property"}
    }
}
proc get_pins {args} {return Q}
proc get_nets {args} {return net}
proc set_property {prop value obj} {
    if {$prop ne "DONT_TOUCH" || $value ne "false"} {error "Unexpected change"}
    incr ::changes
}
proc phys_opt_design {args} {incr ::optimizations}
foreach cmd {write_checkpoint report_timing report_timing_summary report_bus_skew} {
    proc $cmd {args} {}
}
proc exit {code} {error "TEST_EXIT_$code"}
foreach scenario {healthy synchronizer} {
    set changes 0
    set optimizations 0
    set out [file join $root $scenario]
    file mkdir $out
    set argv [list checkpoint $out]
    catch {source $script} result
    if {$scenario eq "healthy"} {
        if {$result ne "TEST_EXIT_0" || $changes!=128 || $optimizations!=1} {error "Invalid healthy flow: $result"}
    } else {
        if {$result ne "TEST_EXIT_1" || $changes!=0 || $optimizations!=0} {error "Synchronizer was not protected"}
    }
    puts "PASS selectors $scenario"
}
