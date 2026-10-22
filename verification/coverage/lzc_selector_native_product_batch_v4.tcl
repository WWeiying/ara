# Reuse sealed visibility/gate code as a library, never execute its v3 entry.
set lpn_test_only 1
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/lzc_selector_native_product_batch_v3.tcl}
proc lpn_guard_exclude {args} {
    lpd_require $::lpn_global_before_complete "Singleton forbidden before complete global4200 audit"
    return [gui_exclude_items {*}$args]
}
proc lpn_session {} {
    global env lpa_binding lpa_expected lpn_global_before_complete
    set lpn_global_before_complete 0
    source $env(LZC_SELECTOR_NATIVE_AUDIT_BINDINGS)
    lpd_require [expr {[array size lpa_binding] == 1200 && [array size lpa_expected] == 36}] "Full observed native bindings required"
    # This sealed procedure copy differs only at the one singleton exclude call.
    source $env(LZC_SELECTOR_NATIVE_GUARDED_SESSION)
    puts LZC_NATIVE_BATCH_V4_BUILTIN_PRESERVING_SESSION_LOADED
    lpb_session
}
if {![info exists lpn_v4_test_only]} {
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
