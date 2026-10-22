source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/fsm741_transition_batch.tcl}
proc dwc_audit {stage} {
    global fx_groups fx_stream
    foreach group $fx_groups {
        fx_context $group
        foreach name [lindex $group 4] {
            fs_select $name
            set actual [gui_exclusion -id CovDetail.1 -list {fsm list} -excluded -selected]
            if {$actual ne "0" && $actual ne "1"} {error "Nonboolean native observation"}
            puts $fx_stream [join [list $stage [lindex $group 0] [lindex $group 2] [lindex $group 3] $name $actual] "\t"]
            flush $fx_stream
            if {($stage eq "initial" || $stage eq "reset" || $stage eq "final") && $actual ne "0"} {error "Reset not empty"}
        }
    }
}
proc dwc_session {} {
    global env dwc_design dwc_sample dwc_selected fx_groups fx_stream p740_scopes p740_root_names
    source [file join $env(DVE_COVERAGE_OUTPUT) selection.tcl]
    set env(FSM_PROBE_OUTPUT) $env(DVE_COVERAGE_OUTPUT)
    gui_open_cov -hier $dwc_design -testdir [list $dwc_sample] -test [list $dwc_selected] -merge ScalarDWC3NativeOnly
    puts "SCALAR_DWC3_SELECTED $dwc_selected"
    set f [open [file join $env(DVE_COVERAGE_OUTPUT) DVEfiles dve_gui.log] r]
    set log [read $f]; close $f
    if {[string first "The design '$dwc_design' was loaded successfully." $log] < 0 || [regexp {UCAPI-DLMA|DVCDT136|EK-CMD-|Load Failed|Error:|Fatal:} $log]} {error "Historical load failed"}
    set fx_stream [open [file join $env(DVE_COVERAGE_OUTPUT) exact-audit.tsv] {WRONLY CREAT EXCL}]
    set p740_scopes [list ara_tb.dut.i_ara_soc.i_system]
    set p740_root_names(ara_tb.dut.i_ara_soc.i_system) i_system
    fs_save initial.el 1
    dwc_audit initial
    p740_summary raw
    # Explicit transitions first, then their sole source-proven state. DVE may absorb arcs.
    foreach mode {Transition State} {
        foreach group $fx_groups {
            if {[lindex $group 3] ne $mode} {continue}
            fx_context $group
            foreach name [lindex $group 5] {
                fs_select $name
                gui_exclude_items -id CovDetail.1 -list {fsm list} -selected -annotation {Frozen configuration/source-proven FSM point; exact three-group scope}
            }
        }
    }
    gui_exclusion -id CoverageTable.1 -recalculate
    fs_save first.el
    dwc_audit applied
    p740_summary applied
    gui_exclusion -reset
    dwc_audit reset
    fs_save reset.el 1
    p740_summary reset
    gui_exclusion_file -load -file [list [file join $env(DVE_COVERAGE_OUTPUT) first.el]]
    gui_exclusion -id CoverageTable.1 -recalculate
    if {[gui_cov_excl_review -isEmpty] != 1} {error "Native import unresolved"}
    dwc_audit reloaded
    fs_save second.el
    p740_summary reloaded
    gui_exclusion -reset
    dwc_audit final
    fs_save final-empty.el 1
    p740_summary final
}
set failed [catch {dwc_session} message]
if {$failed} {puts "SCALAR_DWC3_FAILED $message\n$::errorInfo"}
set cleanup {}
if {[catch {gui_exclusion -reset} detail]} {lappend cleanup $detail}
if {[catch {fs_save cleanup-empty.el 1} detail]} {lappend cleanup $detail}
if {!$failed && ![llength $cleanup]} {puts SCALAR_DWC3_NATIVE_DONE}
if {[llength $cleanup]} {puts "SCALAR_DWC3_FAILED cleanup=$cleanup"}
gui_exit -noprompt
