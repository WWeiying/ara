source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/lzc_selector_native_product_batch_v5_library.tcl}
if {![info exists lpn_v5_test_only]} {
    set failed [catch {lpn_session} message]
    set cleanup {}
    if {[catch {gui_exclusion -reset} detail]} {lappend cleanup $detail}
    if {[info exists lpb_rows]} {
        if {[catch {lpb_audit [file join $lpb_output global-final.tsv] $lpb_rows -1} detail]} {lappend cleanup $detail}
        if {[catch {lpb_save [file join $lpb_output final-empty.el] 1} detail]} {lappend cleanup $detail}
    }
    if {$failed || [llength $cleanup]} {
        puts "LZC_NATIVE_BATCH_FAILED $message cleanup=$cleanup\n$::errorInfo"
    } else {puts LZC_NATIVE_BATCH_COMPLETE_PENDING_OFFLINE_VERIFICATION}
    gui_exit -noprompt
}
