# Read-only fullscope binding, Tcl8.4. No exclusion/reset/load calls.
set qc_test_only 1
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/cva6_fixed_fields_native768.tcl}
unset qc_test_only
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/apply_points740_v4.tcl}

proc mfb_session {} {
    global env mfb_design mfb_vdb mfb_test mfb_scopes qc_seen
    uplevel #0 [list source [file join $env(DVE_COVERAGE_OUTPUT) selection.tcl]]
    gui_open_cov -hier $mfb_design -testdir [list $mfb_vdb] -test [list $mfb_test] -merge MFPU272Readonly
    p740_root
    p740_save initial-empty.el
    set scopes [open [file join $env(DVE_COVERAGE_OUTPUT) scopes.tsv] w]
    puts $scopes "index\tscope\ttoken"
    set index 0
    foreach scope $mfb_scopes {
        set token [p740_select $scope]
        puts $scopes [join [list $index $scope $token] "\t"]
        flush $scopes
        gui_list_action -id CoverageTable.1 -column Toggle $token
        qc_need [expr {[gui_covdetail_query -id CovDetail.1 -name type] eq "Toggle"}] "Not Toggle"
        gui_list_expand -id CovDetail.1 -all {<root>}
        gui_process_events -mstime 100
        set columns {}; set labels {}
        for {set c 0} {$c < 32} {incr c} {
            if {[catch {gui_list_get_property -id CovDetail.1 -column $c} label]} {break}
            if {[string trim $label] ne ""} {lappend labels [string trim $label]; lappend columns $c}
        }
        qc_need [expr {$labels eq "Variable Type Coverage Display"}] "Unknown native columns $labels"
        set f [open [file join $env(DVE_COVERAGE_OUTPUT) native_before_${index}.tsv] w]
        puts $f "handle\tpath\tmeta\tname\ttype\tcoverage\tdisplay"
        set qc_seen {}
        set failed [catch {qc_walk [gui_list_get -id CovDetail.1 -firstChild] $f $columns} message]
        close $f
        if {$failed} {error $message}
        incr index
    }
    close $scopes
    p740_save final-empty.el
    puts MFPU272_READONLY_BIND_DONE
}
if {![info exists ::mfb_test_only]} {
    if {[catch {mfb_session} message]} {
        puts "MFPU272_BIND_FAILED $message"
        set f [open [file join $::env(DVE_COVERAGE_OUTPUT) error.txt] w]
        puts $f $message;puts $f $::errorInfo;close $f
    }
    gui_exit -noprompt
}
