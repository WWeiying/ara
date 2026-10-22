# Legacy-core read-only successor; all GUI operations unchanged.
proc qsd_require {ok message} {if {!$ok} {error $message}}
proc qsd_name {value} {
    for {set i 0} {$i < 4 && [llength $value] == 1} {incr i} {
        set next [lindex $value 0]
        if {$next eq $value} {break}
        set value $next
    }
    return $value
}
proc qsd_emit {values} {
    global qsd_stream
    puts $qsd_stream $values
    flush $qsd_stream
}
proc qsd_clear {} {
    set raw [gui_list_get_selected -id CovDetail.1 -list cond -flat]
    set old {}
    foreach token $raw {
        set name [qsd_name $token]
        if {$name ne ""} {lappend old $name}
    }
    qsd_emit [list selected_before_clear $raw $old]
    qsd_require [expr {[llength $old] <= 4096}] "Selection bound"
    foreach name $old {gui_list_select -id CovDetail.1 -list cond -unselect [list $name]}
    set residual [gui_list_get_selected -id CovDetail.1 -list cond -flat]
    foreach token $residual {qsd_require [expr {[qsd_name $token] eq ""}] "Nonempty selection retained"}
}
proc qsd_scope {scope groups} {
    gui_cov_show_cond_ids -show 0
    gui_list_action -id CoverageTable.1 -column Condition $scope
    qsd_require [expr {[gui_covdetail_query -id CovDetail.1 -name type] eq "Condition"}] "Wrong detail type"
    qsd_clear
    set raw [gui_list_get_selected -id CovDetail.1 -list cond -all -flat]
    qsd_emit [list inventory $scope $raw]
    set actual {}
    foreach token $raw {lappend actual [qsd_name $token]}
    qsd_require [expr {[llength $actual] > 0 && [llength $actual] <= 8192 &&
        [llength [lsort -unique $actual]] == [llength $actual]}] "Empty/duplicate/unbounded inventory"
    foreach group $groups {
        qsd_require [expr {[llength $group] == 2}] "Group pair shape differs"
        set expression [lindex $group 0]
        set expected [lindex $group 1]
        qsd_require [expr {[lsearch -exact $actual $expression] >= 0}] "Expected expression absent"
        qsd_clear
        gui_list_select -id CovDetail.1 -list cond -select [list $expression]
        set selected [gui_list_get_selected -id CovDetail.1 -list cond -flat]
        qsd_require [expr {[gui_list_get_selected -id CovDetail.1 -list cond -count] == 1 &&
            [qsd_name $selected] eq $expression}] "Exact expression selection failed"
        set vectors [gui_list_get_selected -id CovDetail.1 -list vector -all -flat]
        qsd_emit [list group $scope $expression $selected $vectors]
        set names {}
        foreach token $vectors {lappend names [qsd_name $token]}
        qsd_require [expr {[llength $names] <= 3 && [lsort $names] eq [lsort $expected]}] "Truth table differs"
    }
    qsd_clear
    # Raw display is not a numeric signature or an order-based mapping.
    gui_cov_show_cond_ids -show 1
    qsd_emit [list ids_display $scope [gui_list_get_selected -id CovDetail.1 -list cond -all -flat]]
    gui_cov_show_cond_ids -show 0
    qsd_emit [list scope_complete $scope [llength $groups]]
}
proc qsd_session {} {
    global env qsd_stream qsd_design qsd_testdir qsd_test qsd_scopes
    puts [list QBS_TCL_CAPABILITIES [info patchlevel] [info tclversion] [info commands lassign] [info commands dict]]
    source $env(QBS_SIDE1792_SELECTION)
    set qsd_stream [open [file join $env(QBS_SIDE1792_OUTPUT) native-rows.tcllist] w]
    qsd_require [expr {[llength $qsd_scopes] == 2}] "Two exact scopes required"
    gui_open_cov -hier $qsd_design -testdir [list $qsd_testdir] -test [list $qsd_test] -merge QBS1792ReadOnlyDiscovery
    gui_list_expand -id CoverageTable.1 -all {<root>}
    qsd_emit [list input $qsd_design $qsd_testdir $qsd_test]
    foreach scope $qsd_scopes {qsd_scope [lindex $scope 0] [lindex $scope 1]}
    qsd_emit [list complete 1344 NATIVE_SIGNATURE_HOLD]
    close $qsd_stream
    puts QBS_SIDE1792_DISCOVERY_COMPLETE_SIGNATURE_HOLD
}
if {![info exists qsd_test_only]} {
    set failed [catch {qsd_session} message]
    if {$failed} {puts "QBS_SIDE1792_DISCOVERY_HOLD $message\n$::errorInfo"}
    if {[info exists qsd_stream]} {catch {close $qsd_stream}}
    gui_exit -noprompt
}
