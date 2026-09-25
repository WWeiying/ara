# Read-only diagnostic core/probe enumeration for the isolated J10 image.
set manager_open 0
set server_connected 0
set target_open 0
set status [catch {
    open_hw_manager
    set manager_open 1
    connect_hw_server -url localhost:3121
    set server_connected 1
    set targets [get_hw_targets]
    if {[llength $targets] != 1} { error "Expected one JTAG target" }
    set target [lindex $targets 0]
    open_hw_target $target
    set target_open 1
    set devices [get_hw_devices -of_objects $target -filter {PART =~ xcvu9p*}]
    if {[llength $devices] != 1} { error "Expected one xcvu9p device" }
    set device [lindex $devices 0]
    current_hw_device $device
    set_property PROBES.FILE [lindex $argv 0] $device
    refresh_hw_device $device
    foreach vio [get_hw_vios -of_objects $device] {
        puts "VIO $vio CELL_NAME=[get_property CELL_NAME $vio]"
        foreach probe [get_hw_probes -of_objects $vio] {
            puts "PROBE $probe NAME=[get_property NAME $probe] TYPE=[get_property TYPE $probe] PORT=[get_property PROBE_PORT $probe]"
        }
    }
    foreach axi [get_hw_axis -of_objects $device] {
        puts "AXI $axi CELL_NAME=[get_property CELL_NAME $axi] PROTOCOL=[get_property PROTOCOL $axi]"
    }
    puts INSPECT_PASS
} message options]
if {$target_open} { catch {close_hw_target} }
if {$server_connected} { catch {disconnect_hw_server} }
if {$manager_open} { catch {close_hw_manager} }
if {$status} {
    puts stderr "INSPECT_ERROR $message"
    exit 1
}
