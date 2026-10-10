source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/fsm741_transition_batch.tcl}
# Selected query reports a display projection, not direct native membership.
# All direct target identities are independently checked in BOTH saved ELs.
proc fx_audit {stage expected} {
    global fx_groups fx_stream
    set mismatches {}
    foreach group $fx_groups {
        fx_context $group
        foreach name [lindex $group 4] {
            fs_select $name
            set actual [gui_exclusion -id CovDetail.1 -list {fsm list} -excluded -selected]
            set target [expr {[lsearch -exact [lindex $group 5] $name] >= 0}]
            set want 0
            if {$expected && [lindex $group 3] eq "State"} {set want INHERITED_OBSERVATION}
            if {$expected && $target} {set want NATIVE_EL_AUTHORITY}
            puts $fx_stream [join [list $stage [lindex $group 0] [lindex $group 2] [lindex $group 3] $name $actual $want] "\t"]
            flush $fx_stream
            if {$actual ne "0" && $actual ne "1"} {error "Nonboolean native query"}
            if {$want eq "0" && $actual ne "0"} {lappend mismatches [list [lindex $group 0] [lindex $group 2] [lindex $group 3] $name $actual $want]}
        }
    }
    if {[llength $mismatches]} {error "Protected/reset exclusion mismatch: $stage $mismatches"}
}
