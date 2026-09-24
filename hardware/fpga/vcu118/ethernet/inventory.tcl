# Read-only cable and device inventory. Do not program or refresh the device.
namespace eval eth_inventory {
    proc run {args} {
        if {[llength $args] > 1} { error "Usage: inventory.tcl ?hw_server_url?" }
        set server [expr {[llength $args] ? [lindex $args 0] : "localhost:3121"}]
        set opened_manager 0
        set connected_server 0
        set opened_target 0
        set status [catch {
            open_hw_manager
            set opened_manager 1
            connect_hw_server -url $server
            set connected_server 1
            set targets [get_hw_targets]
            puts "HW_TARGET_COUNT [llength $targets]"
            foreach target $targets { puts "HW_TARGET $target" }
            if {[llength $targets] != 1} {
                error "Expected exactly one JTAG target; no device was opened"
            }
            open_hw_target [lindex $targets 0]
            set opened_target 1
            set devices [get_hw_devices -filter {PART =~ xcvu9p*}]
            puts "VCU118_DEVICE_COUNT [llength $devices]"
            foreach device $devices {
                puts "VCU118_DEVICE $device PART=[get_property PART $device]"
            }
            if {[llength $devices] != 1} {
                error "Expected exactly one xcvu9p device; no programming attempted"
            }
            puts "READ_ONLY_INVENTORY_PASS"
        } message options]
        if {$opened_target} { catch {close_hw_target} }
        if {$connected_server} { catch {disconnect_hw_server} }
        if {$opened_manager} { catch {close_hw_manager} }
        if {$status} { return -options $options $message }
    }
}
eth_inventory::run {*}$argv
