# Independent three-stage read-only measurement of already-qualified exclusions.
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/apply_points740_v4.tcl}
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/native_toggle_ratio_hook.tcl}
proc csv_row {stream values} {
    set quoted {}
    foreach value $values {lappend quoted "\"[string map [list \" \"\"] $value]\""}
    puts $stream [join $quoted ,]
}
# Selection is deliberately global, before any procedure can create local aliases.
source [file join $::env(DVE_COVERAGE_OUTPUT) selection.tcl]
proc ratio763_reset {} {
    gui_cov_show_value -switch false
    gui_exclusion -reset
    gui_exclusion -id CoverageTable.1 -recalculate
    gui_process_events -mstime 100
    p740_root
}
proc ratio763_stage {stage} {
    global p740_scopes p740_root_names
    set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) percentages_$stage.csv] {WRONLY CREAT EXCL}]
    csv_row $stream {Stage Scope Token Handle GUIPath Name Score Line Toggle FSM Condition Branch}
    set failed [catch {foreach scope $p740_scopes {p740_row $scope $stream $stage}} message]
    close $stream
    if {$failed} {error $message}
    nr_counts::audit $stage
}
proc ratio763_session {} {
    global ratio_design ratio_testdirs ratio_tests
    gui_open_cov -hier $ratio_design -testdir $ratio_testdirs -test $ratio_tests -merge Ratio763Only
    set tables {}
    foreach id [gui_get_window_ids] {if {[string match CoverageTable.* $id]} {lappend tables $id}}
    if {$tables ne {CoverageTable.1}} {error "Unexpected ratio coverage table"}
    ratio763_reset
    p740_save initial-empty.el
    ratio763_stage raw
    gui_exclusion_file -load -file [list [file join $::env(DVE_COVERAGE_OUTPUT) combined.el]]
    gui_exclusion -id CoverageTable.1 -recalculate
    gui_process_events -mstime 100
    if {[gui_cov_excl_review -isEmpty] != 1} {error "Existing qualified EL needs review"}
    p740_save applied.el
    ratio763_stage applied
    ratio763_reset
    p740_save reset-empty.el
    ratio763_stage reset
    puts RATIO763_RAW_APPLIED_RESET_DONE
}
set ratio_failed [catch {ratio763_session} ratio_message]
set ratio_cleanup [catch {ratio763_reset; p740_save cleanup-empty.el} ratio_detail]
if {$ratio_failed || $ratio_cleanup} {
    set ratio_error [open [file join $::env(DVE_COVERAGE_OUTPUT) error.txt] {WRONLY CREAT EXCL}]
    puts $ratio_error "$ratio_message\ncleanup=$ratio_detail\n$::errorInfo"
    close $ratio_error
    puts "RATIO763_FAILED $ratio_message cleanup=$ratio_detail"
}
gui_exit -noprompt
