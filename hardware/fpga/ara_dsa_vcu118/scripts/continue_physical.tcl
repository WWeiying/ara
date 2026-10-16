source [file join [file dirname [info script]] continue_physical_support.tcl]
if {[catch {
    if {[llength $argv] != 4} { error "Expected: package synth_run session token" }
    foreach script {common.tcl run_support.tcl warning_details.tcl} {
        source [file join [lindex $argv 0] scripts $script]
    }
    fpga_physical::execute {*}$argv
} message]} {
    puts stderr $::errorInfo
    if {[llength $argv] == 4 && [file isdirectory [lindex $argv 2]]} {
        fpga_physical::stage [lindex $argv 2] failed
    }
    exit 1
}
exit 0
