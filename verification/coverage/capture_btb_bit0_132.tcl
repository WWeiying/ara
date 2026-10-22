# One rooted BTB scope. Native EL membership, never vector aggregate flags, is authoritative.
proc btb_need {ok why} {if {!$ok} {error $why}}
proc btb_save {name} {
    gui_exclusion_file -save -file [list [file join $::env(DVE_COVERAGE_OUTPUT) $name]]
}
proc btb_reset {} {
    gui_exclusion -reset
    gui_exclusion -id CoverageTable.1 -recalculate
    gui_process_events -mstime 100
}
proc btb_load {name} {
    gui_exclusion_file -load -file [list [file join $::env(DVE_COVERAGE_OUTPUT) $name]]
    btb_need [expr {[gui_cov_excl_review -isEmpty] == 1}] "Rejected/unresolved native import"
    gui_exclusion -id CoverageTable.1 -recalculate
    gui_process_events -mstime 100
}
proc btb_csv {stream fields} {
    set values {}
    foreach field $fields {lappend values "\"[string map [list \" \"\"] $field]\""}
    puts $stream [join $values ,]
}
proc btb_root {} {
    gui_covtable_show -id CoverageTable.1 -show {Design Hierarchy} -cumulative 1
    gui_cov_show_value -switch false
    gui_covtable_setroot -id CoverageTable.1 $::btb_scope
    gui_process_events -mstime 100
    gui_exclusion -id CoverageTable.1 -recalculate
    gui_process_events -mstime 100
    set row [gui_list_get -id CoverageTable.1 -firstChild]
    btb_need [expr {$row ne "" && $row ne "0"}] "Missing BTB root"
    set path [gui_list_get -id CoverageTable.1 -path $row]
    set name [string trim [gui_list_get -id CoverageTable.1 -text 0 $row]]
    set next [gui_list_get -id CoverageTable.1 -nextSibling $row]
    btb_need [expr {$path eq "i_btb" && $name eq "i_btb" && ($next eq "" || $next eq "0")}] "Nonunique/foreign BTB root"
    return $row
}
proc btb_rows {stream item} {
    while {$item ne "" && $item ne "0"} {
        puts $stream [join [list [gui_list_get -id CovDetail.1 -path $item] \
            [gui_list_get -id CovDetail.1 -meta $item] \
            [string trim [gui_list_get -id CovDetail.1 -text 0 $item]]] "\t"]
        btb_rows $stream [gui_list_get -id CovDetail.1 -firstChild $item]
        set item [gui_list_get -id CovDetail.1 -nextSibling $item]
    }
}
proc btb_capture {stage} {
    set row [btb_root]
    set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) rooted_${stage}.csv] w]
    btb_csv $stream {Stage Scope Path Name Score Line Toggle FSM Condition Branch}
    array set metrics {}
    for {set column 5} {$column < 32} {incr column} {
        if {[catch {gui_list_get_property -id CoverageTable.1 -column $column} label]} {break}
        set label [string trim $label]
        if {[lsearch -exact {Score Line Toggle FSM Condition Branch} $label] >= 0} {
            btb_need [expr {![info exists metrics($label)]}] "Duplicate root metric"
            set metrics($label) [string trim [gui_list_get -id CoverageTable.1 -text $column $row]]
            if {$metrics($label) eq ""} {set metrics($label) NA}
        }
    }
    set values [list $stage $::btb_scope i_btb i_btb]
    foreach label {Score Line Toggle FSM Condition Branch} {
        btb_need [info exists metrics($label)] "Missing root metric"
        lappend values $metrics($label)
    }
    btb_csv $stream $values;close $stream
    if {$stage eq "before" || $stage eq "final"} {
        gui_list_action -id CoverageTable.1 -column Toggle i_btb
        btb_need [expr {[gui_covdetail_query -id CovDetail.1 -name type] eq "Toggle"}] "Not native Toggle"
        gui_list_expand -id CovDetail.1 -all {<root>}
        gui_process_events -mstime 100
        set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) objects_${stage}.tsv] w]
        puts $stream "path\tmeta\tname"
        btb_rows $stream [gui_list_get -id CovDetail.1 -firstChild]
        close $stream
    }
}
proc btb_stage {stage file} {
    btb_save $file
    puts [exec $::btb_python -B $::btb_helper stage --output $::env(DVE_COVERAGE_OUTPUT) \
        --seal $::env(BTB132_CONFIG_SEAL) --stage $stage]
    btb_capture $stage
    puts "BTB132_STAGE $stage"
}
proc btb_session {} {
    uplevel #0 [list source [file join $::env(DVE_COVERAGE_OUTPUT) selection.tcl]]
    foreach key {btb_design btb_vdb btb_test btb_scope btb_python btb_helper} {
        btb_need [info exists ::$key] "Missing global selection $key"
    }
    set deadline [expr {[clock seconds]+40}]
    while {![file exists [file join $::env(DVE_COVERAGE_OUTPUT) live-ready]]} {
        if {[clock seconds] >= $deadline} {error "Live executable gate timeout"}
        after 100
    }
    gui_open_cov -hier $::btb_design -testdir [list $::btb_vdb] -test [list $::btb_test] -merge BTB132LocalNative
    set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) selected_tests.txt] w]
    puts $stream $::btb_test;close $stream
    puts "BTB132_SELECTED $::btb_test"
    # Preserve old local state, then clear globally before measuring the baseline.
    btb_save inherited-before-clear.el
    btb_reset
    btb_stage before initial-empty.el
    btb_load candidate.el
    btb_stage applied first.el
    btb_reset
    btb_stage reset reset-empty.el
    btb_load first.el
    btb_stage reloaded second.el
    btb_reset
    btb_stage final final-empty.el
}
proc btb_main {} {
    set failed [catch {btb_session} message]
    set info ""
    if {$failed} {set info $::errorInfo}
    # Independent cleanup operations; a query error cannot suppress the reset/save.
    set reset_failed [catch {btb_reset} reset_message]
    set save_failed [catch {btb_save cleanup-empty.el} save_message]
    if {$failed || $reset_failed || $save_failed} {
        set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) error.txt] w]
        puts $stream [list $message $reset_message $save_message]
        puts $stream $info;close $stream
        puts "BTB132_NATIVE_FAILED $message $reset_message $save_message"
        flush stdout
        exit 1
    }
    puts BTB132_NATIVE_DONE
    flush stdout
    # Standard Tcl process exit avoids the observed gui_exit UI shutdown hang.
    exit 0
}
if {![info exists ::btb_library_only]} {btb_main}
