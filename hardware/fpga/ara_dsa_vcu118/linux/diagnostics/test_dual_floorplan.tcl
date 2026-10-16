source [file join [file dirname [info script]] dual_floorplan.tcl]
dual_floor::validate_regions
rename dual_floor::plan dual_floor::reviewed_plan
proc dual_floor::plan {} {
    return {{overlap CLOCKREGION_X2Y12:CLOCKREGION_X4Y13 {fifo}}}
}
if {![catch {dual_floor::validate_regions}]} {error "MIG overlap not detected"}
rename dual_floor::plan {}
rename dual_floor::reviewed_plan dual_floor::plan
puts "PASS MIG region exclusion"
set all {}
foreach item [dual_floor::plan] {
    lassign $item name range members
    if {![regexp {^CLOCKREGION_X[0-5]Y[0-9]+:CLOCKREGION_X[0-5]Y[0-9]+$} $range]} {error "Invalid range"}
    foreach member $members {
        if {([string match *gen_channel* $member] && ![string match ara_c?_mig $name]) || [string match *pcs_pma* $member] || [string match i_cheshire* $member]} {
            error "Unexpected PHY/CPU relocation"
        }
        if {$member in $all} {error "Duplicate member"}
        lappend all $member
    }
}
if {[llength $all]!=22} {error "Expected 20 user hierarchies and two explicit MIG regions"}
proc get_cells {args} {
    set filter [lindex $args end]
    if {$filter eq {!IS_PRIMITIVE}} {
        if {$::scenario eq "missing"} {return [lrange $::all 1 end]}
        return $::all
    }
    return [dual_floor::buffer_name]
}
proc get_pblocks {args} {return {}}
proc get_property {prop obj} {
    switch $prop {
        NAME {return $obj}
        REF_NAME {return BUFGCE}
        IS_LOC_FIXED {return [expr {$::scenario eq "fixed"}]}
        CLOCK_REGION {return X4Y6}
        default {error "Unexpected property $prop"}
    }
}
proc create_pblock {name} {lappend ::mutations create; return $name}
proc resize_pblock {args} {lappend ::mutations resize}
proc add_cells_to_pblock {args} {lappend ::mutations add}
proc report_utilization {args} {}
proc set_property {name value obj} {
    if {$name ni {IS_SOFT EXCLUDE_PLACEMENT CONTAIN_ROUTING CLOCK_REGION}} {error "Unexpected constraint edit"}
    set expected [expr {$name eq "IS_SOFT" && [string match ara_c?_mig $obj] ? "true" : "false"}]
    if {$name ne "CLOCK_REGION" && $value ne $expected} {error "Wrong Pblock policy"}
    lappend ::mutations $name
}
set tmp [file join /tmp dual_floorplan_test_[pid]]
try {
    foreach scenario {healthy missing fixed} {
        set mutations {}
        set failed [catch {dual_floor::apply $tmp} result]
        if {$scenario eq "healthy"} {
            if {$failed || [llength $result]!=6} {error "Bad valid plan: $result"}
            if {[lindex $mutations end] ne "CLOCK_REGION"} {error "Missing MDM constraint"}
        } elseif {!$failed || [llength $mutations]} {error "Partial modification on invalid design"}
        puts "PASS $scenario"
    }
} finally {file delete -force $tmp}
