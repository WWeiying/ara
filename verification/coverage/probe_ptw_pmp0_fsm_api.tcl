# Help only: no loading, selecting, exclusion, reset, or coverage qualification.
set failed [catch {
    if {![info exists env(DVE_COVERAGE_OUTPUT)]} {error "Missing evidence directory"}
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) ptw-fsm-api-help.txt] w]
    puts $stream "Tcl [info patchlevel]"
    foreach command {gui_covdetail_select gui_list_select_all gui_list_get_selected gui_list_get_meta gui_list_get_value gui_dump_common_list gui_exclusion gui_cov_excl_review} {
        puts $stream "COMMAND $command"
        set bad [catch {help $command} value]
        puts $stream "HELP_STATUS $bad RESULT [list $value]"
    }
    close $stream
    puts PTW_FSM_HELP_ONLY_NOT_NATIVE_QUALIFICATION
} message]
if {$failed} {puts "PTW_FSM_HELP_FAILED $message"}
gui_exit -noprompt
