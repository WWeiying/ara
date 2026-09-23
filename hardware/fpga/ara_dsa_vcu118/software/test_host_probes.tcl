# Check host setup ordering without Vivado or hardware.
set ::host_library_only 1
source [file join [file dirname [info script]] host_vivado.tcl]

proc open_hw_manager {} {}
proc connect_hw_server {args} {}
proc get_hw_targets {} { return {target0} }
proc get_property {name object} { return $object }
proc open_hw_target {target} {}
proc get_hw_devices {args} { return {device0} }
proc current_hw_device {device} {}
proc set_property {name value device} {
    if {$name ne "PROBES.FILE" || $device ne "device0" || $value ne $::expected_probes} {
        error "Wrong probes association"
    }
    lappend ::calls set
}
proc refresh_hw_device {device} { lappend ::calls refresh }
proc get_hw_axis {args} { return {} }

set ::expected_probes [info script]
set ::calls {}
set arguments [list 1 token localhost:3121 - - i_jtag_mem i_jtag_debug $::expected_probes]
if {![catch {host::main $arguments} message] ||
    ![string match "Expected one CELL_NAME suffix*" $message] ||
    $::calls ne {set refresh}} {
    error "Probes file was not applied before hardware refresh: $::calls; $message"
}

set ::calls {}
set arguments [list 1 token localhost:3121 - - i_jtag_mem i_jtag_debug -]
if {![catch {host::main $arguments} message] || $::calls ne {refresh}} {
    error "Optional probes path changed existing flow: $::calls; $message"
}
puts "PASS: probes applied before refresh"
