source [file join [file dirname [info script]] trace_fpga_control_net.tcl]
if {[llength $argv] != 1} {error "Expected new output directory"}
set out [lindex $argv 0]
if {[file exists $out]} {error "Refusing existing output directory"}
file mkdir $out
proc get_nets {args} {
    if {[lsearch -exact $args -hierarchical] >= 0} {return {net other}}
    return {net}
}
proc get_pins {args} {
    if {[lsearch -exact $args -leaf] >= 0} {return {driver load1 load2}}
    return {input}
}
proc get_cells {args} {return [lindex $args end]}
proc list_property {obj} {return {INIT LOC}}
proc get_property {prop obj} {
    switch -- $prop {
        NAME {if {$obj eq "net"} {return {top/value[14][31]_i_1_n_0}}; return $obj}
        DIRECTION {if {$obj eq "driver"} {return OUT}; return IN}
        REF_NAME {if {$obj eq "driver"} {return LUT2}; return FDRE}
        REF_PIN_NAME {if {$obj eq "driver"} {return O}; return CE}
        INIT {return {4'h2}}
        LOC {return SLICE_X0Y0}
        default {error "Unexpected property $prop"}
    }
}
set file [file join $out trace.txt]
fpga_control_trace::write {top/value[14][31]_i_1_n_0} $file
set f [open $file r]; set content [read $f]; close $f
if {![string match {*DRIVERS 1 LOAD_TYPES {{FDRE CE} 2}*} $content]} {
    error "Missing enable-load histogram: $content"
}
if {![catch {fpga_control_trace::write {top/value[14][31]_i_1_n_0} $file}]} {
    error "Overwrote existing evidence"
}
if {![catch {fpga_control_trace::write missing [file join $out absent.txt]}]} {
    error "Accepted missing net"
}
puts "PASS: exact array-name lookup, driver inputs, CE histogram, immutable output"
