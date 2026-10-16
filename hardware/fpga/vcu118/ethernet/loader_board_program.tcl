# Program only the isolated Ethernet loader image on a single VCU118.
namespace eval loader_board {
    proc one {objects description} {
        if {[llength $objects] != 1} {
            error "Expected exactly one $description, found [llength $objects]"
        }
        return [lindex $objects 0]
    }

    proc run {bit probes server} {
        foreach path [list $bit $probes] {
            if {![file isfile $path]} { error "Missing loader image: $path" }
        }
        set manager_open 0
        set server_connected 0
        set target_open 0
        set status [catch {
            open_hw_manager
            set manager_open 1
            connect_hw_server -url $server
            set server_connected 1
            set target [one [get_hw_targets] "JTAG target"]
            open_hw_target $target
            set target_open 1
            set device [one [get_hw_devices -of_objects $target -filter {PART =~ xcvu9p*}] "xcvu9p device"]
            current_hw_device $device
            puts "PROGRAM_TARGET $target DEVICE=$device PART=[get_property PART $device]"
            set_property PROGRAM.FILE $bit $device
            set_property PROBES.FILE $probes $device
            program_hw_devices $device
            refresh_hw_device $device
            puts "LOADER_IMAGE_PROGRAMMED_NO_FIRMWARE $bit"
        } message options]
        if {$target_open} { catch {close_hw_target} }
        if {$server_connected} { catch {disconnect_hw_server} }
        if {$manager_open} { catch {close_hw_manager} }
        if {$status} { return -options $options $message }
    }
}

if {[llength $argv] != 3} {
    error "Usage: loader_board_program.tcl BIT LTX HW_SERVER_URL"
}
if {[catch {loader_board::run {*}$argv} message options]} {
    puts stderr [dict get $options -errorinfo]
    exit 1
}
exit 0
