# DVE -script does not reliably set info script; bind the immutable source explicitly.
set ::c910_test_only 1
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/c910_srt_datapath_native_v3.tcl}
proc c910_session {} {
    global env fma_instances fma_design fma_vdb fma_test fma_python fma_helper c910_fma_tcl
    source [file join $env(DVE_COVERAGE_OUTPUT) selection.tcl]
    c910_primitives
    gui_open_cov -hier $fma_design -testdir [list $fma_vdb] -test [list $fma_test] -merge C9101264NativeRecovery
    gui_list_expand -id CoverageTable.1 -all {<root>}
    fma_save initial-empty.el
    foreach instance $fma_instances {c910_bind before $instance}
    gui_exclusion_file -load -file [list {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/c910-srt-native1264-load-agent-20261007-03/first.el}]
    gui_exclusion -id CoverageTable.1 -recalculate
    fma_need [expr {[gui_cov_excl_review -isEmpty] == 1}] "Native recovery needs review"
    foreach instance $fma_instances {c910_bind selected $instance}
    fma_save first.el
    fma_check first.el
    c910_reset
    foreach instance $fma_instances {c910_bind reset $instance}
    fma_save reset-empty.el
    c910_load first.el
    foreach instance $fma_instances {c910_bind reloaded $instance}
    fma_save second.el
    fma_check second.el
    c910_reset
    foreach instance $fma_instances {c910_bind final $instance}
    fma_save final-empty.el
    puts C910_SRT_NATIVE_CAPTURE_DONE
}
if {![info exists ::c910_recovery_test_only]} {
    if {[catch {c910_session} message]} {c910_failure $message $::errorInfo}
    gui_exit -noprompt
}
