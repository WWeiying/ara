# Exercise Tcl transaction validation without Vivado or hardware.
set ::host_library_only 1
source [file join [file dirname [info script]] host_vivado.tcl]

proc host::core {bus} { return mem }
proc create_hw_axi_txn {name object args} {
    set ::created_args $args
    return txn
}
proc get_property {name object} {
    switch -- $name {
        CMD.SIZE { return 64 }
        CMD.LEN {
            if {[info exists ::override_len]} { return $::override_len }
            return [lindex $::created_args [expr {[lsearch -exact $::created_args -len] + 1}]]
        }
        CMD.BURST { return INCR }
        DATA {
            if {[info exists ::override_data]} { return $::override_data }
            return [lindex $::created_args [expr {[lsearch -exact $::created_args -data] + 1}]]
        }
        STATUS.AXI_WRITE_BUSY { return 0 }
        STATUS.AXI_WRITE_DONE { return 1 }
        STATUS.BRESP { return OKAY }
        default { error "Unexpected property $name" }
    }
}
proc run_hw_axi {txn} { incr ::runs }
proc refresh_hw_axi {object} {}
proc delete_hw_axi_txn {txn} { incr ::deletes }

set ::runs 0
set ::deletes 0
set line [list M WRITE 00000000ffff0000 2 fedcba9876543210_efcdab8967452301]
if {[host::transaction $line] ne "-" || $::runs != 1 || $::deletes != 1} {
    error "Word-separated two-beat transaction did not complete"
}
set ::override_len 1
if {![catch {host::transaction $line} message] ||
    ![string match "Vivado CMD.LEN differs*" $message] || $::runs != 1} {
    error "Wrong CMD.LEN was not rejected before write: $message"
}
unset ::override_len
set ::override_data 00000000000000000000000000000000
if {![catch {host::transaction $line} message] ||
    ![string match "Vivado DATA differs*" $message] || $::runs != 1} {
    error "Wrong DATA was not rejected before write: $message"
}
unset ::override_data
if {![catch {host::transaction [list M WRITE 00000000ffff0000 2 fedc_ba98]}] ||
    $::runs != 1 || $::deletes != 3} {
    error "Malformed word separators were accepted"
}
puts "PASS: burst transaction properties checked before execution"
