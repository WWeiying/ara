# Tcl 8.4: branch-only. Absolute frozen helper, no Line or Condition commands.
set dbg_library_only 1
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/capture_operand_debug.tcl}
foreach helper {dbg_select dbg_save dbg_require} {
    if {[llength [info commands $helper]] != 1} {error "Missing pinned helper $helper"}
}
proc dbg_options {metric} {
    dbg_require [expr {$metric eq "branch"}] "Only Branch allowed"
    return [list -list branch]
}
proc dbg_metadata {scope metric} {
    global dbg_keys
    dbg_require [expr {$metric eq "branch"}] "Only Branch allowed"
    gui_list_action -id CoverageTable.1 -column Branch $scope
    dbg_require [expr {[gui_covdetail_query -id CovDetail.1 -name type] eq "Branch"}] "Wrong detail type"
    gui_list_expand -id CovDetail.1 -all {<root>}
    array set found {}
    set parent [gui_list_get -id CovDetail.1 -firstChild]
    while {$parent ne "" && $parent ne "0"} {
        set parentpath [gui_list_get -id CovDetail.1 -path $parent]
        dbg_require [regexp {^Item([0-9]+)$} $parentpath unused parentid] "Unknown native parent scope=$scope path=$parentpath"
        set item [gui_list_get -id CovDetail.1 -firstChild $parent]
        while {$item ne "" && $item ne "0"} {
            set meta [gui_list_get -id CovDetail.1 -meta $item]
            set path [gui_list_get -id CovDetail.1 -path $item]
            set children [gui_list_get -id CovDetail.1 -childCount $item]
            dbg_require [regexp {^(Branch|MISSING_ELSE|MISSING_DEFAULT)([0-9]+)\.([0-9]+)$} $meta unused kind sid vid] "Unknown native leaf scope=$scope parent=$parentpath meta=$meta path=$path children=$children"
            dbg_require [expr {$sid eq $parentid && $path eq "$parentpath.$meta" && $children == 0}] "Native leaf binding differs scope=$scope meta=$meta path=$path"
            set key "$sid,$vid"
            dbg_require [expr {![info exists found($key)]}] "Duplicate vector scope=$scope key=$key"
            set found($key) [list $meta $path]
            set item [gui_list_get -id CovDetail.1 -nextSibling $item]
        }
        set parent [gui_list_get -id CovDetail.1 -nextSibling $parent]
    }
    dbg_require [expr {[lsort [array names found]] eq [lsort $dbg_keys($scope|branch)]}] "Complete native/compiled branch inventory differs scope=$scope"
    puts "DBG_BRANCH_INVENTORY $scope [array size found]"
    return [array get found]
}
proc dbg_audit {stage active} {
    global env dbg_scopes dbg_keys dbg_targets
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) states_$stage.tsv] w]
    puts $stream "scope\tmetric\tcoordinate\tmeta\tpath\texcluded"
    set count 0
    set failed [catch {
        foreach scope $dbg_scopes {
            array unset metadata
            array set metadata [dbg_metadata $scope branch]
            foreach key $dbg_keys($scope|branch) {
                set meta [lindex $metadata($key) 0]
                set path [lindex $metadata($key) 1]
                dbg_select branch $meta
                set actual [gui_exclusion -id CovDetail.1 -list branch -excluded -selected]
                set wanted [expr {$active && [lsearch -exact $dbg_targets($scope|branch) $key] >= 0}]
                dbg_require [expr {($actual eq "0" || $actual eq "1") && $actual == $wanted}] "Singleton differs stage=$stage scope=$scope key=$key meta=$meta actual=$actual wanted=$wanted"
                puts $stream "$scope\tbranch\t$key\t$meta\t$path\t$actual"
                incr count
            }
        }
    } message]
    close $stream
    if {$failed} {error $message}
    puts "DBG_AUDIT $stage $count"
}
proc dbg_session {} {
    global env dbg_design dbg_test dbg_scopes dbg_targets dbg_python dbg_driver
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
    gui_open_cov -hier $dbg_design -testdir [list $dbg_test] -test [list $test] -merge OperandDebugBranchQualificationOnly
    gui_list_expand -id CoverageTable.1 -all {<root>}
    dbg_save initial-empty.el 1
    dbg_audit before 0
    foreach scope $dbg_scopes {
        array unset metadata
        array set metadata [dbg_metadata $scope branch]
        foreach key $dbg_targets($scope|branch) {
            dbg_select branch [lindex $metadata($key) 0]
            gui_exclude_items -id CovDetail.1 -list branch -selected -annotation {Reviewed operand debug instrumentation; native qualification only; not aggregate approval}
        }
    }
    gui_exclusion -id CoverageTable.1 -recalculate
    dbg_require [expr {[gui_cov_excl_review -isEmpty] == 1}] "Selection requires review"
    dbg_audit selected 1
    dbg_save first.el
    puts [exec $dbg_python -B $dbg_driver first --output $env(DVE_COVERAGE_OUTPUT) --seal $env(DEBUG_CAPTURE_SEAL)]
    gui_exclusion -reset
    dbg_audit reset 0
    dbg_save reset-empty.el 1
    gui_exclusion_file -load -file [list [file join $env(DVE_COVERAGE_OUTPUT) first.el]]
    gui_exclusion -id CoverageTable.1 -recalculate
    dbg_require [expr {[gui_cov_excl_review -isEmpty] == 1}] "Reload requires review"
    dbg_audit reloaded 1
    dbg_save second.el
}
set failed [catch {dbg_session} message]
if {$failed} {puts "DBG_SESSION_ERROR $message\n$::errorInfo"}
set cleanup {}
if {[catch {gui_exclusion -reset} detail]} {lappend cleanup $detail}
if {[info exists dbg_scopes]} {
    if {[catch {dbg_audit final 0} detail]} {lappend cleanup $detail}
}
if {[catch {dbg_save final-empty.el 1} detail]} {lappend cleanup $detail}
if {$failed || [llength $cleanup]} {puts "DBG_CAPTURE_FAILED $message cleanup=$cleanup"} else {puts DBG_CAPTURE_DONE}
gui_exit -noprompt
