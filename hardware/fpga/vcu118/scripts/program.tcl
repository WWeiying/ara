source [file join [file dirname [info script]] common.tcl]
require_vivado
set bit [file join $package_root output ${project_name}.bit]
set ltx [file join $package_root output ${project_name}.ltx]
if {![file exists $bit]} { error "Bitstream is missing; run implementation first." }
open_hw_manager
connect_hw_server
set targets [get_hw_targets]
if {[llength $targets] != 1} { error "Select the desired board manually in Hardware Manager." }
open_hw_target [lindex $targets 0]
set devices [get_hw_devices -filter {PART =~ xcvu9p*}]
if {[llength $devices] != 1} { error "Expected exactly one VCU118 device." }
set device [lindex $devices 0]
set_property PROGRAM.FILE $bit $device
if {[file exists $ltx]} { set_property PROBES.FILE $ltx $device }
program_hw_devices $device
refresh_hw_device $device
puts "FPGA configured. Check VIO status and UART. No flash was erased/programmed."
