# Program one VCU118 SRAM image, select passive boot and pulse the full VIO reset.
# Usage: vivado -mode batch -source program_host_image.tcl -tclargs image.bit image.ltx
proc one {objects label} {
    if {[llength $objects] != 1} { error "Expected one $label, found [llength $objects]: $objects" }
    return [lindex $objects 0]
}

proc program_host_image {bit ltx} {
    foreach path [list $bit $ltx] {
        if {![file isfile $path] || [file size $path] == 0} { error "Missing/empty image: $path" }
    }
    open_hw_manager
    connect_hw_server -url localhost:3121
    set target [one [get_hw_targets] {hardware target}]
    open_hw_target $target
    set device [one [get_hw_devices -of_objects $target -filter {PART =~ xcvu9p*}] {VCU118 FPGA}]
    puts "TARGET $target DEVICE $device PART=[get_property PART $device]"
    current_hw_device $device
    set_property PROGRAM.FILE $bit $device
    set_property PROBES.FILE $ltx $device
    program_hw_devices $device
    puts "PROGRAMMED $bit"
    refresh_hw_device $device

    set vio [one [get_hw_vios -of_objects $device] {board VIO}]
    set reset [one [get_hw_probes -quiet probe_out0 -of_objects $vio] {reset probe}]
    set boot_mode [one [get_hw_probes -quiet probe_out1 -of_objects $vio] {boot mode probe}]
    set boot_select [one [get_hw_probes -quiet probe_out2 -of_objects $vio] {boot select probe}]
    set status [one [get_hw_probes -quiet probe_in0 -of_objects $vio] {status probe}]
    set_property OUTPUT_VALUE_RADIX HEX $reset
    set_property OUTPUT_VALUE_RADIX HEX $boot_mode
    set_property OUTPUT_VALUE_RADIX HEX $boot_select
    set_property INPUT_VALUE_RADIX HEX $status
    set_property OUTPUT_VALUE 0 $boot_mode
    set_property OUTPUT_VALUE 0 $boot_select
    set_property OUTPUT_VALUE 1 $reset
    commit_hw_vio $vio
    after 100
    set_property OUTPUT_VALUE 0 $reset
    commit_hw_vio $vio
    puts {VIO_FULL_RESET_PULSED boot_mode=0 boot_select=0}

    for {set attempt 0} {$attempt < 120} {incr attempt} {
        refresh_hw_vio $vio
        set raw [get_property INPUT_VALUE $status]
        regsub -nocase {^0x} $raw {} digits
        if {![regexp -nocase {^[0-9a-f]+$} $digits]} { error "Malformed VIO status: $raw" }
        scan $digits %x value
        if {$value == 14} {
            puts "BOARD_READY status=$raw"
            close_hw_target $target
            disconnect_hw_server
            close_hw_manager
            return
        }
        after 1000
    }
    error "Board did not reach VIO status 0xe after reset; last=$raw"
}

if {[catch {
    if {[llength $argv] != 2} { error {Expected image.bit image.ltx} }
    program_host_image {*}$argv
} message options]} {
    puts stderr "PROGRAM_HOST_ERROR $message"
    puts stderr [dict get $options -errorinfo]
    exit 1
}
exit 0
