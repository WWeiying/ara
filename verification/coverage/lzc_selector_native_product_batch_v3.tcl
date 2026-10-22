# Fresh entry point; frozen session/verifier contracts remain unchanged.
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/lzc_selector_native_product_audit_visibility.tcl}
rename lpb_audit lpn_visibility_audit
set lpn_global_before_complete 0
proc lpb_audit {path rows active} {
    global lpb_output lpn_global_before_complete
    set initial [expr {$path eq [file join $lpb_output global-before.tsv]}]
    if {$initial} {set lpn_global_before_complete 0}
    lpn_visibility_audit $path $rows $active
    if {$initial} {
        lpd_require [expr {[llength $rows] == 4200 && $active == -1}] "Full4200 initial audit required"
        set stream [open $path r]
        set lines 0
        while {[gets $stream line] >= 0} {incr lines}
        close $stream
        lpd_require [expr {$lines == 4201}] "Full4200 initial audit output required"
        set lpn_global_before_complete 1
        puts LZC_NATIVE_BATCH_GLOBAL_BEFORE_4200_COMPLETE
    }
}
proc lpn_guard_exclude {args} {
    lpd_require $::lpn_global_before_complete "Singleton forbidden before complete global4200 audit"
    return [lpn_native_exclude {*}$args]
}
proc lpn_session {} {
    global env lpa_binding lpa_expected lpn_global_before_complete
    set lpn_global_before_complete 0
    source $env(LZC_SELECTOR_NATIVE_AUDIT_BINDINGS)
    lpd_require [expr {[array size lpa_binding] == 1200 && [array size lpa_expected] == 36}] "Full observed native bindings required"
    rename gui_exclude_items lpn_native_exclude
    proc gui_exclude_items {args} {return [lpn_guard_exclude {*}$args]}
    puts LZC_NATIVE_BATCH_V3_VISIBILITY_BINDINGS_LOADED
    lpb_session
}
if {![info exists lpn_test_only]} {
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
