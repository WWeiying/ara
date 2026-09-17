# Batch entry point; no current project, RTL, or XDC is loaded.
if {[catch {
    if {[llength $argv] != 3} { error "Usage: audit_routed.tcl checkpoint session token" }
    source [file join [file dirname [info script]] common.tcl]
    source [file join [file dirname [info script]] audit_support.tcl]
    fpga_audit::execute {*}$argv
} message]} {
    puts stderr $::errorInfo
    exit 1
}
exit 0
