# Tcl 8.4. Qualification only; never excludes an instance or a condition.
proc dbg_require {ok message} {if {!$ok} {error $message}}
proc dbg_options {metric} {
    if {$metric eq "branch"} {return [list -list branch]}
    dbg_require [expr {$metric eq "line"}] "Unsupported metric"
    return {}
}
proc dbg_select {metric meta} {
    set options [dbg_options $metric]
    set old [eval gui_list_get_selected -id CovDetail.1 $options -flat]
    if {[llength $old]} {eval gui_list_select -id CovDetail.1 $options -unselect [list $old]}
    eval gui_list_select -id CovDetail.1 $options -select [list [list $meta]]
    set actual [eval gui_list_get_selected -id CovDetail.1 $options -flat]
    dbg_require [expr {[llength $actual] == 1 && [lindex $actual 0] eq $meta}] "Singleton selection differs"
}
proc dbg_visit_line {item} {
    global dbg_line_found dbg_line_seen
    while {$item ne "" && $item ne "0"} {
        dbg_require [expr {![info exists dbg_line_seen($item)]}] "Native tree cycle"
        set dbg_line_seen($item) 1
        set meta [gui_list_get -id CovDetail.1 -meta $item]
        set path [gui_list_get -id CovDetail.1 -path $item]
        puts "DBG_LINE_NATIVE meta=$meta path=$path"
        if {[regexp {^Block([0-9]+)$} $meta unused key]} {
            dbg_require [expr {![info exists dbg_line_found($key)]}] "Duplicate native block"
            set dbg_line_found($key) [list $meta $path]
        }
        set child [gui_list_get -id CovDetail.1 -firstChild $item]
        if {$child ne "" && $child ne "0"} {dbg_visit_line $child}
        set item [gui_list_get -id CovDetail.1 -nextSibling $item]
    }
}
proc dbg_metadata {scope metric} {
    global dbg_keys dbg_line_found dbg_line_seen
    if {$metric eq "branch"} {set label Branch} else {set label Line}
    gui_list_action -id CoverageTable.1 -column $label $scope
    dbg_require [expr {[gui_covdetail_query -id CovDetail.1 -name type] eq $label}] "Wrong detail type"
    gui_list_expand -id CovDetail.1 -all {<root>}
    array set found {}
    if {$metric eq "branch"} {
        set parent [gui_list_get -id CovDetail.1 -firstChild]
        while {$parent ne "" && $parent ne "0"} {
            set parentpath [gui_list_get -id CovDetail.1 -path $parent]
            dbg_require [regexp {^Item([0-9]+)$} $parentpath unused parentid] "Unknown native branch parent"
            set item [gui_list_get -id CovDetail.1 -firstChild $parent]
            while {$item ne "" && $item ne "0"} {
                set meta [gui_list_get -id CovDetail.1 -meta $item]
                set path [gui_list_get -id CovDetail.1 -path $item]
                dbg_require [regexp {^(Branch|MISSING_ELSE)([0-9]+)\.([0-9]+)$} $meta unused kind sid vid] "Unknown native vector"
                dbg_require [expr {$sid eq $parentid && $path eq "$parentpath.$meta"}] "Native branch path differs"
                dbg_require [expr {[gui_list_get -id CovDetail.1 -childCount $item] == 0}] "Not a native vector leaf"
                set key "$sid,$vid"
                dbg_require [expr {![info exists found($key)]}] "Duplicate native vector"
                set found($key) [list $meta $path]
                set item [gui_list_get -id CovDetail.1 -nextSibling $item]
            }
            set parent [gui_list_get -id CovDetail.1 -nextSibling $parent]
        }
    } else {
        array unset dbg_line_found
        array unset dbg_line_seen
        array set dbg_line_found {}
        array set dbg_line_seen {}
        dbg_visit_line [gui_list_get -id CovDetail.1 -firstChild]
        array set found [array get dbg_line_found]
    }
    dbg_require [expr {[lsort [array names found]] eq [lsort $dbg_keys($scope|$metric)]}] "Complete native/compiled inventory differs"
    return [array get found]
}
proc dbg_audit {stage active} {
    global env dbg_scopes dbg_keys dbg_targets
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) states_$stage.tsv] w]
    puts $stream "scope\tmetric\tcoordinate\tmeta\tpath\texcluded"
    set count 0
    set failed [catch {
        foreach scope $dbg_scopes {
            foreach metric {branch line} {
                array unset metadata
                array set metadata [dbg_metadata $scope $metric]
                foreach key $dbg_keys($scope|$metric) {
                    set meta [lindex $metadata($key) 0]
                    set path [lindex $metadata($key) 1]
                    dbg_select $metric $meta
                    set actual [eval gui_exclusion -id CovDetail.1 [dbg_options $metric] -excluded -selected]
                    set wanted [expr {$active && [lsearch -exact $dbg_targets($scope|$metric) $key] >= 0}]
                    dbg_require [expr {($actual eq "0" || $actual eq "1") && $actual == $wanted}] "Protected/target singleton state differs"
                    puts $stream "$scope\t$metric\t$key\t$meta\t$path\t$actual"
                    incr count
                }
            }
        }
    } message]
    close $stream
    if {$failed} {error $message}
    puts "DBG_AUDIT $stage $count"
}
proc dbg_save {name {empty 0}} {
    global env
    set path [file join $env(DVE_COVERAGE_OUTPUT) $name]
    gui_exclusion_file -save -file [list $path]
    if {$empty} {dbg_require [expr {[file size $path] == 0}] "Global exclusion file not empty"}
}
proc dbg_session {} {
    global env dbg_design dbg_test dbg_scopes dbg_targets dbg_python dbg_driver
    source [file join $env(DVE_COVERAGE_OUTPUT) selection.tcl]
    set deadline [expr {[clock seconds] + 60}]
    while {![file exists [file join $env(DVE_COVERAGE_OUTPUT) live-ready]]} {
        if {[clock seconds] >= $deadline} {error "Live executable identity gate timed out"}
        after 100
    }
    foreach command {gui_list_get gui_list_select gui_list_get_selected gui_exclusion gui_exclude_items} {
        set failed [catch {help $command} result]
        puts "DBG_API_HELP $command failed=$failed result=$result"
    }
    set dirs [glob -types d -directory [file join $dbg_test snps coverage db testdata] *]
    dbg_require [expr {[llength $dirs] == 1}] "Exactly one historical PASS sample required"
    set test [file join [file rootname $dbg_test] [file tail [lindex $dirs 0]]]
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) selected_tests.txt] w]
    puts $stream $test
    close $stream
    gui_open_cov -hier $dbg_design -testdir [list $dbg_test] -test [list $test] -merge OperandDebugQualificationOnly
    gui_list_expand -id CoverageTable.1 -all {<root>}
    dbg_save initial-empty.el 1
    dbg_audit before 0
    foreach scope $dbg_scopes {
        foreach metric {branch line} {
            array unset metadata
            array set metadata [dbg_metadata $scope $metric]
            foreach key $dbg_targets($scope|$metric) {
                dbg_select $metric [lindex $metadata($key) 0]
                eval gui_exclude_items -id CovDetail.1 [dbg_options $metric] -selected -annotation [list {Reviewed operand debug instrumentation; native qualification only; not aggregate approval}]
            }
        }
    }
    gui_exclusion -id CoverageTable.1 -recalculate
    dbg_require [expr {[gui_cov_excl_review -isEmpty] == 1}] "Selection requires review"
    dbg_audit selected 1
    dbg_save first.el
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) config.json] r]
    close $stream
    # The externally supplied seal is never obtained from mutable saved comparisons.
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
if {![info exists dbg_library_only]} {
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
}
