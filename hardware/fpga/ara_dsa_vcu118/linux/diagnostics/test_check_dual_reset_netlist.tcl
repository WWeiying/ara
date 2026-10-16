set ::dual_reset_library_only true
source [file join [file dirname [info script]] check_dual_reset_netlist.tcl]
set mode normal
proc get_cells {args} {
    set expr [lindex $args end]
    regexp {NAME (?:==|=~) ([^ ]+)} $expr -> name
    if {[string match */i_ui_rstgen/* $name]} {
        set base [string range $name 0 end-1]
        return [list ${base}r0 ${base}r1 ${base}r2 ${base}r3]
    }
    if {$::mode eq "missing"} {return {}}
    return $name
}
proc get_property {prop cell} {
    if {$prop eq "NAME"} {return $cell}
    if {$prop eq "ASYNC_REG"} {
        return [expr {[string match */i_ui_rstgen/* $cell] || $::mode eq "protected"}]
    }
    if {$prop eq "DONT_TOUCH"} {return 0}
    error "Unexpected property $prop"
}
proc get_pins {args} {
    if {[lindex $args end] eq "DIRECTION == IN && IS_LEAF"} {return [lrepeat 40 inverter/I0]}
    set cell [lindex $args 1]
    if {[lindex $args end] eq "REF_PIN_NAME == CLR"} {return $cell/CLR}
    return $cell/Q
}
proc get_nets {args} {return reset_net}
proc all_fanout {args} {
    if {$::mode eq "data_only"} {return [lrepeat 200 reg/D]}
    if {$::mode eq "disconnected"} {return {}}
    return [lrepeat 200 reg/CLR]
}
proc filter {pins expr} {
    if {$expr ne "REF_PIN_NAME == CLR || REF_PIN_NAME == PRE"} {error "Unexpected filter"}
    set result {}
    foreach pin $pins {if {[file tail $pin] in {CLR PRE}} {lappend result $pin}}
    return $result
}
proc all_fanin {args} {
    if {$::mode eq "wrong_driver"} {return other/Q}
    return [string map {ui_resetn_reg/CLR i_ui_rstgen/i_rstgen_bypass/r3/Q} [lindex $args end]]
}
set out [file join /tmp dual_reset_check_[pid]]
file mkdir $out
try {
    check_dual_reset_netlist $out
    foreach mode {missing protected wrong_driver data_only disconnected} {
        if {![catch {check_dual_reset_netlist $out} message]} {error "Accepted bad case $mode"}
    }
    puts "PASS: inverter tree accepted; missing, protected, wrong source, data-only and disconnected rejected"
} finally {file delete -force $out}
