# Reuse frozen procedure-only combo03. Never execute a second standalone session.
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/report_c910_combo742_v3.tcl}
set q745_source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/queue_constant_native.tcl}
set q745_stream [open $q745_source r]
set q745_body [read $q745_stream]
close $q745_stream
set q745_start [string first {proc qc_need } $q745_body]
set q745_end [string first {proc qc_session } $q745_body]
if {$q745_start < 0 || $q745_end <= $q745_start} {error "Queue procedure boundary differs"}
uplevel #0 [string range $q745_body $q745_start [expr {$q745_end - 1}]]
rename combo_audit combo745_original_audit
proc combo_audit {stage mode active} {
    combo745_original_audit $stage $mode $active
    p740_root
    qc_audit $mode
}
rename p740_summary combo745_system_summary
proc p740_summary {stage} {
    combo745_system_summary $stage
    set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) modules_$stage.csv] {WRONLY CREAT EXCL}]
    fconfigure $stream -encoding utf-8 -translation lf
    csv_row $stream {Stage Scope Token Handle GUIPath Name Score Line Toggle FSM Condition Branch}
    set failed [catch {
        foreach root $::report745_roots {
            set scope [lindex $root 0]
            set ::p740_root_names($scope) [lindex $root 1]
            p740_row $scope $stream $stage
        }
    } message]
    close $stream
    p740_root
    if {$failed} {error $message}
    puts "COMBO745_MODULE_SUMMARY $stage [llength $::report745_roots]"
}
# Frozen hook sources selection locally. Only added queue/root declarations must be global.
rename apply_reviewed_waivers combo745_original_hook
proc apply_reviewed_waivers {id} {
    uplevel #0 [list source [file join $::env(DVE_COVERAGE_OUTPUT) selection.tcl]]
    combo745_original_hook $id
}
