source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/lzc_selector_native_product_audit_visibility.tcl}
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/lzc_selector_native_product_guard_legacy.tcl}
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
proc lpn_preload {} {
    set patchlevel [lpng_preflight]
    set payloads [lpng_list_preflight]
    puts "LZC_NATIVE_GUARD_PREFLIGHT_COMPLETE patchlevel=$patchlevel payloads=$payloads gate=closed no_native_call"
}
proc lpn_session {} {
    global env lpa_binding lpa_expected lpn_global_before_complete
    set lpn_global_before_complete 0
    lpn_preload
    source $env(LZC_SELECTOR_NATIVE_AUDIT_BINDINGS)
    lpd_require [expr {[array size lpa_binding] == 1200 && [array size lpa_expected] == 36}] "Full observed native bindings required"
    source $env(LZC_SELECTOR_NATIVE_GUARDED_SESSION)
    puts LZC_NATIVE_BATCH_V5_LEGACY_GUARD_SESSION_LOADED
    lpb_session
}
