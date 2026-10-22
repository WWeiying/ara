# Tcl 8.4, exact single-test qualification. Absolute frozen helper, no other policies.
set dbg_library_only 1
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/capture_operand_debug.tcl}
foreach helper {dbg_require dbg_select dbg_save} {
    if {[llength [info commands $helper]] != 1} {error "FF1 missing pinned helper $helper"}
}
proc ff1_metadata {scope} {
    global dbg_keys
    gui_list_action -id CoverageTable.1 -column Branch $scope
    dbg_require [expr {[gui_covdetail_query -id CovDetail.1 -name type] eq "Branch"}] "FF1 detail type differs"
    gui_list_expand -id CovDetail.1 -all {<root>}
    array set found {}
    array set seen {}
    set parent [gui_list_get -id CovDetail.1 -firstChild]
    while {$parent ne "" && $parent ne "0"} {
        dbg_require [expr {![info exists seen($parent)]}] "FF1 native tree cycle"
        set seen($parent) 1
        set parentpath [gui_list_get -id CovDetail.1 -path $parent]
        dbg_require [regexp {^Item([0-9]+)$} $parentpath unused parentid] "FF1 unknown native parent $parentpath"
        set item [gui_list_get -id CovDetail.1 -firstChild $parent]
        while {$item ne "" && $item ne "0"} {
            dbg_require [expr {![info exists seen($item)]}] "FF1 native leaf cycle"
            set seen($item) 1
            set meta [gui_list_get -id CovDetail.1 -meta $item]
            set path [gui_list_get -id CovDetail.1 -path $item]
            dbg_require [regexp {^(Branch|MISSING_DEFAULT)([0-9]+)\.([0-9]+)$} $meta unused kind sid vid] "FF1 unknown native leaf meta=$meta path=$path"
            dbg_require [expr {$sid eq $parentid && $path eq "$parentpath.$meta" && [gui_list_get -id CovDetail.1 -childCount $item] == 0}] "FF1 leaf identity differs"
            set key "$sid,$vid"
            dbg_require [expr {![info exists found($key)]}] "FF1 duplicate vector"
            set found($key) [list $meta $path]
            set item [gui_list_get -id CovDetail.1 -nextSibling $item]
        }
        set parent [gui_list_get -id CovDetail.1 -nextSibling $parent]
    }
    dbg_require [expr {[array size found] == 54 && [lsort [array names found]] eq [lsort $dbg_keys($scope|branch)]}] "FF1 complete observed/compiled selector inventory differs"
    return [array get found]
}
proc ff1_audit {stage active} {
    global env dbg_scopes dbg_keys dbg_targets
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) states_$stage.tsv] w]
    puts $stream "scope\tmetric\tcoordinate\tmeta\tpath\texcluded"
    set count 0
    set failed [catch {
        foreach scope $dbg_scopes {
            array unset metadata
            array set metadata [ff1_metadata $scope]
            foreach key $dbg_keys($scope|branch) {
                set meta [lindex $metadata($key) 0]
                set path [lindex $metadata($key) 1]
                dbg_select branch $meta
                set actual [gui_exclusion -id CovDetail.1 -list branch -excluded -selected]
                set wanted [expr {$active && [lsearch -exact $dbg_targets($scope|branch) $key] >= 0}]
                dbg_require [expr {($actual eq "0" || $actual eq "1") && $actual == $wanted}] "FF1 singleton differs stage=$stage scope=$scope key=$key actual=$actual wanted=$wanted"
                puts $stream "$scope\tbranch\t$key\t$meta\t$path\t$actual"
                incr count
            }
        }
        dbg_require [expr {$count == 1728}] "FF1 incomplete all-position audit"
    } message]
    close $stream
    if {$failed} {error $message}
    puts "FF1_AUDIT $stage $count"
}
proc ff1_session {} {
    global env dbg_design dbg_test dbg_scopes dbg_keys dbg_targets ff1_python ff1_driver ff1_test_identity
    source [file join $env(DVE_COVERAGE_OUTPUT) selection.tcl]
    foreach helper {ff1_metadata ff1_audit dbg_require dbg_select dbg_save} {
        dbg_require [expr {[llength [info commands $helper]] == 1}] "FF1 helper not loaded"
    }
    set deadline [expr {[clock seconds] + 60}]
    while {![file exists [file join $env(DVE_COVERAGE_OUTPUT) live-ready]]} {
        if {[clock seconds] >= $deadline} {error "FF1 live identity gate timed out"}
        after 100
    }
    foreach command {gui_list_get gui_list_select gui_list_get_selected gui_exclusion gui_exclude_items} {
        set failed [catch {help $command} result]
        puts "FF1_API_HELP $command failed=$failed result=$result"
        dbg_require [expr {!$failed}] "FF1 required API unavailable"
    }
    set dirs [glob -types d -directory [file join $dbg_test snps coverage db testdata] *]
    dbg_require [expr {[llength $dirs] == 1}] "FF1 exactly one historical test required"
    set test [file join [file rootname $dbg_test] [file tail [lindex $dirs 0]]]
    dbg_require [expr {$test eq $ff1_test_identity}] "FF1 selected test identity differs"
    gui_open_cov -hier $dbg_design -testdir [list $dbg_test] -test [list $test] -merge FF1NativeQualificationOnly
    gui_list_expand -id CoverageTable.1 -all {<root>}
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) selected_tests.txt] w]
    puts $stream $test
    close $stream
    dbg_save initial-empty.el 1
    ff1_audit before 0
    foreach scope $dbg_scopes {
        array unset metadata
        array set metadata [ff1_metadata $scope]
        foreach key $dbg_targets($scope|branch) {
            dbg_select branch [lindex $metadata($key) 0]
            gui_exclude_items -id CovDetail.1 -list branch -selected -annotation {FF1 narrow width exact case native qualification only; not application approval}
        }
    }
    gui_exclusion -id CoverageTable.1 -recalculate
    dbg_require [expr {[gui_cov_excl_review -isEmpty] == 1}] "FF1 selection requires review"
    ff1_audit selected 1
    dbg_save first.el
    puts [exec $ff1_python -B $ff1_driver first --output $env(DVE_COVERAGE_OUTPUT) --seal $env(FF1_CAPTURE_SEAL)]
    gui_exclusion -reset
    ff1_audit reset 0
    dbg_save reset-empty.el 1
    gui_exclusion_file -load -file [list [file join $env(DVE_COVERAGE_OUTPUT) first.el]]
    gui_exclusion -id CoverageTable.1 -recalculate
    dbg_require [expr {[gui_cov_excl_review -isEmpty] == 1}] "FF1 reload requires review"
    ff1_audit reloaded 1
    dbg_save second.el
}
if {![info exists ff1_library_only]} {
    set failed [catch {ff1_session} message]
    if {$failed} {puts "FF1_SESSION_ERROR $message\n$::errorInfo"}
    set cleanup {}
    if {[catch {gui_exclusion -reset} detail]} {lappend cleanup $detail}
    if {[info exists dbg_scopes]} {
        if {[catch {ff1_audit final 0} detail]} {lappend cleanup $detail}
    }
    if {[catch {dbg_save final-empty.el 1} detail]} {lappend cleanup $detail}
    if {$failed || [llength $cleanup]} {puts "FF1_FAILED $message cleanup=$cleanup"} else {puts FF1_CAPTURE_DONE_904}
    gui_exit -noprompt
}
