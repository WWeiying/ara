source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/fsm741_transition_native.tcl}
proc apply_reviewed_waivers {id} {
    global env fx_groups fx_stream p740_scopes p740_root_names
    if {$id ne "CoverageTable.1"} {error "Wrong report table"}
    source [file join $env(DVE_COVERAGE_OUTPUT) selection.tcl]
    set deadline [expr {[clock seconds]+60}]
    while {![file exists [file join $env(DVE_COVERAGE_OUTPUT) live-ready]]} {
        if {[clock seconds] >= $deadline} {error "Live gate timed out"}
        after 100
    }
    set p740_scopes [list ara_tb.dut.i_ara_soc.i_system]
    set p740_root_names(ara_tb.dut.i_ara_soc.i_system) i_system
    set fx_stream [open [file join $env(DVE_COVERAGE_OUTPUT) exact-audit.tsv] {WRONLY CREAT EXCL}]
    set failed [catch {
        p740_save initial-empty.el
        fx_audit initial 0
        p740_summary raw
        gui_exclusion_file -load -file [list [file join $env(DVE_COVERAGE_OUTPUT) combined.el]]
        if {[gui_cov_excl_review -isEmpty] != 1} {error "Combined import unresolved"}
        gui_exclusion -id $id -recalculate
        p740_save applied.el
        fx_audit applied 1
        p740_summary applied
        gui_exclusion -reset
        p740_save reset-empty.el
        fx_audit reset 0
        p740_summary reset
        gui_exclusion_file -load -file [list [file join $env(DVE_COVERAGE_OUTPUT) applied.el]]
        if {[gui_cov_excl_review -isEmpty] != 1} {error "Combined reload unresolved"}
        gui_exclusion -id $id -recalculate
        p740_save reloaded.el
        fx_audit reloaded 1
        p740_summary reloaded
        gui_exclusion -reset
        p740_save final-empty.el
        fx_audit final 0
        p740_summary final
    } message]
    if {$failed} {puts "EXACT742_FAILED $message\n$::errorInfo"}
    set cleanup {}
    if {[catch {gui_exclusion -reset} detail]} {lappend cleanup $detail}
    if {[catch {p740_save cleanup-empty.el} detail]} {lappend cleanup $detail}
    close $fx_stream
    if {$failed || [llength $cleanup]} {error "EXACT742_FAILED $message cleanup=$cleanup"}
    puts EXACT742_FSM_OBSERVERS_DONE
}
