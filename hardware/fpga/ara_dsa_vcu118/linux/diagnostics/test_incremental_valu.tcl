set valu_incremental_test_mode 1
source [file join [file dirname [info script]] run_incremental_valu.tcl]
set root [lindex $argv 0]
if {$root eq "" || [file exists $root]} {error "Supply a new test directory"}
file mkdir $root
foreach name {new_opt old_reference} {
    set f [open [file join $root $name] w]; puts $f checkpoint; close $f
}
rename source original_source
proc source {path} {}
proc record {name args} {lappend ::calls [linsert $args 0 $name]}
proc set_param {args} {}
proc open_checkpoint {path} {record open $path}
proc read_checkpoint {args} {record reuse {*}$args}
proc report_incremental_reuse {args} {}
proc place_design {} {record place}
proc route_design {} {record route}
proc write_checkpoint {path} {record checkpoint $path}
proc close_design {} {record close}
proc require_no_multiple_drivers {dir} {}
proc write_reports {dir reject} {record reports $reject}
proc report_route_status {args} {
    if {[lindex $args 0] eq "-boolean_check"} {
        if {[lindex $args 1] eq "ROUTED_FULLY"} {return [expr {$::scenario ne "route_fail"}]}
        return 0
    }
}
namespace eval fpga_run {}
proc fpga_run::require_timing {dir} {
    record timing
    if {$::scenario eq "timing_fail"} {error "Timing gate failed"}
}
foreach scenario {pass route_fail timing_fail} {
    set calls {}
    set out [file join $root $scenario]; file mkdir $out
    set code [catch {valu_incremental::run [file join $root new_opt] \
        [file join $root old_reference] package $out} message]
    if {$code != ($scenario ne "pass")} {error "Unexpected result $scenario: $message"}
    if {[lindex $calls 0] ne [list open [file join $root new_opt]] ||
        [lindex $calls 1] ne [list reuse -incremental [file join $root old_reference]]} {
        error "Wrong reference/current ordering"
    }
    if {[lsearch -exact $calls [list checkpoint [file join $out routed.dcp]]] < 0} {
        error "Result not preserved before gate"
    }
    set f [open [file join $out stage.txt]]; set stage [string trim [read $f]]; close $f
    if {($stage eq "timing_passed_requires_full_audit") != ($scenario eq "pass")} {
        error "False pass state: $scenario"
    }
}
puts "PASS: three scenarios, current netlist preserved, failing gates reject result"
