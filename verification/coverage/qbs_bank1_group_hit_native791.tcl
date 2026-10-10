# Native capture uses established frozen UI operations, not guessed handles.
set ::dw_test_only 1
uplevel #0 [list source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/qualify_dwc_points742.tcl}]
proc bg_call {args} {
    return [eval exec [list $::bg_python -B $::bg_helper] $args [list --output $::env(DVE_COVERAGE_OUTPUT) --seal $::env(QBS_BANK1_NATIVE_SEAL)]]
}
proc bg_walk {item stream} {
    while {$item ne "" && $item ne "0"} {
        set path [gui_list_get -id CovDetail.1 -path $item]
        set meta [gui_list_get -id CovDetail.1 -meta $item]
        set name [string trim [gui_list_get -id CovDetail.1 -text 0 $item]]
        dw_select $path $meta
        set flag [gui_exclusion -id CovDetail.1 -excluded -selected]
        dw_need [expr {$flag eq "0" || $flag eq "1"}] "Nonboolean flag"
        puts $stream [join [list $item $path $meta $name $flag] "\t"]
        bg_walk [gui_list_get -id CovDetail.1 -firstChild $item] $stream
        set item [gui_list_get -id CovDetail.1 -nextSibling $item]
    }
}
proc bg_inventory {stage} {
    set index 0
    foreach scope $::bg_scopes {
        p740_root
        gui_list_action -id CoverageTable.1 -column Toggle $scope
        dw_need [expr {[gui_covdetail_query -id CovDetail.1 -name type] eq "Toggle"}] "Foreign metric"
        gui_list_expand -id CovDetail.1 -all {<root>}
        gui_process_events -mstime 100
        set f [open [file join $::env(DVE_COVERAGE_OUTPUT) native_${stage}_${index}.tsv] {WRONLY CREAT EXCL}]
        puts $f "handle\tpath\tmeta\tname\texcluded"
        set failed [catch {bg_walk [gui_list_get -id CovDetail.1 -firstChild] $f} detail]
        close $f
        if {$failed} {error $detail}
        puts [bg_call inventory --stage $stage --index $index]
        incr index
    }
}
proc bg_session {} {
    uplevel #0 [list source [file join $::env(DVE_COVERAGE_OUTPUT) selection.tcl]]
    foreach name {design sample test python helper scopes} {
        dw_need [expr {[info exists ::bg_$name] && [set ::bg_$name] ne ""}] "Missing global $name"
    }
    dw_need [expr {[llength $::bg_scopes] == 26 && [llength [lsort -unique $::bg_scopes]] == 26}] "Exact subtree"
    set deadline [expr {[clock seconds]+30}]
    while {![file exists [file join $::env(DVE_COVERAGE_OUTPUT) live-ready]]} {
        if {[clock seconds] >= $deadline} {error "Actual owning executable proof missing"}
        after 100
    }
    puts [bg_call check]
    gui_open_cov -hier $::bg_design -testdir [list $::bg_sample] -test [list $::bg_test] -merge QBSBank1GroupHitOnly
    dw_save initial-empty.el 1
    puts [bg_call el --stage before]
    bg_inventory before
    puts [bg_call bind]
    dw_load actual-candidate.el
    dw_save first.el
    puts [bg_call el --stage selected]
    bg_inventory selected
    dw_reset
    dw_save reset-empty.el 1
    puts [bg_call el --stage reset]
    bg_inventory reset
    dw_load first.el
    dw_save second.el
    puts [bg_call el --stage reloaded]
    bg_inventory reloaded
    dw_reset
    dw_save final-empty.el 1
    puts [bg_call el --stage final]
    bg_inventory final
}
if {![info exists ::bg_test_only]} {
    set failed [catch {bg_session} detail]
    if {$failed} {
        set f [open [file join $::env(DVE_COVERAGE_OUTPUT) error.txt] w]
        puts $f "$detail\n$::errorInfo"; close $f
        puts "QBS_BANK1_GROUP_HIT_NATIVE_FAILED $detail"
    }
    set cleanup [catch {dw_reset; dw_save cleanup-empty.el 1} detail]
    if {$cleanup} {puts "QBS_BANK1_GROUP_HIT_NATIVE_FAILED cleanup $detail"}
    if {!$failed && !$cleanup} {puts QBS_BANK1_GROUP_HIT_NATIVE_DONE}
    gui_exit -noprompt
}
