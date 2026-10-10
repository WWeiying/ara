# Exact native Toggle objects, no module/instance exclusion.
set dw_test_only 1
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/qualify_dwc_points742.tcl}
proc rvfi_walk {item stream} {
    global rvfi_rows rvfi_targets
    while {$item ne "" && $item ne "0"} {
        set path [gui_list_get -id CovDetail.1 -path $item]
        set meta [gui_list_get -id CovDetail.1 -meta $item]
        set name [string trim [gui_list_get -id CovDetail.1 -text 0 $item]]
        dw_select $path $meta
        set excluded [gui_exclusion -id CovDetail.1 -excluded -selected]
        dw_need [expr {$excluded eq "0" || $excluded eq "1"}] "Nonboolean native observation"
        puts $stream [join [list $item $path $meta $name $excluded] "\t"]
        foreach target $rvfi_targets {
            if {$meta eq $target || $name eq $target} {lappend rvfi_rows [list $path $meta $target]}
        }
        rvfi_walk [gui_list_get -id CovDetail.1 -firstChild $item] $stream
        set item [gui_list_get -id CovDetail.1 -nextSibling $item]
    }
}
proc rvfi_validate_rows {rows targets} {
    set found {}
    foreach row $rows {lappend found [lindex $row 2]}
    dw_need [expr {[llength $targets] == 788 && [lsort $found] eq [lsort $targets]}] "Missing/duplicate/foreign native target"
}
proc rvfi_bind {stage} {
    global env rvfi_scope rvfi_rows rvfi_targets rvfi_python rvfi_helper
    p740_root
    gui_list_action -id CoverageTable.1 -column Toggle $rvfi_scope
    dw_need [expr {[gui_covdetail_query -id CovDetail.1 -name type] eq "Toggle"}] "Not native Toggle"
    gui_list_expand -id CovDetail.1 -all {<root>}
    gui_process_events -mstime 100
    set rvfi_rows {}
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) native_${stage}.tsv] {WRONLY CREAT EXCL}]
    puts $stream "handle\tpath\tmeta\tname\texcluded"
    set failed [catch {rvfi_walk [gui_list_get -id CovDetail.1 -firstChild] $stream} message]
    close $stream
    if {$failed} {error $message}
    rvfi_validate_rows $rvfi_rows $rvfi_targets
    puts [exec $rvfi_python -B $rvfi_helper inventory --output $env(DVE_COVERAGE_OUTPUT) --stage $stage]
    return $rvfi_rows
}
proc rvfi_check_el {name} {
    global env rvfi_python rvfi_helper
    puts [exec $rvfi_python -B $rvfi_helper el --output $env(DVE_COVERAGE_OUTPUT) --file $name]
}
proc rvfi_session {} {
    global env rvfi_design rvfi_sample rvfi_test
    source [file join $env(DVE_COVERAGE_OUTPUT) selection.tcl]
    gui_open_cov -hier $rvfi_design -testdir [list $rvfi_sample] -test [list $rvfi_test] -merge ParentRVFI788NativeOnly
    puts "SYSTEM_RVFI788_SELECTED $rvfi_test"
    set f [open [file join $env(DVE_COVERAGE_OUTPUT) DVEfiles dve_gui.log] r]
    set log [read $f]; close $f
    if {[string first "The design '$rvfi_design' was loaded successfully." $log] < 0 || [regexp {UCAPI-DLMA|DVCDT136|EK-CMD-|Load Failed|Error:|Fatal:} $log]} {error "Historical load failed"}
    dw_save initial-empty.el 1
    set rows [rvfi_bind before]
    foreach row $rows {
        dw_select [lindex $row 0] [lindex $row 1]
        gui_exclude_items -id CovDetail.1 -selected -annotation {Observation-only parent RVFI net; full typed complements retained}
    }
    gui_exclusion -id CoverageTable.1 -recalculate
    dw_save first.el
    rvfi_check_el first.el
    rvfi_bind selected
    dw_reset
    rvfi_bind reset
    dw_save reset-empty.el 1
    dw_load first.el
    rvfi_bind reloaded
    dw_save second.el
    rvfi_check_el second.el
    dw_reset
    rvfi_bind final
    dw_save final-empty.el 1
}
if {![info exists rvfi_test_only]} {
    set failed [catch {rvfi_session} message]
    if {$failed} {puts "SYSTEM_RVFI788_FAILED $message\n$::errorInfo"}
    set cleanup {}
    if {[catch {dw_reset} detail]} {lappend cleanup $detail}
    if {[catch {dw_save cleanup-empty.el 1} detail]} {lappend cleanup $detail}
    if {!$failed && ![llength $cleanup]} {puts SYSTEM_RVFI788_NATIVE_DONE}
    if {[llength $cleanup]} {puts "SYSTEM_RVFI788_FAILED cleanup=$cleanup"}
    gui_exit -noprompt
}
