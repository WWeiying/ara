# Tcl 8.4. Import exact qualified EL only; no new exclusions or update API.
proc six_initialize {} {
    global env exp1272_library_only pack208_library_only six_expected_count
    source [file join $env(DVE_COVERAGE_OUTPUT) population-selection.tcl]
    if {$six_expected_count != 717} {error "Unreviewed explicit population"}
    source [file join $env(DVE_COVERAGE_OUTPUT) root-row-helpers.tcl]
    set exp1272_library_only 1
    source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/capture_narrow_exponent_native1272.tcl}
    set pack208_library_only 1
    source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/capture_fp16_pack_native208_v2.tcl}
    rename qbs_audit six_previous_audit
    proc qbs_audit {stage active} {
        global env
        set root $env(DVE_COVERAGE_OUTPUT)
        set failed [catch {
            foreach group {qbs debug operand ff1 exponent pack} {
                qbsapp_root
                uplevel #0 [list source [file join $root $group-selection.tcl]]
                set env(DVE_COVERAGE_OUTPUT) [file join $root $group]
                switch -- $group {
                    qbs {combo_qbs_audit $stage $active}
                    debug {obd_audit $stage $active}
                    operand {op1144_audit $stage $active}
                    ff1 {ff1_audit $stage $active}
                    exponent {exp1272_audit $stage $active}
                    pack {pack208_audit $stage $active}
                }
                set env(DVE_COVERAGE_OUTPUT) $root
            }
        } message]
        set env(DVE_COVERAGE_OUTPUT) $root
        uplevel #0 [list source [file join $root qbs-selection.tcl]]
        qbsapp_root
        if {$failed} {error $message}
    }
    set body [info body qbsapp_session]
    set countneedle {$qbsapp_count != 701}
    if {[string first $countneedle $body] < 0 || [string first $countneedle $body] != [string last $countneedle $body]} {
        error "Frozen population guard boundary differs"
    }
    set body [string map [list $countneedle {$qbsapp_count != $six_expected_count}] $body]
    set body "global six_expected_count\n$body"
    set needle "qbsapp_summary applied\n    gui_exclusion -reset"
    if {[string first $needle $body] < 0 || [string first $needle $body] != [string last $needle $body]} {
        error "Frozen after-root session boundary differs"
    }
    set replacement "qbsapp_summary applied\n    qbsapp_root\n    qbs_audit reloaded 1\n    dbg_save after-root.el\n    puts SIX_COMBO_AFTER_ROOT_VERIFIED\n    gui_exclusion -reset"
    proc qbsapp_session {} [string map [list $needle $replacement] $body]
    source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/six_policy_singleton_selection_v2.tcl}
    six2_install_selection_adapter
    puts SIX717_SELECTION_ADAPTER_INSTALLED
}
set failed [catch {six_initialize; qbsapp_session} message]
if {$failed} {puts "SIX_COMBO_ERROR $message\n$::errorInfo"}
set cleanup {}
if {[catch {gui_exclusion -reset} detail]} {lappend cleanup $detail}
if {[llength [info commands qbs_audit]] && [info exists dbg_scopes]} {
    if {[catch {qbsapp_root; qbs_audit final 0} detail]} {lappend cleanup $detail}
} else {
    lappend cleanup {Incomplete audit initialization}
}
if {[llength [info commands dbg_save]]} {
    if {[catch {dbg_save final-empty.el 1} detail]} {lappend cleanup $detail}
} else {
    lappend cleanup {Missing native export helper}
}
if {$failed || [llength $cleanup]} {
    puts "SIX_COMBO_FAILED $message cleanup=$cleanup"
} else {
    puts SIX_COMBO_DONE_EXACT5808
}
gui_exit -noprompt
