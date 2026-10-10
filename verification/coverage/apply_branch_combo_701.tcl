# Tcl 8.4; each group retains its own complete protected native inventory.
source [file join $env(DVE_COVERAGE_OUTPUT) root-helpers.tcl]
set op1144_library_only 1
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/capture_operand_1144.tcl}
set obd_library_only 1
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/apply_operand_debug_1832.tcl}
set ff1_library_only 1
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/capture_ff1_native904.tcl}
rename qbs_audit combo_qbs_audit
proc qbs_audit {stage active} {
    global env
    set root $env(DVE_COVERAGE_OUTPUT)
    set failed [catch {
        foreach group {qbs debug operand ff1} {
            qbsapp_root
            uplevel #0 [list source [file join $root $group-selection.tcl]]
            set env(DVE_COVERAGE_OUTPUT) [file join $root $group]
            switch -- $group {
                qbs {combo_qbs_audit $stage $active}
                debug {obd_audit $stage $active}
                operand {op1144_audit $stage $active}
                ff1 {ff1_audit $stage $active}
            }
            set env(DVE_COVERAGE_OUTPUT) $root
        }
    } message]
    set env(DVE_COVERAGE_OUTPUT) $root
    uplevel #0 [list source [file join $root qbs-selection.tcl]]
    qbsapp_root
    if {$failed} {error $message}
}
set needle {($qbsapp_count != 1 && $qbsapp_count != 699)}
set body [info body qbsapp_session]
if {[string first $needle $body] < 0 || [string first $needle $body] != [string last $needle $body]} {
    error "Frozen population contract differs"
}
proc qbsapp_session {} [string map [list $needle {$qbsapp_count != 701}] $body]
set failed [catch {qbsapp_session} message]
if {$failed} {puts "COMBO_ERROR $message\n$::errorInfo"}
set cleanup {}
if {[catch {gui_exclusion -reset} detail]} {lappend cleanup $detail}
if {[info exists dbg_scopes]} {
    if {[catch {qbsapp_root; qbs_audit final 0} detail]} {lappend cleanup $detail}
}
if {[catch {dbg_save final-empty.el 1} detail]} {lappend cleanup $detail}
if {$failed || [llength $cleanup]} {puts "COMBO_FAILED $message cleanup=$cleanup"} else {puts COMBO_DONE_EXACT4328}
gui_exit -noprompt
