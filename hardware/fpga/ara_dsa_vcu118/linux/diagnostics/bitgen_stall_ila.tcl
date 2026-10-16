# Diagnostic-only bitgen from the reviewed, immutable routed checkpoint.
if {[catch {
    if {[llength $argv] != 3} { error "Expected package checkpoint output" }
    lassign $argv package checkpoint output
    set ::env(ARA_FPGA_PROFILE) host_ethernet
    set_param board.repoPaths [linsert [get_param board.repoPaths] 0 [file join $package board_files]]
    if {[llength [get_board_parts -quiet xilinx.com:vcu118:part0:2.4]] != 1} {
        error "Missing frozen board definition"
    }
    set_msg_config -id {Board 49-67} -new_severity ERROR
    set_msg_config -id {Constraints 18-638} -new_severity ERROR
    set_param general.maxThreads 8
    set argv [list $checkpoint $output audited]
    source [file join $package scripts write_profile_bit.tcl]
} message]} {
    puts stderr $::errorInfo
    exit 1
}
exit 0
