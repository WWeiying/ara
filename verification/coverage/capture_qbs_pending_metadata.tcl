# Tcl 8.4. Exact Branch leaves only; no hierarchy-wide exclusions.
set dbg_library_only 1
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/capture_operand_debug.tcl}
proc dbg_options {metric} {
    dbg_require [expr {$metric eq "branch"}] "Only Branch allowed"
    return [list -list branch]
}
proc qbs_metadata {scope} {
    global qbs_native_keys
    gui_list_action -id CoverageTable.1 -column Branch $scope
    dbg_require [expr {[gui_covdetail_query -id CovDetail.1 -name type] eq "Branch"}] "Wrong detail type"
    gui_list_expand -id CovDetail.1 -all {<root>}
    array set found {}
    set parent [gui_list_get -id CovDetail.1 -firstChild]
    while {$parent ne "" && $parent ne "0"} {
        set parentpath [gui_list_get -id CovDetail.1 -path $parent]
        dbg_require [regexp {^Item([0-9]+)$} $parentpath unused parentid] "Unknown parent scope=$scope path=$parentpath"
        set item [gui_list_get -id CovDetail.1 -firstChild $parent]
        while {$item ne "" && $item ne "0"} {
            set meta [gui_list_get -id CovDetail.1 -meta $item]
            set path [gui_list_get -id CovDetail.1 -path $item]
            set children [gui_list_get -id CovDetail.1 -childCount $item]
            dbg_require [regexp {^(Branch|MISSING_ELSE|MISSING_DEFAULT)([0-9]+)\.([0-9]+)$} $meta unused kind sid vid] "Unknown leaf scope=$scope meta=$meta path=$path children=$children"
            dbg_require [expr {$sid eq $parentid && $path eq "$parentpath.$meta" && $children == 0}] "Leaf binding differs scope=$scope meta=$meta path=$path"
            set key "$sid,$vid"
            dbg_require [expr {![info exists found($key)]}] "Duplicate vector"
            set found($key) [list $meta $path]
            set item [gui_list_get -id CovDetail.1 -nextSibling $item]
        }
        set parent [gui_list_get -id CovDetail.1 -nextSibling $parent]
    }
    dbg_require [expr {[lsort [array names found]] eq [lsort $qbs_native_keys($scope)]}] "Complete native/compiled inventory differs scope=$scope"
    puts "QBS_NATIVE_INVENTORY $scope [array size found]"
    return [array get found]
}
proc qbs_audit {stage active} {
    global env dbg_scopes dbg_targets qbs_audit_keys
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) states_$stage.tsv] w]
    puts $stream "scope\tmetric\tcoordinate\tmeta\tpath\texcluded"
    set count 0
    set failed [catch {
        foreach scope $dbg_scopes {
            array unset metadata
            array set metadata [qbs_metadata $scope]
            foreach key $qbs_audit_keys($scope) {
                set meta [lindex $metadata($key) 0]
                set path [lindex $metadata($key) 1]
                dbg_select branch $meta
                set actual [gui_exclusion -id CovDetail.1 -list branch -excluded -selected]
                set wanted [expr {$active && [lsearch -exact $dbg_targets($scope|branch) $key] >= 0}]
                dbg_require [expr {($actual eq "0" || $actual eq "1") && $actual == $wanted}] "Singleton differs stage=$stage scope=$scope key=$key actual=$actual wanted=$wanted"
                puts $stream "$scope\tbranch\t$key\t$meta\t$path\t$actual"
                incr count
            }
        }
    } message]
    close $stream
    if {$failed} {error $message}
    puts "QBS_AUDIT $stage $count"
}
proc qbs_session {} {
    global env dbg_design dbg_test dbg_scopes dbg_targets dbg_python dbg_driver qbs_native_keys qbs_audit_keys
    source [file join $env(DVE_COVERAGE_OUTPUT) selection.tcl]
    set deadline [expr {[clock seconds] + 60}]
    while {![file exists [file join $env(DVE_COVERAGE_OUTPUT) live-ready]]} {
        if {[clock seconds] >= $deadline} {error "Live identity gate timed out"}
        after 100
    }
    set dirs [glob -types d -directory [file join $dbg_test snps coverage db testdata] *]
    dbg_require [expr {[llength $dirs] == 1}] "Exactly one historical PASS sample required"
    set test [file join [file rootname $dbg_test] [file tail [lindex $dirs 0]]]
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) selected_tests.txt] w]
    puts $stream $test
    close $stream
    gui_open_cov -hier $dbg_design -testdir [list $dbg_test] -test [list $test] -merge QBSPendingNativeQualificationOnly
    gui_list_expand -id CoverageTable.1 -all {<root>}
    dbg_save initial-empty.el 1
    qbs_audit before 0
    foreach scope $dbg_scopes {
        array unset metadata
        array set metadata [qbs_metadata $scope]
        foreach key $dbg_targets($scope|branch) {
            dbg_select branch [lindex $metadata($key) 0]
            gui_exclude_items -id CovDetail.1 -list branch -selected -annotation {Reviewed QBS pending metadata older path; native qualification only; not aggregate approval}
        }
    }
    gui_exclusion -id CoverageTable.1 -recalculate
    dbg_require [expr {[gui_cov_excl_review -isEmpty] == 1}] "Selection requires review"
    qbs_audit selected 1
    dbg_save first.el
    puts [exec $dbg_python -B $dbg_driver first --output $env(DVE_COVERAGE_OUTPUT) --seal $env(DEBUG_CAPTURE_SEAL)]
    gui_exclusion -reset
    qbs_audit reset 0
    dbg_save reset-empty.el 1
    gui_exclusion_file -load -file [list [file join $env(DVE_COVERAGE_OUTPUT) first.el]]
    gui_exclusion -id CoverageTable.1 -recalculate
    dbg_require [expr {[gui_cov_excl_review -isEmpty] == 1}] "Reload requires review"
    qbs_audit reloaded 1
    dbg_save second.el
}
set failed [catch {qbs_session} message]
if {$failed} {puts "QBS_SESSION_ERROR $message\n$::errorInfo"}
set cleanup {}
if {[catch {gui_exclusion -reset} detail]} {lappend cleanup $detail}
if {[info exists dbg_scopes]} {
    if {[catch {qbs_audit final 0} detail]} {lappend cleanup $detail}
}
if {[catch {dbg_save final-empty.el 1} detail]} {lappend cleanup $detail}
if {$failed || [llength $cleanup]} {puts "DBG_CAPTURE_FAILED $message cleanup=$cleanup"} else {puts DBG_CAPTURE_DONE}
gui_exit -noprompt
