# Independent Tcl 8.4 format capture. Never imports a corpus exclusion policy.
proc op1144_require {condition message} {if {!$condition} {error $message}}
proc op1144_select {metas} {
    set old [gui_list_get_selected -id CovDetail.1 -list branch -flat]
    if {[llength $old]} {gui_list_select -id CovDetail.1 -list branch -unselect $old}
    if {[llength $metas]} {gui_list_select -id CovDetail.1 -list branch -select $metas}
    set actual [gui_list_get_selected -id CovDetail.1 -list branch -flat]
    op1144_require [expr {[lsort $actual] eq [lsort $metas]}] "Exact branch selection differs"
}
proc op1144_metadata {scope} {
    global op1144_keys
    gui_list_action -id CoverageTable.1 -column Branch $scope
    op1144_require [expr {[gui_covdetail_query -id CovDetail.1 -name type] eq "Branch"}] "Not Branch view"
    gui_list_expand -id CovDetail.1 -all {<root>}
    array set found {}
    set parent [gui_list_get -id CovDetail.1 -firstChild]
    while {$parent ne "" && $parent ne "0"} {
        set parentpath [gui_list_get -id CovDetail.1 -path $parent]
        op1144_require [regexp {^Item([0-9]+)$} $parentpath unused parentid] "Unknown branch parent"
        set item [gui_list_get -id CovDetail.1 -firstChild $parent]
        while {$item ne "" && $item ne "0"} {
            set meta [gui_list_get -id CovDetail.1 -meta $item]
            set path [gui_list_get -id CovDetail.1 -path $item]
            op1144_require [regexp {^(Branch|MISSING_ELSE)([0-9]+)\.([0-9]+)$} $meta unused kind sid vid] "Unknown leaf metadata"
            op1144_require [expr {$sid eq $parentid && $path eq "$parentpath.$meta"}] "Leaf path differs"
            op1144_require [expr {[gui_list_get -id CovDetail.1 -childCount $item] == 0}] "Not vector leaf"
            set key "$sid,$vid"
            op1144_require [expr {![info exists found($key)]}] "Duplicate vector leaf"
            set found($key) [list $meta $path]
            set item [gui_list_get -id CovDetail.1 -nextSibling $item]
        }
        set parent [gui_list_get -id CovDetail.1 -nextSibling $parent]
    }
    op1144_require [expr {[lsort [array names found]] eq [lsort $op1144_keys($scope)]}] "Full101 branch inventory differs"
    return [array get found]
}
proc op1144_audit {stage active} {
    global env op1144_scopes op1144_keys op1144_targets
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) states_$stage.tsv] w]
    puts $stream "scope\tcoordinate\tmeta\tpath\texcluded"
    set failed [catch {
        foreach scope $op1144_scopes {
            array unset metadata
            array set metadata [op1144_metadata $scope]
            foreach key $op1144_keys($scope) {
                set meta [lindex $metadata($key) 0]
                set path [lindex $metadata($key) 1]
                set wanted [expr {$active && [lsearch -exact $op1144_targets($scope) $key] >= 0}]
                op1144_select [list $meta]
                set actual [gui_exclusion -id CovDetail.1 -list branch -excluded -selected]
                op1144_require [expr {($actual eq "0" || $actual eq "1") && $actual == $wanted}] "Singleton exclusion state differs"
                puts $stream "$scope\t$key\t$meta\t$path\t$actual"
            }
        }
    } message]
    close $stream
    if {$failed} {error $message}
    puts "OP1144_AUDIT $stage 3636"
}
proc op1144_save {name {empty 0}} {
    global env
    set path [file join $env(DVE_COVERAGE_OUTPUT) $name]
    gui_exclusion_file -save -file [list $path]
    if {$empty} {op1144_require [expr {[file size $path] == 0}] "Exclusion file not empty"}
}
proc op1144_session {} {
    global env op1144_design op1144_test op1144_scopes op1144_targets
    source [file join $env(DVE_COVERAGE_OUTPUT) selection.tcl]
    puts OP1144_WAITING_FOR_LIVE_IDENTITY
    set deadline [expr {[clock seconds] + 60}]
    while {![file exists [file join $env(DVE_COVERAGE_OUTPUT) live-ready]]} {
        if {[clock seconds] >= $deadline} {error "Live executable identity gate timed out"}
        after 100
    }
    set dirs [glob -types d -directory [file join $op1144_test snps coverage db testdata] *]
    op1144_require [expr {[llength $dirs] == 1}] "Requires one selected test"
    set test [file join [file rootname $op1144_test] [file tail [lindex $dirs 0]]]
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) selected_tests.txt] w]
    puts $stream $test
    close $stream
    gui_open_cov -hier $op1144_design -testdir [list $op1144_test] -test [list $test] -merge Operand1144IdentityOnly
    gui_list_expand -id CoverageTable.1 -all {<root>}
    op1144_save initial-empty.el 1
    op1144_audit before 0
    foreach scope $op1144_scopes {
        array unset metadata
        array set metadata [op1144_metadata $scope]
        foreach key $op1144_targets($scope) {
            op1144_select [list [lindex $metadata($key) 0]]
            gui_exclude_items -id CovDetail.1 -list branch -selected -annotation {Operand parameter native discovery; exact vectors only; not application approval}
        }
    }
    gui_exclusion -id CoverageTable.1 -recalculate
    op1144_require [expr {[gui_cov_excl_review -isEmpty] == 1}] "Initial selection needs review"
    op1144_audit selected 1
    op1144_save first.el
    gui_exclusion -reset
    op1144_audit reset 0
    op1144_save reset-empty.el 1
    gui_exclusion_file -load -file [list [file join $env(DVE_COVERAGE_OUTPUT) first.el]]
    gui_exclusion -id CoverageTable.1 -recalculate
    op1144_require [expr {[gui_cov_excl_review -isEmpty] == 1}] "Roundtrip requires review"
    op1144_audit reloaded 1
    op1144_save second.el
}
if {![info exists op1144_library_only]} {
    set failed [catch {op1144_session} message]
    set cleanup {}
    if {[catch {gui_exclusion -reset} detail]} {lappend cleanup $detail}
    if {[info exists op1144_scopes]} {
        if {[catch {op1144_audit final 0} detail]} {lappend cleanup $detail}
    }
    if {[catch {op1144_save final-empty.el 1} detail]} {lappend cleanup $detail}
    if {$failed || [llength $cleanup]} {
        puts "OP1144_CAPTURE_FAILED $message cleanup=$cleanup"
    } else {puts OP1144_CAPTURE_DONE_1144}
    gui_exit -noprompt
}
