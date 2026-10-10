# Read-only native labels. No exclusion, EL, reset, or report commands.
proc point789_session {} {
    uplevel #0 [list source [file join $::env(DVE_COVERAGE_OUTPUT) selection.tcl]]
    set ::cv_test_only 1
    uplevel #0 [list source $::point_library]
    uplevel #0 [list source $::point_selector]
    gui_open_cov -hier $::cv_design -testdir [list $::cv_vdb] -test [list $::cv_test] -merge PointIdentityReadOnly
    foreach metric {Line Branch} {
        # Only the bind parent has compiled Line/Branch capacity. The child is absent.
        cv_snapshot observed $metric 0 $::point_scope
    }
    puts POINT789_READONLY_DONE
}
if {![info exists ::point_test_only]} {
    if {[catch {point789_session} message]} {
        set f [open [file join $::env(DVE_COVERAGE_OUTPUT) error.txt] {WRONLY CREAT EXCL}]
        puts $f $message; puts $f $::errorInfo; close $f
        puts "POINT789_READONLY_FAILED $message"
        exit 1
    }
    exit 0
}
