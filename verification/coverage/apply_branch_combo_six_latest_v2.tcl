# Evaluate only frozen procedure definitions, then install the fresh selection adapter.
set six2_stream [open {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/apply_branch_combo_six_latest.tcl} r]
set six2_text [read $six2_stream]
close $six2_stream
set six2_boundary {set failed [catch {six_initialize; qbsapp_session} message]}
set six2_index [string first $six2_boundary $six2_text]
if {$six2_index < 0 || $six2_index != [string last $six2_boundary $six2_text]} {
    error "SIX2 frozen entry boundary differs"
}
uplevel #0 [string range $six2_text 0 [expr {$six2_index-1}]]
rename six_initialize six2_frozen_initialize
proc six_initialize {} {
    six2_frozen_initialize
    source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/six_policy_singleton_selection_v2.tcl}
    six2_install_selection_adapter
    puts SIX2_SELECTION_ADAPTER_INSTALLED
}
set six2_tail [string range $six2_text $six2_index end]
uplevel #0 $six2_tail
