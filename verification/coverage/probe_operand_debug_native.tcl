# Read-only bounded tree inspection; no exclusions are selected or applied.
proc probe_require {ok message} {if {!$ok} {error $message}}
proc probe_safe {value} {return [string map [list "\t" {\t} "\n" {\n} "\r" {\r}] $value]}
proc probe_row {stream metric item depth} {
    set fields [list $metric $depth $item]
    foreach option {-meta -path -childCount} {
        lappend fields [probe_safe [gui_list_get -id CovDetail.1 $option $item]]
    }
    for {set col 0} {$col < 4} {incr col} {
        set failed [catch {gui_list_get -id CovDetail.1 -text $col $item} text]
        if {$failed} {set text "UNAVAILABLE:$text"}
        lappend fields [probe_safe $text]
    }
    puts $stream [join $fields "\t"]
    flush $stream
    puts "DBG_PROBE_NODE [join $fields { | }]"
}
proc probe_tree {stream metric} {
    set parent [gui_list_get -id CovDetail.1 -firstChild]
    for {set p 0} {$p < 5 && $parent ne "" && $parent ne "0"} {incr p} {
        probe_row $stream $metric $parent 0
        set child [gui_list_get -id CovDetail.1 -firstChild $parent]
        for {set c 0} {$c < 6 && $child ne "" && $child ne "0"} {incr c} {
            probe_row $stream $metric $child 1
            set grand [gui_list_get -id CovDetail.1 -firstChild $child]
            for {set g 0} {$g < 3 && $grand ne "" && $grand ne "0"} {incr g} {
                probe_row $stream $metric $grand 2
                set grand [gui_list_get -id CovDetail.1 -nextSibling $grand]
            }
            set child [gui_list_get -id CovDetail.1 -nextSibling $child]
        }
        set parent [gui_list_get -id CovDetail.1 -nextSibling $parent]
    }
}
proc probe_session {} {
    global env probe_scope probe_design probe_test
    source [file join $env(DVE_COVERAGE_OUTPUT) selection.tcl]
    set deadline [expr {[clock seconds] + 60}]
    while {![file exists [file join $env(DVE_COVERAGE_OUTPUT) live-ready]]} {
        if {[clock seconds] >= $deadline} {error "Live executable identity gate timed out"}
        after 100
    }
    set dirs [glob -types d -directory [file join $probe_test snps coverage db testdata] *]
    probe_require [expr {[llength $dirs] == 1}] "Exactly one test required"
    set test [file join [file rootname $probe_test] [file tail [lindex $dirs 0]]]
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) selected_tests.txt] w]
    puts $stream $test
    close $stream
    gui_open_cov -hier $probe_design -testdir [list $probe_test] -test [list $test] -merge OperandDebugReadOnlyProbe
    gui_list_expand -id CoverageTable.1 -all {<root>}
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) native-tree.tsv] w]
    puts $stream "metric\tdepth\thandle\tmeta\tpath\tchild_count\tcol0\tcol1\tcol2\tcol3"
    set views [open [file join $env(DVE_COVERAGE_OUTPUT) view-types.tsv] w]
    puts $views "metric\taction_failed\tactual_type\tdetail"
    foreach {metric label} {branch Branch line Line} {
        set failed [catch {gui_list_action -id CoverageTable.1 -column $label $probe_scope} detail]
        set actual {}
        if {!$failed} {
            set type_failed [catch {gui_covdetail_query -id CovDetail.1 -name type} actual]
            if {$type_failed} {set failed 1; set detail $actual}
        }
        puts $views "$metric\t$failed\t[probe_safe $actual]\t[probe_safe $detail]"
        flush $views
        if {!$failed} {
            gui_list_expand -id CovDetail.1 -all {<root>}
            probe_tree $stream $metric
        }
    }
    close $views
    close $stream
    gui_exclusion_file -save -file [list [file join $env(DVE_COVERAGE_OUTPUT) probe-empty.el]]
    probe_require [expr {[file size [file join $env(DVE_COVERAGE_OUTPUT) probe-empty.el]] == 0}] "Probe not globally empty"
    puts DBG_PROBE_DONE
}
if {![info exists probe_library_only]} {
    if {[catch {probe_session} message]} {puts "DBG_PROBE_FAILED $message\n$::errorInfo"}
    gui_exit -noprompt
}
