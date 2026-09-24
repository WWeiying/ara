set ::axi_inspect_library_only 1
source [file join [file dirname [info script]] host_axi_netlist.tcl]
set cell gen_host.i_host_bridge/i_jtag_mem
set mode constant
proc open_checkpoint {path} {}
proc close_design {} {}
proc version {args} { return mock }
proc get_cells {args} {
    if {[lindex $args 0] eq "-hier"} {
        if {[lindex $args end] eq "NAME =~ */i_jtag_mem"} { return $::cell }
        if {$::mode eq "export_failure" && [string match *i_read_unit [lindex $args end]]} {
            return i_cheshire_soc/gen_llc.i_llc/i_axi_llc_top_raw/i_read_unit
        }
        return {}
    }
    return [lindex $args end]
}
proc get_property {property object} {
    if {$property eq "IS_BLACKBOX"} { return [expr {$::mode eq "blackbox"}] }
    if {$property eq "NAME"} { return $object }
    if {$property eq "REF_NAME"} { return $object }
    error "Unexpected property $property"
}
proc get_nets {args} { return [lindex $args end] }
proc write_verilog {args} { error "mock export failure" }
proc get_pins {args} {
    if {[lindex $args 0] eq "-leaf"} {
        set net [lindex $args 2]
        if {$::mode eq "dynamic"} { return FDRE }
        if {[regexp {m_axi_(ar|aw)size\[([01])\]} $net]} { return VCC }
        if {[regexp {m_axi_(ar|aw)size\[2\]} $net]} { return GND }
        return FDRE
    }
    set pins {}
    foreach field {arsize awsize} {
        for {set i 0} {$i < 3} {incr i} {
            lappend pins [format {%s/m_axi_%s[%d]} $::cell $field $i]
        }
    }
    return $pins
}
set output [lindex $argv 0]
foreach mode {constant dynamic export_failure} expected {011 ??? 011} {
    axi_inspect::inspect mock.dcp $output
    set stream [open [file join $output axi_netlist.rpt] r]
    set report [read $stream]
    close $stream
    if {[string first "SIZE arsize bits=$expected " $report] < 0 ||
        [string first "INSPECTION_COMPLETE" $report] < 0} { error "Wrong report: $report" }
    if {$mode eq "export_failure" && [string first "NETLIST_EXPORT_ERROR" $report] < 0} {
        error "Export failure was not reported"
    }
}
set mode blackbox
if {![catch {axi_inspect::inspect mock.dcp $output} error] ||
    [string first "black box" $error] < 0} { error "Black box was not rejected" }
puts "PASS: netlist constant, unresolved and black-box checks"
