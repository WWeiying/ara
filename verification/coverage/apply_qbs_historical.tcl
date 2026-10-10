# Tcl 8.4. Exact448 only; restore full-root scope before every audit/export.
source [file join $env(DVE_COVERAGE_OUTPUT) capture-helpers.tcl]
set opapp_library_only 1
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/apply_operand_1144_690_v2.tcl}
proc qbsapp_root {} {
    gui_covtable_show -id CoverageTable.1 -show {Design Hierarchy} -cumulative 1
    gui_covtable_setroot -id CoverageTable.1 ara_tb
    gui_list_expand -id CoverageTable.1 -all {<root>}
    gui_cov_show_value -switch false
    gui_process_events -mstime 100
    set first [gui_list_get -id CoverageTable.1 -firstChild]
    if {$first eq "" || $first eq "0" || [gui_list_get -id CoverageTable.1 -path $first] ne "ara_tb"} {
        error "Full-root GUI contract differs"
    }
}
proc qbsapp_rows {stream parent depth prefix columns} {
    global qbsapp_seen qbsapp_rows_count
    if {$depth > 256 || $qbsapp_rows_count >= 100000} {error "Summary bounds exceeded"}
    if {$parent eq ""} {set item [gui_list_get -id CoverageTable.1 -firstChild]} else {
        set item [gui_list_get -id CoverageTable.1 -firstChild $parent]
    }
    while {$item ne "" && $item ne "0"} {
        if {[info exists qbsapp_seen($item)]} {error "Repeated GUI handle"}
        set qbsapp_seen($item) 1
        set name [string trim [gui_list_get -id CoverageTable.1 -text 0 $item]]
        if {$name ne ""} {
            if {$prefix eq ""} {set scope $name} else {set scope "$prefix.$name"}
            set path [gui_list_get -id CoverageTable.1 -path $item]
            if {$path ne $scope} {error "Relative GUI path path=$path expected=$scope"}
            set values [list $name $depth $path $scope]
            foreach column $columns {
                set value [string trim [gui_list_get -id CoverageTable.1 -text $column $item]]
                if {$value eq ""} {set value NA}
                lappend values $value
            }
            opapp_csv $stream $values
            incr qbsapp_rows_count
            qbsapp_rows $stream $item [expr {$depth+1}] $scope $columns
        }
        set item [gui_list_get -id CoverageTable.1 -nextSibling $item]
    }
}
proc qbsapp_summary {stage} {
    global env qbsapp_seen qbsapp_rows_count
    qbsapp_root
    gui_exclusion -id CoverageTable.1 -recalculate
    gui_process_events -mstime 100
    set columns {}
    set header {Name Depth GUIPath Scope}
    for {set column 5} {$column < 32} {incr column} {
        if {[catch {gui_list_get_property -id CoverageTable.1 -column $column} label]} {break}
        set label [string trim $label]
        if {$label eq ""} {continue}
        if {[lsearch -exact $header $label] >= 0} {error "Duplicate summary label"}
        lappend header $label
        lappend columns $column
    }
    foreach required {Score Line Toggle FSM Condition Branch} {
        if {[lsearch -exact $header $required] < 0} {error "Missing metric $required"}
    }
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) summary_$stage.csv] w]
    fconfigure $stream -encoding utf-8 -translation lf
    opapp_csv $stream $header
    array unset qbsapp_seen
    array set qbsapp_seen {}
    set qbsapp_rows_count 0
    set failed [catch {qbsapp_rows $stream "" 0 "" $columns} message]
    close $stream
    if {$failed} {error $message}
    if {!$qbsapp_rows_count} {error "Empty hierarchy report"}
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) gui-contract.tsv] a]
    puts $stream "$stage\tara_tb\t$qbsapp_rows_count"
    close $stream
    puts "QBSAPP_SUMMARY $stage $qbsapp_rows_count"
}
proc qbsapp_session {} {
    global env dbg_design dbg_scopes dbg_keys dbg_targets qbs_native_keys qbs_audit_keys
    global qbsapp_native qbsapp_databases qbsapp_tests qbsapp_count
    source [file join $env(DVE_COVERAGE_OUTPUT) selection.tcl]
    if {($qbsapp_count != 1 && $qbsapp_count != 699) || [llength $qbsapp_databases] != $qbsapp_count ||
        [llength $qbsapp_tests] != $qbsapp_count} {error "Wrong actual population"}
    set qbsapp_databases [opapp_canonical $qbsapp_databases]
    set qbsapp_tests [opapp_canonical $qbsapp_tests]
    if {[llength [lsort -unique $qbsapp_databases]] != $qbsapp_count ||
        [llength [lsort -unique $qbsapp_tests]] != $qbsapp_count} {error "Duplicate GUI input"}
    foreach scope $dbg_scopes {
        if {[llength $qbs_native_keys($scope)] != 2119 || [llength $qbs_audit_keys($scope)] != 2119 ||
            [llength $dbg_targets($scope|branch)] != 224} {error "Wrong exact branch population"}
    }
    puts QBSAPP_CANONICAL_INPUTS
    set deadline [expr {[clock seconds]+60}]
    while {![file exists [file join $env(DVE_COVERAGE_OUTPUT) live-ready]]} {
        if {[clock seconds] >= $deadline} {error "Live identity gate timeout"}
        after 100
    }
    foreach database $qbsapp_databases {
        if {[llength [glob -nocomplain -types d -directory [file join $database snps coverage db testdata] *]] != 1} {
            error "Ambiguous testdata before load"
        }
    }
    gui_open_cov -hier $dbg_design -testdir $qbsapp_databases -test $qbsapp_tests -merge QBSExact448HistoricalOnly
    set log [open [file join $env(DVE_COVERAGE_OUTPUT) DVEfiles dve_gui.log] r]
    set text [read $log]
    close $log
    if {[regexp -nocase {DVCDT136|UCAPI-DLMA|Load Failed|Failed to load tests|EK-CMD-|Error:|Error-|Fatal:} $text] ||
        [string first "The design '$dbg_design' was loaded successfully." $text] < 0} {error "Coverage load gate failed"}
    puts QBSAPP_LOAD_GATE_PASSED
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) selected_tests.txt] w]
    foreach test $qbsapp_tests {puts $stream $test}
    close $stream
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) gui-contract.tsv] w]
    puts $stream "stage\troot\trows"
    close $stream
    qbsapp_root
    dbg_save initial-empty.el 1
    qbs_audit before 0
    qbsapp_summary raw
    gui_exclusion_file -load -file [list $qbsapp_native]
    gui_exclusion -id CoverageTable.1 -recalculate
    if {[gui_cov_excl_review -isEmpty] != 1} {error "Native import review not empty"}
    qbsapp_root
    qbs_audit selected 1
    dbg_save applied.el
    qbsapp_summary applied
    gui_exclusion -reset
    qbsapp_root
    qbs_audit reset 0
    dbg_save reset-empty.el 1
    qbsapp_summary reset
}
if {![info exists qbsapp_library_only]} {
    set failed [catch {qbsapp_session} message]
    if {$failed} {puts "QBSAPP_ERROR $message\n$::errorInfo"}
    set cleanup {}
    if {[catch {gui_exclusion -reset} detail]} {lappend cleanup $detail}
    if {[info exists dbg_scopes]} {
        if {[catch {qbsapp_root; qbs_audit final 0} detail]} {lappend cleanup $detail}
    }
    if {[catch {dbg_save final-empty.el 1} detail]} {lappend cleanup $detail}
    if {$failed || [llength $cleanup]} {puts "QBSAPP_FAILED $message cleanup=$cleanup"} else {puts QBSAPP_DONE_EXACT448}
    gui_exit -noprompt
}
