source [file join [file dirname [info script]] dual_slr_locality.tcl]
set out [lindex $argv 0]
if {$out eq "" || [file exists $out]} {error "Expected new result directory"}
file mkdir $out
proc get_cells {args} {
    set filter [lindex $args end]
    if {[string match {*REF_NAME == RX_BITSLICE} $filter]} {return phy_anchor}
    if {[string match {*REF_NAME == MMCME4_ADV} $filter]} {
        return [expr {[string match {*gen_ddr2*} $filter] ? "c2_anchor" : "c1_anchor"}]
    }
    set name [string range $filter 8 end]
    if {$::scenario eq "missing" && [string match {*i_ui_por} $name]} {return {}}
    return "$::generation|$name"
}
proc get_sites {args} {return [lindex $args end]}
proc get_slrs {args} {
    if {$::scenario eq "ambiguous"} {return {SLR1 SLR2}}
    return [dict get {phy_anchor SLR1 c1_anchor SLR2 c2_anchor SLR0} [lindex $args end]]
}
proc get_property {property cell} {
    if {$property eq "NAME"} {return [lindex [split $cell |] end]}
    if {$property eq "IS_PRIMITIVE"} {return 0}
    return $::applied($cell)
}
proc set_property {property value cell} {
    if {$property ne "USER_SLR_ASSIGNMENT"} {error "Unexpected non-placement edit"}
    if {![string match "$::generation|*" $cell]} {error "Stale or unresolved object: $cell"}
    set ::applied($cell) $value
}
foreach scenario {healthy missing ambiguous} {
    set generation placed
    unset -nocomplain applied
    array set applied {}
    set failed [catch {dual_locality::apply [file join $out $scenario.tsv]} message]
    if {$scenario eq "healthy"} {
        if {$failed || [array size applied]!=10} {error "Invalid healthy result: $message"}
    } else {
        if {!$failed || [array size applied]!=0} {error "Changed partial plan: $scenario"}
    }
    puts "PASS locality $scenario"
}
set scenario healthy
set generation placed
set saved_plan [dual_locality::plan]
set generation optimized
array unset applied
dual_locality::apply_plan $saved_plan [file join $out reopened.tsv]
if {[array size applied]!=10} {error "Missing reopened assignments"}
puts "PASS locality reopened_checkpoint"
