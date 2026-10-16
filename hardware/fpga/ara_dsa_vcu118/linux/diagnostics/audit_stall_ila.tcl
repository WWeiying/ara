# Review the completed observation checkpoint with the frozen audit helpers.
if {[catch {
    if {[llength $argv] != 4} { error "Expected checkpoint package session token" }
    lassign $argv checkpoint package session token
    set ::env(ARA_FPGA_PROFILE) host_ethernet
    source [file join $package scripts common.tcl]
    source [file join $package scripts audit_support.tcl]
    set_param board.repoPaths [linsert [get_param board.repoPaths] 0 [file join $package board_files]]
    if {[llength [get_board_parts -quiet $board_part]] != 1} {
        error "Frozen board definition unavailable"
    }
    set_msg_config -id {Board 49-67} -new_severity ERROR
    set_msg_config -id {Constraints 18-638} -new_severity ERROR
    set_param general.maxThreads 8
    fpga_audit::execute $checkpoint $session $token
} message]} {
    puts stderr $::errorInfo
    exit 1
}
exit 0
