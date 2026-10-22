# Reuse sealed C910 selection/bind/reset and FMA tree walker in a private session.
set ::c910_test_only 1
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/c910_srt_datapath_native_v3.tcl}
proc scalar_radix_session {} {
    global env fma_instances fma_design fma_vdb fma_test fma_python fma_helper c910_fma_tcl
    source [file join $env(DVE_COVERAGE_OUTPUT) selection.tcl]
    c910_primitives
    gui_open_cov -hier $fma_design -testdir [list $fma_vdb] -test [list $fma_test] -merge ScalarRadix158NativeOnly
    gui_list_expand -id CoverageTable.1 -all {<root>}
    fma_save initial-empty.el
    set instance [lindex $fma_instances 0]
    c910_bind before $instance
    c910_load candidate.el
    c910_bind selected $instance
    fma_save first.el
    fma_check first.el
    c910_reset
    c910_bind reset $instance
    fma_save reset-empty.el
    c910_load first.el
    c910_bind reloaded $instance
    fma_save second.el
    fma_check second.el
    c910_reset
    c910_bind final $instance
    fma_save final-empty.el
    puts SCALAR_RADIX158_NATIVE_DONE
}
if {[catch {scalar_radix_session} message]} {
    c910_failure $message $::errorInfo
}
gui_exit -noprompt
