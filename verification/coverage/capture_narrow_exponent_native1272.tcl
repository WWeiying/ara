# Tcl 8.4, one historical test; no pack, default, WIDTH64 or instance exclusion.
set dbg_library_only 1
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/capture_operand_debug.tcl}
foreach helper {dbg_require dbg_select dbg_save} {
    if {[llength [info commands $helper]] != 1} {error "EXP1272 missing pinned helper $helper"}
}
proc exp1272_metadata {scope} {
    global dbg_keys
    gui_list_action -id CoverageTable.1 -column Branch $scope
    dbg_require [expr {[gui_covdetail_query -id CovDetail.1 -name type] eq "Branch"}] "EXP1272 wrong detail type"
    gui_list_expand -id CovDetail.1 -all {<root>}
    array set found {}
    array set seen {}
    set parent [gui_list_get -id CovDetail.1 -firstChild]
    while {$parent ne "" && $parent ne "0"} {
        dbg_require [expr {![info exists seen($parent)]}] "EXP1272 native parent cycle"
        set seen($parent) 1
        set parentpath [gui_list_get -id CovDetail.1 -path $parent]
        dbg_require [regexp {^Item([0-9]+)$} $parentpath unused parentid] "EXP1272 unknown parent path=$parentpath"
        set item [gui_list_get -id CovDetail.1 -firstChild $parent]
        while {$item ne "" && $item ne "0"} {
            dbg_require [expr {![info exists seen($item)]}] "EXP1272 native leaf cycle"
            set seen($item) 1
            set meta [gui_list_get -id CovDetail.1 -meta $item]
            set path [gui_list_get -id CovDetail.1 -path $item]
            dbg_require [regexp {^(Branch|MISSING_ELSE|MISSING_DEFAULT)([0-9]+)\.([0-9]+)$} $meta unused kind sid vid] "EXP1272 unknown native leaf meta=$meta path=$path"
            dbg_require [expr {$sid eq $parentid && $path eq "$parentpath.$meta" && [gui_list_get -id CovDetail.1 -childCount $item] == 0}] "EXP1272 native identity differs"
            set key "$sid,$vid"
            dbg_require [expr {![info exists found($key)]}] "EXP1272 duplicate vector"
            set found($key) [list $meta $path]
            set item [gui_list_get -id CovDetail.1 -nextSibling $item]
        }
        set parent [gui_list_get -id CovDetail.1 -nextSibling $parent]
    }
    dbg_require [expr {[lsort [array names found]] eq [lsort $dbg_keys($scope|branch)]}] "EXP1272 complete native/compiled selector inventory differs"
    return [array get found]
}
proc exp1272_audit {stage active} {
    global env dbg_scopes dbg_keys dbg_targets
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) states_$stage.tsv] w]
    puts $stream "scope\tmetric\tcoordinate\tmeta\tpath\texcluded"
    set count 0
    set failed [catch {
        foreach scope $dbg_scopes {
            array unset metadata
            array set metadata [exp1272_metadata $scope]
            foreach key $dbg_keys($scope|branch) {
                set meta [lindex $metadata($key) 0]
                set path [lindex $metadata($key) 1]
                dbg_select branch $meta
                set actual [gui_exclusion -id CovDetail.1 -list branch -excluded -selected]
                set wanted [expr {$active && [lsearch -exact $dbg_targets($scope|branch) $key] >= 0}]
                dbg_require [expr {($actual eq "0" || $actual eq "1") && $actual == $wanted}] "EXP1272 singleton differs stage=$stage scope=$scope key=$key actual=$actual wanted=$wanted"
                puts $stream "$scope\tbranch\t$key\t$meta\t$path\t$actual"
                incr count
            }
        }
        dbg_require [expr {$count == 5616}] "EXP1272 incomplete all-position audit"
    } message]
    close $stream
    if {$failed} {error $message}
    puts "EXP1272_AUDIT $stage $count"
}
proc exp1272_session {} {
    global env dbg_design dbg_test dbg_scopes dbg_keys dbg_targets exp_python exp_driver exp_test_identity
    source [file join $env(DVE_COVERAGE_OUTPUT) selection.tcl]
    foreach helper {exp1272_metadata exp1272_audit dbg_require dbg_select dbg_save} {
        dbg_require [expr {[llength [info commands $helper]] == 1}] "EXP1272 helper not loaded"
    }
    set deadline [expr {[clock seconds] + 60}]
    while {![file exists [file join $env(DVE_COVERAGE_OUTPUT) live-ready]]} {
        if {[clock seconds] >= $deadline} {error "EXP1272 live executable gate timed out"}
        after 100
    }
    foreach command {gui_list_get gui_list_select gui_list_get_selected gui_exclusion gui_exclude_items} {
        set failed [catch {help $command} result]
        puts "EXP1272_API_HELP $command failed=$failed result=$result"
        dbg_require [expr {!$failed}] "EXP1272 required API unavailable"
    }
    set dirs [glob -types d -directory [file join $dbg_test snps coverage db testdata] *]
    dbg_require [expr {[llength $dirs] == 1}] "EXP1272 exactly one historical test required"
    set test [file join [file rootname $dbg_test] [file tail [lindex $dirs 0]]]
    dbg_require [expr {$test eq $exp_test_identity}] "EXP1272 selected test identity differs"
    gui_open_cov -hier $dbg_design -testdir [list $dbg_test] -test [list $test] -merge NarrowExponentNativeQualificationOnly
    gui_list_expand -id CoverageTable.1 -all {<root>}
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) selected_tests.txt] w]
    puts $stream $test
    close $stream
    dbg_save initial-empty.el 1
    exp1272_audit before 0
    foreach scope $dbg_scopes {
        array unset metadata
        array set metadata [exp1272_metadata $scope]
        foreach key $dbg_targets($scope|branch) {
            dbg_select branch [lindex $metadata($key) 0]
            gui_exclude_items -id CovDetail.1 -list branch -selected -annotation {Narrow round SRT double exponent exact case native qualification only; not application approval}
        }
    }
    gui_exclusion -id CoverageTable.1 -recalculate
    dbg_require [expr {[gui_cov_excl_review -isEmpty] == 1}] "EXP1272 selection requires review"
    exp1272_audit selected 1
    dbg_save first.el
    puts [exec $exp_python -B $exp_driver first --output $env(DVE_COVERAGE_OUTPUT) --seal $env(EXP1272_CAPTURE_SEAL)]
    gui_exclusion -reset
    exp1272_audit reset 0
    dbg_save reset-empty.el 1
    gui_exclusion_file -load -file [list [file join $env(DVE_COVERAGE_OUTPUT) first.el]]
    gui_exclusion -id CoverageTable.1 -recalculate
    dbg_require [expr {[gui_cov_excl_review -isEmpty] == 1}] "EXP1272 reload requires review"
    exp1272_audit reloaded 1
    dbg_save second.el
}
if {![info exists exp1272_library_only]} {
    set failed [catch {exp1272_session} message]
    if {$failed} {puts "EXP1272_SESSION_ERROR $message\n$::errorInfo"}
    set cleanup {}
    if {[catch {gui_exclusion -reset} detail]} {lappend cleanup $detail}
    if {[info exists dbg_scopes]} {
        if {[catch {exp1272_audit final 0} detail]} {lappend cleanup $detail}
    }
    if {[catch {dbg_save final-empty.el 1} detail]} {lappend cleanup $detail}
    if {$failed || [llength $cleanup]} {puts "EXP1272_FAILED $message cleanup=$cleanup"} else {puts EXP1272_CAPTURE_DONE}
    gui_exit -noprompt
}
