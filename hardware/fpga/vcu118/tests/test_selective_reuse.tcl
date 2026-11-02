set ::selective_reuse_test_mode true
source [file join [file dirname [info script]] .. ethernet rebuild_selective_reuse.tcl]
proc check {condition message} {
    if {![uplevel 1 [list expr $condition]]} {error $message}
}
check {[selective_reuse::roots] eq {i_dram_wrapper gen_ddr2.i_dram_wrapper_c2}} "Compute hierarchy must not be reused"
set ::calls {}
proc write_checkpoint {path} {lappend ::calls checkpoint}
proc report_route_status {args} {
    if {[lindex $args 0] eq "-file"} {lappend ::calls report; return}
    return [dict get $::route [lindex $args 1]]
}
foreach {full errors expected} {1 0 0 0 0 1 1 1 1 0 1 1 invalid 0 1 1 invalid 1} {
    set ::calls {}
    set ::route [dict create ROUTED_FULLY $full ERRORS_IN_ROUTES $errors]
    set failed [catch {selective_reuse::check_route unused test}]
    check {$failed == $expected} "Route gate incorrectly accepted/rejected $full/$errors"
    if {$expected} {
        check {$::calls eq {checkpoint report}} "Failure checkpoint must precede reporting"
    } else {
        check {$::calls eq {report}} "Valid route should not write redundant checkpoint"
    }
}
check {[catch {selective_reuse::run synth unused unused a101ed39f750 unused unused}]} "Must not resynthesize"
# Exercise the full driver with a mocked Vivado API, not only text matching.
set temp [file normalize [file join [pwd] selective_test_[pid]]]
file mkdir $temp
set f [open [file join $temp accepted_opt.txt] w]
puts $f accepted_current_opt.dcp
close $f
rename source saved_source
proc source {args} {}
namespace eval fpga_run {}
proc fpga_run::nonempty {path} {}
proc fpga_run::require_timing {path} {lappend ::flow timing_gate}
proc rebuild_stage {out stage} {lappend ::flow $stage}
proc rebuild_domain_timing {args} {}
proc set_param {args} {}
proc get_param {args} {return {}}
proc open_checkpoint {path} {lappend ::flow open_current}
proc current_design {} {return design}
proc get_property {property object} {
    if {$property eq "PART"} {return $::test_part}
    if {$property eq "REF_NAME"} {return BUFGCE}
    if {$property eq "IS_LOC_FIXED"} {return false}
    if {$property in {LOC BEL}} {
        if {[info exists ::props($object,$property)]} {return $::props($object,$property)}
        if {$property eq "BEL"} {return BUFCE}
        if {[string match gen_ddr2* $object]} {return BUFGCE_X0Y12}
        return BUFGCE_X0Y120
    }
    return design_container_not_rtl_top
}
proc set_property {property value object} {set ::props($object,$property) $value}
proc get_cells {args} {
    if {[lsearch -exact $args -filter] >= 0} {return [lindex [lindex $args end] 2]}
    return [lindex $args end]
}
proc read_checkpoint {args} {
    check {$args eq {-incremental reference.dcp -reuse_objects {i_dram_wrapper gen_ddr2.i_dram_wrapper_c2}}} "Unexpected reuse scope"
    lappend ::flow selective_reference
}
proc report_incremental_reuse {args} {}
proc place_design {} {lappend ::flow place}
proc phys_opt_design {args} {lappend ::flow physopt}
proc route_design {} {lappend ::flow route}
proc close_design {} {lappend ::flow closed}
set ::design_top ara_dsa_vcu118
set ::max_threads 8
set ::test_part xcvu9p-flga2104-2L-e
try {
    foreach bad {0 1} {
        set ::flow {}
        set ::route [dict create ROUTED_FULLY [expr {!$bad}] ERRORS_IN_ROUTES $bad]
        set failed [catch {selective_reuse::run impl_existing package $temp a101ed39f750 reference.dcp $temp}]
        check {$failed == $bad} "Incorrect full-driver outcome"
        check {[lsearch -exact $::flow open_current] < [lsearch -exact $::flow selective_reference]} "Must open current netlist before reference"
        check {[lsearch -exact $::flow route] >= 0} "Route not executed"
        check {[lsearch -exact $::flow restore_ddr_clock_anchors] < [lsearch -exact $::flow place]} "DDR clock anchors must precede placement"
        if {$bad} {
            check {[lsearch -exact $::flow timing_gate] < 0} "Illegal route escaped gate"
            check {[lsearch -exact $::flow post_route_physical_optimization] < 0} "Illegal route caused another pass"
        } else {
            check {[lindex $::flow end] eq "closed"} "Successful driver did not finish"
            check {[lsearch -exact $::flow timing_gate] > [lsearch -exact $::flow route]} "Timing gate must follow route"
        }
    }
    set ::test_part wrong_device
    set ::flow {}
    check {[catch {selective_reuse::run impl_existing package $temp a101ed39f750 reference.dcp $temp}]} "Wrong device accepted"
    check {[lsearch -exact $::flow selective_reference] < 0} "Wrong device reached reference reuse"
} finally {
    file delete -force $temp
}
puts "PASS: infrastructure selection, six route gates, and two full-driver cases (mock Vivado)"
