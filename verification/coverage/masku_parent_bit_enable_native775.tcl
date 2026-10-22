# Prepared only. Global plain-text source; no relative info-script lookup.
set ::dw_test_only 1
uplevel #0 [list source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/qualify_dwc_points742.tcl}]
proc re_call {args} {
    return [eval exec [list $::re_python -B $::re_helper] $args [list --output $::env(DVE_COVERAGE_OUTPUT) --seal $::env(MASKU_PARENT_ONLY_SEAL)]]
}
proc re_walk {item stream} {
    while {$item ne "" && $item ne "0"} {
        set path [gui_list_get -id CovDetail.1 -path $item]
        set meta [gui_list_get -id CovDetail.1 -meta $item]
        set name [string trim [gui_list_get -id CovDetail.1 -text 0 $item]]
        dw_select $path $meta
        set flag [gui_exclusion -id CovDetail.1 -excluded -selected]
        dw_need [expr {$flag eq "0" || $flag eq "1"}] "Nonboolean native observation"
        puts $stream [join [list $item $path $meta $name $flag] "\t"]
        re_walk [gui_list_get -id CovDetail.1 -firstChild $item] $stream
        set item [gui_list_get -id CovDetail.1 -nextSibling $item]
    }
}
proc re_inventory {stage} {
    set index 0
    foreach scope $::re_scopes {
        p740_root
        gui_list_action -id CoverageTable.1 -column Toggle $scope
        dw_need [expr {[gui_covdetail_query -id CovDetail.1 -name type] eq "Toggle"}] "Not native Toggle"
        gui_list_expand -id CovDetail.1 -all {<root>}
        gui_process_events -mstime 100
        set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) native_${stage}_${index}.tsv] {WRONLY CREAT EXCL}]
        puts $stream "handle\tpath\tmeta\tname\texcluded"
        set failed [catch {re_walk [gui_list_get -id CovDetail.1 -firstChild] $stream} message]
        close $stream
        if {$failed} {error $message}
        puts [re_call inventory --stage $stage --index $index]
        incr index
    }
}
proc re_session {} {
    uplevel #0 [list source [file join $::env(DVE_COVERAGE_OUTPUT) selection.tcl]]
    foreach name {design sample test python helper scopes} {
        dw_need [expr {[info exists ::re_$name]}] "Missing global configuration: $name"
        dw_need [expr {[set ::re_$name] ne ""}] "Empty global configuration: $name"
    }
    dw_need [expr {[llength $::re_scopes] == 26 && [llength [lsort -unique $::re_scopes]] == 26}] "Exact26 scopes required"
    gui_open_cov -hier $::re_design -testdir [list $::re_sample] -test [list $::re_test] -merge MaskuParentOnly
    set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) DVEfiles dve_gui.log] r]
    set log [read $stream]; close $stream
    if {[string first "The design '$::re_design' was loaded successfully." $log] < 0 || [regexp {UCAPI-DLMA|DVCDT136|EK-CMD-|Load Failed|Error:|Fatal:} $log]} {error "Frozen load failed"}
    dw_save initial-empty.el 1
    puts [re_call el --stage before]
    re_inventory before
    puts [re_call bind]
    puts [re_call selection]
    uplevel #0 [list source [file join $::env(DVE_COVERAGE_OUTPUT) actual-selection.tcl]]
    set total 0; set index 0
    foreach scope $::re_scopes {
        dw_need [info exists ::re_targets($index)] "Missing actual target binding"
        p740_root
        gui_list_action -id CoverageTable.1 -column Toggle $scope
        foreach label $::re_targets($index) {
            dw_select $label $label
            gui_exclude_items -id CovDetail.1 -selected -annotation {Frozen VlBitMaskEnable0 parent internal bit_enable_mask only; no startup X exclusion; ports and all complements protected}
            incr total
        }
        incr index
    }
    dw_need [expr {$total == 1}] "Exact parent target only"
    gui_exclusion -id CoverageTable.1 -recalculate
    dw_save first.el
    puts [re_call el --stage selected]
    re_inventory selected
    dw_reset
    dw_save reset-empty.el 1
    puts [re_call el --stage reset]
    re_inventory reset
    dw_load first.el
    dw_save second.el
    puts [re_call el --stage reloaded]
    re_inventory reloaded
    dw_reset
    dw_save final-empty.el 1
    puts [re_call el --stage final]
    re_inventory final
}
if {![info exists ::re_test_only]} {
    set failed [catch {re_session} message]
    if {$failed} {
        set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) error.txt] w]
        puts $stream "$message\n$::errorInfo"; close $stream
        puts "MASKU_PARENT_ONLY_FAILED $message\n$::errorInfo"
    }
    set cleanup {}
    if {[catch {dw_reset} detail]} {lappend cleanup $detail}
    if {[catch {dw_save cleanup-empty.el 1} detail]} {lappend cleanup $detail}
    if {!$failed && ![llength $cleanup]} {puts MASKU_PARENT_ONLY_NATIVE_DONE}
    if {[llength $cleanup]} {puts "MASKU_PARENT_ONLY_FAILED cleanup=$cleanup"}
    gui_exit -noprompt
}
