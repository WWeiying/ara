source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/fsm741_transition_native.tcl}
proc combo_walk {item stream} {
    while {$item ne "" && $item ne "0"} {
        puts $stream [join [list $item [gui_list_get -id CovDetail.1 -path $item] [gui_list_get -id CovDetail.1 -meta $item] [string trim [gui_list_get -id CovDetail.1 -text 0 $item]]] "\t"]
        combo_walk [gui_list_get -id CovDetail.1 -firstChild $item] $stream
        set item [gui_list_get -id CovDetail.1 -nextSibling $item]
    }
}
proc combo_inventory {stage} {
    foreach group $::combo_groups {
        p740_root
        gui_list_action -id CoverageTable.1 -column Toggle [lindex $group 0]
        if {[gui_covdetail_query -id CovDetail.1 -name type] ne "Toggle"} {error "Wrong native metric"}
        gui_list_expand -id CovDetail.1 -all {<root>}
        gui_process_events -mstime 100
        set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) combo_${stage}_[lindex $group 1].tsv] {WRONLY CREAT EXCL}]
        puts $stream "handle\tpath\tmeta\tname"
        combo_walk [gui_list_get -id CovDetail.1 -firstChild] $stream
        close $stream
    }
}
proc combo_reset {} {
    gui_exclusion -reset
    gui_exclusion -id CoverageTable.1 -recalculate
    gui_process_events -mstime 100
}
proc combo_audit {stage mode active} {
    fx_audit $stage $active
    combo_inventory $mode
    if {$::combo_has_dwc} {dw_audit $mode $active}
}
proc combo_load {name} {
    gui_exclusion_file -load -file [list [file join $::env(DVE_COVERAGE_OUTPUT) $name]]
    gui_exclusion -id CoverageTable.1 -recalculate
    if {[gui_cov_excl_review -isEmpty] != 1} {error "Unresolved native import"}
}
proc apply_reviewed_waivers {id} {
    global env fx_groups fx_stream p740_scopes p740_root_names combo_groups combo_has_dwc dw_groups dw_toggles dw_stream
    if {$id ne "CoverageTable.1"} {error "Wrong table"}
    source [file join $env(DVE_COVERAGE_OUTPUT) selection.tcl]
    set deadline [expr {[clock seconds]+60}]
    while {![file exists [file join $env(DVE_COVERAGE_OUTPUT) live-ready]]} {
        if {[clock seconds] >= $deadline} {error "Live gate timeout"}
        after 100
    }
    if {$combo_has_dwc} {
        set ::dw_test_only 1
        source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/qualify_dwc_points742.tcl}
        set dw_stream [open [file join $env(DVE_COVERAGE_OUTPUT) dwc-audit.tsv] {WRONLY CREAT EXCL}]
    }
    set p740_scopes [list ara_tb.dut.i_ara_soc.i_system]
    set p740_root_names(ara_tb.dut.i_ara_soc.i_system) i_system
    set fx_stream [open [file join $env(DVE_COVERAGE_OUTPUT) exact-audit.tsv] {WRONLY CREAT EXCL}]
    set failed [catch {
        p740_save initial-empty.el
        combo_audit initial before 0
        p740_summary raw
        combo_load combined.el
        combo_audit applied selected 1
        p740_save applied.el
        p740_summary applied
        combo_reset
        combo_audit reset reset 0
        p740_save reset-empty.el
        p740_summary reset
        combo_load applied.el
        combo_audit reloaded reloaded 1
        p740_save reloaded.el
        p740_summary reloaded
        combo_reset
        combo_audit final final 0
        p740_save final-empty.el
        p740_summary final
    } message]
    if {$failed} {
        set stream [open [file join $env(DVE_COVERAGE_OUTPUT) error.txt] w]
        puts $stream "$message\n$::errorInfo"
        close $stream
    }
    set cleanup [catch {combo_reset; p740_save cleanup-empty.el} detail]
    close $fx_stream
    if {$combo_has_dwc} {close $dw_stream}
    if {$failed || $cleanup} {error "COMBO742_FAILED $message cleanup=$detail"}
    puts COMBO742_NATIVE_DONE
}
