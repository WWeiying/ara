# Batch entry point for run.ps1, which owns the lock and validates input hashes.
if {[catch {
    if {[llength $argv] != 4} { error "Use scripts/run.ps1 [-Stage synth|impl]" }
    source [file join [file dirname [info script]] common.tcl]
    source [file join [file dirname [info script]] run_support.tcl]
    fpga_run::execute {*}$argv
} message]} {
    puts stderr $::errorInfo
    exit 1
}
exit 0
