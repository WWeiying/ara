# Tcl8.4; explicit five-code-metric commands, never recursive or Assert/Group.
proc cv_need {ok why} {if {!$ok} {error $why}}
proc cv_save {name} {
    gui_exclusion_file -save -file [list [file join $::env(DVE_COVERAGE_OUTPUT) $name]]
}
proc cv_reset {} {
    gui_exclusion -reset
    gui_exclusion -id CoverageTable.1 -recalculate
    gui_process_events -mstime 100
}
proc cv_select_detail {path meta} {
    set old [gui_list_get_selected -id CovDetail.1 -flat]
    if {[llength $old]} {gui_list_select -id CovDetail.1 -unselect [lindex $old 0]}
    gui_list_select -id CovDetail.1 -select [list $path]
    set selected [gui_list_get_selected -id CovDetail.1 -meta -flat]
    cv_need [expr {[llength $selected] == 1 && [llength [lindex $selected 0]] == 1 && [lindex [lindex $selected 0] 0] eq $meta}] "Native detail selection identity"
}
proc cv_walk {item stream columns} {
    while {$item ne "" && $item ne "0"} {
        set path [gui_list_get -id CovDetail.1 -path $item]
        set meta [gui_list_get -id CovDetail.1 -meta $item]
        set name [string trim [gui_list_get -id CovDetail.1 -text 0 $item]]
        cv_select_detail $path $meta
        set excluded [gui_exclusion -id CovDetail.1 -excluded -selected]
        cv_need [expr {$excluded eq "0" || $excluded eq "1"}] "Non-Boolean native exclusion"
        set cells {}
        foreach c $columns {lappend cells [string trim [gui_list_get -id CovDetail.1 -text $c $item]]}
        foreach value [list $path $meta $name $cells] {
            cv_need [expr {[string first "\t" $value] < 0 && [string first "\n" $value] < 0}] "Multiline snapshot cell"
        }
        puts $stream [join [list $path $meta $name $excluded $cells] "\t"]
        cv_walk [gui_list_get -id CovDetail.1 -firstChild $item] $stream $columns
        set item [gui_list_get -id CovDetail.1 -nextSibling $item]
    }
}
proc cv_snapshot {stage metric index scope} {
    p740_root
    p740_select $scope
    gui_list_action -id CoverageTable.1 -column $metric $scope
    cv_need [expr {[gui_covdetail_query -id CovDetail.1 -name type] eq $metric}] "Metric detail identity differs: $metric"
    gui_list_expand -id CovDetail.1 -all {<root>}
    gui_process_events -mstime 100
    set columns {}; set labels {}
    for {set c 0} {$c < 32} {incr c} {
        if {[catch {gui_list_get_property -id CovDetail.1 -column $c} label]} {break}
        if {[string trim $label] ne ""} {lappend columns $c; lappend labels [string trim $label]}
    }
    cv_need [expr {[llength $columns] > 0}] "No native snapshot columns"
    set header [open [file join $::env(DVE_COVERAGE_OUTPUT) ${stage}_${metric}_${index}.columns] {WRONLY CREAT EXCL}]
    puts $header $labels; close $header
    set f [open [file join $::env(DVE_COVERAGE_OUTPUT) ${stage}_${metric}_${index}.tsv] {WRONLY CREAT EXCL}]
    puts $f "path\tmeta\tname\texcluded\tcells"
    set failed [catch {cv_walk [gui_list_get -id CovDetail.1 -firstChild] $f $columns} message]
    close $f
    if {$failed} {error $message}
}
proc cv_audit {stage} {
    set availability {}
    foreach metric {Line Condition Branch FSM Toggle Assert Group} {
        # An unsupported query is HOLD, not an invented absent metric.
        set loaded [gui_has_metric -metric $metric]
        cv_need [expr {$loaded eq "0" || $loaded eq "1"}] "Unknown loaded metric status: $metric"
        if {$loaded} {set boolean true} else {set boolean false}
        lappend availability "\"$metric\":$boolean"
        if {[lsearch -exact {Assert Group} $metric] < 0} {
            cv_need $loaded "Required code metric absent: $metric"
            set i 0
            foreach scope $::cv_scopes {cv_snapshot $stage $metric $i $scope; incr i}
        } elseif {$loaded} {
            # Cumulative product root protects assertions and functional coverage.
            cv_snapshot $stage $metric 0 $::cv_root
        }
    }
    set f [open [file join $::env(DVE_COVERAGE_OUTPUT) ${stage}_availability.json] {WRONLY CREAT EXCL}]
    puts $f "\{[join $availability ,]\}"; close $f
}
proc cv_apply {} {
    foreach scope $::cv_scopes {
        foreach metric {Line Condition Branch FSM Toggle} {
            p740_root
            p740_select $scope
            # Native help and installed metricExclude.tcl establish this command.
            gui_exclude_items -id CoverageTable.1 -selected -metric $metric -annotation $::cv_annotation
        }
    }
    gui_exclusion -id CoverageTable.1 -recalculate
    gui_process_events -mstime 100
    cv_need [expr {[gui_cov_excl_review -isEmpty] == 1}] "Native exclusions need review"
}
proc cv_session {} {
    global cv_design cv_vdb cv_test cv_root cv_scopes cv_library cv_annotation
    uplevel #0 [list source [file join $::env(DVE_COVERAGE_OUTPUT) selection.tcl]]
    uplevel #0 [list source $cv_library]
    cv_need [expr {[llength $cv_scopes] == 2}] "Exact two scopes required"
    help gui_exclude_items
    help gui_exclusion_file
    gui_open_cov -hier $cv_design -testdir [list $cv_vdb] -test [list $cv_test] -merge PassiveTwoScopeOnly
    cv_save initial-empty.el
    cv_audit before
    cv_apply
    cv_audit selected
    cv_save first.el
    cv_reset
    cv_audit reset
    cv_save reset-empty.el
    gui_exclusion_file -load -file [list [file join $::env(DVE_COVERAGE_OUTPUT) first.el]]
    gui_exclusion -id CoverageTable.1 -recalculate
    gui_process_events -mstime 100
    cv_need [expr {[gui_cov_excl_review -isEmpty] == 1}] "Reload needs review"
    cv_audit reloaded
    cv_save second.el
    cv_reset
    cv_audit final
    cv_save final-empty.el
    puts CVXIF_TWO_SCOPE_DONE
}
if {![info exists ::cv_test_only]} {
    if {[catch {cv_session} message]} {
        puts "CVXIF_TWO_SCOPE_FAILED $message"
        set f [open [file join $::env(DVE_COVERAGE_OUTPUT) error.txt] {WRONLY CREAT EXCL}]
        puts $f $message; puts $f $::errorInfo; close $f
        if {[catch {cv_reset; cv_save cleanup-empty.el} cleanup]} {puts "CVXIF_CLEANUP_FAILED $cleanup"}
    }
    gui_exit -noprompt
}
