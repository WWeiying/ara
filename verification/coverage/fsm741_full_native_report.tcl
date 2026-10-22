source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/fsm741_transition_native.tcl}
proc fx_session {} {
    global env fx_groups fx_stream p740_scopes p740_root_names
    source [file join $env(DVE_COVERAGE_OUTPUT) selection.tcl]
    set deadline [expr {[clock seconds]+60}]
    while {![file exists [file join $env(DVE_COVERAGE_OUTPUT) live-ready]]} {
        if {[clock seconds] >= $deadline} {error "Live gate timed out"}
        after 100
    }
    set fx_stream [open [file join $env(DVE_COVERAGE_OUTPUT) exact-audit.tsv] {WRONLY CREAT EXCL}]
    set p740_scopes [list ara_tb.dut.i_ara_soc.i_system]
    set p740_root_names(ara_tb.dut.i_ara_soc.i_system) i_system
    fs_save initial.el 1
    fx_audit initial 0
    p740_summary raw
    gui_exclusion_file -load -file [list {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/fsm741-transition66-native-20261007-02/first.el}]
    if {[gui_cov_excl_review -isEmpty] != 1} {error "Qualified native import unresolved"}
    gui_exclusion -id CoverageTable.1 -recalculate
    fs_save first.el
    fx_audit applied 1
    p740_summary applied
    gui_exclusion -reset
    fx_audit reset 0
    fs_save reset.el 1
    p740_summary reset
    gui_exclusion_file -load -file [list [file join $env(DVE_COVERAGE_OUTPUT) first.el]]
    if {[gui_cov_excl_review -isEmpty] != 1} {error "Native roundtrip unresolved"}
    gui_exclusion -id CoverageTable.1 -recalculate
    fx_audit reloaded 1
    fs_save second.el
    p740_summary reloaded
    gui_exclusion -reset
    fx_audit final 0
    fs_save final-empty.el 1
    p740_summary final
}
