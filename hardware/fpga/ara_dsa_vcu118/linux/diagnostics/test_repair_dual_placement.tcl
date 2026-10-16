set root [lindex $argv 0]
if {$root eq "" || [file exists $root]} {error "Supply a new test directory"}
set script [file join [file dirname [info script]] repair_dual_placement.tcl]
rename source original_source
proc source {args} {}
rename exit original_exit
proc exit {code} {return -code error -errorcode [list TEST_EXIT $code] "exit $code"}
foreach cmd {set_param open_checkpoint close_design report_timing_summary report_timing report_bus_skew report_drc} {
    proc $cmd {args} {}
}
proc dual_cdc_preflight {args} {if {$::scenario eq "cdc_fail"} {error "missing exception"}}
proc get_timing_paths {args} {return path}
proc get_property {key path} {return [expr {$key eq "SLACK" ? "-0.1" : "pin"}]}
proc phys_opt_design {args} {
    if {$args ne "-placement_opt"} {error "Unexpected optimization"}
    lappend ::calls optimize
    if {$::scenario eq "opt_fail"} {error "Optimization failed"}
}
proc write_checkpoint {args} {lappend ::calls checkpoint}
foreach scenario {healthy cdc_fail opt_fail} {
    set dir [file join $root $scenario]; file mkdir $dir
    set ::argv [list input.dcp tools $dir]; set calls {}
    catch {original_source $script} message options
    set expected [expr {$scenario ne "healthy"}]
    if {[dict get $options -errorcode] ne [list TEST_EXIT $expected]} {error "Unexpected $scenario: $options"}
    if {$scenario eq "cdc_fail" && "optimize" in $calls} {error "Modified invalid design"}
    if {$scenario eq "healthy" && $calls ne {optimize checkpoint}} {error "Wrong physical sequence"}
    puts "PASS $scenario"
}
