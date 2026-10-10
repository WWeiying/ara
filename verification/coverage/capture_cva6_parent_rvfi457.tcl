# Absolute sources and global plain-text selection work under DVE top-level eval.
set ::dw_test_only 1
uplevel #0 [list source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/qualify_dwc_points742.tcl}]
proc csv_row {stream values} {
    set quoted {}
    foreach value $values {lappend quoted "\"[string map [list \" \"\"] $value]\""}
    puts $stream [join $quoted ,]
}
proc cr_call {args} {
    return [eval exec [list $::cr_python -B $::cr_helper] $args [list --output $::env(DVE_COVERAGE_OUTPUT) --seal $::env(CVA6_PARENT_RVFI457_SEAL)]]
}
proc cr_walk {item stream} {
    while {$item ne "" && $item ne "0"} {
        set path [gui_list_get -id CovDetail.1 -path $item]
        set meta [gui_list_get -id CovDetail.1 -meta $item]
        set name [string trim [gui_list_get -id CovDetail.1 -text 0 $item]]
        dw_select $path $meta
        set excluded [gui_exclusion -id CovDetail.1 -excluded -selected]
        dw_need [expr {$excluded eq "0" || $excluded eq "1"}] "Nonboolean native observation"
        puts $stream [join [list $item $path $meta $name $excluded] "\t"]
        cr_walk [gui_list_get -id CovDetail.1 -firstChild $item] $stream
        set item [gui_list_get -id CovDetail.1 -nextSibling $item]
    }
}
proc cr_inventory {stage} {
    p740_root
    gui_list_action -id CoverageTable.1 -column Toggle $::cr_scope
    dw_need [expr {[gui_covdetail_query -id CovDetail.1 -name type] eq "Toggle"}] "Not native Toggle"
    gui_list_expand -id CovDetail.1 -all {<root>}
    gui_process_events -mstime 100
    set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) native_${stage}.tsv] {WRONLY CREAT EXCL}]
    puts $stream "handle\tpath\tmeta\tname\texcluded"
    set failed [catch {cr_walk [gui_list_get -id CovDetail.1 -firstChild] $stream} message]
    close $stream
    if {$failed} {error $message}
    if {$stage eq "before"} {puts [cr_call bind]} else {puts [cr_call inventory --stage $stage]}
}
proc cr_session {} {
    uplevel #0 [list source [file join $::env(DVE_COVERAGE_OUTPUT) selection.tcl]]
    foreach name {design sample test scope python helper} {
        dw_need [expr {[info exists ::cr_$name]}] "Missing global configuration: $name"
        dw_need [expr {[set ::cr_$name] ne ""}] "Empty global configuration: $name"
    }
    gui_open_cov -hier $::cr_design -testdir [list $::cr_sample] -test [list $::cr_test] -merge CVA6ParentRVFI457Only
    puts "CVA6_PARENT_RVFI457_SELECTED $::cr_test"
    set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) DVEfiles dve_gui.log] r]
    set log [read $stream]; close $stream
    if {[string first "The design '$::cr_design' was loaded successfully." $log] < 0 || [regexp {UCAPI-DLMA|DVCDT136|EK-CMD-|Load Failed|Error:|Fatal:} $log]} {error "Frozen load failed"}
    dw_save initial-empty.el 1
    cr_inventory before
    uplevel #0 [list source [file join $::env(DVE_COVERAGE_OUTPUT) actual-selection.tcl]]
    dw_need [expr {[llength $::cr_targets] == 457 && [llength [lsort -unique $::cr_targets]] == 457}] "Actual target binding incomplete"
    foreach label $::cr_targets {
        dw_select $label $label
        gui_exclude_items -id CovDetail.1 -selected -annotation {Source-proven observation-only CVA6 output leaves; full complement retained}
    }
    gui_exclusion -id CoverageTable.1 -recalculate
    dw_save first.el
    puts [cr_call el --file first.el]
    cr_inventory selected
    dw_reset
    cr_inventory reset
    dw_save reset-empty.el 1
    dw_load first.el
    cr_inventory reloaded
    dw_save second.el
    puts [cr_call el --file second.el]
    dw_reset
    cr_inventory final
    dw_save final-empty.el 1
}
if {![info exists ::cr_test_only]} {
    set failed [catch {cr_session} message]
    if {$failed} {puts "CVA6_PARENT_RVFI457_FAILED $message\n$::errorInfo"}
    set cleanup {}
    if {[catch {dw_reset} detail]} {lappend cleanup $detail}
    if {[catch {dw_save cleanup-empty.el 1} detail]} {lappend cleanup $detail}
    if {!$failed && ![llength $cleanup]} {puts CVA6_PARENT_RVFI457_NATIVE_DONE}
    if {[llength $cleanup]} {puts "CVA6_PARENT_RVFI457_FAILED cleanup=$cleanup"}
    gui_exit -noprompt
}
