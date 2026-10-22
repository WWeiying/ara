# Independent full-population session. Absolute pinned helpers; no baseline policy import.
proc opapp_load {} {
    global env op1144_library_only
    set path $env(OP1144_BASE_HOOK)
    if {[file pathtype $path] ne "absolute" || ![file isfile $path]} {error "Invalid absolute helper"}
    set op1144_library_only 1
    source $path
    foreach name {op1144_require op1144_select op1144_metadata op1144_audit op1144_save} {
        if {[info procs $name] ne $name} {error "Missing loaded helper: $name"}
    }
}
proc opapp_csv {stream values} {
    set quoted {}
    foreach value $values {lappend quoted "\"[string map [list \" \"\"] $value]\""}
    puts $stream [join $quoted ,]
}
proc opapp_rows {stream parent depth columns} {
    global opapp_seen opapp_count
    if {$depth > 256 || $opapp_count >= 100000} {error "Summary bounds exceeded"}
    if {$parent eq ""} {set item [gui_list_get -id CoverageTable.1 -firstChild]} else {
        set item [gui_list_get -id CoverageTable.1 -firstChild $parent]
    }
    while {$item ne "" && $item ne "0"} {
        if {[info exists opapp_seen($item)]} {error "Repeated summary handle"}
        set opapp_seen($item) 1
        set name [gui_list_get -id CoverageTable.1 -text 0 $item]
        set values [list $name $depth]
        foreach column $columns {
            set value [string trim [gui_list_get -id CoverageTable.1 -text $column $item]]
            if {$value eq ""} {set value NA}
            lappend values $value
        }
        if {[string trim $name] ne ""} {opapp_csv $stream $values; incr opapp_count}
        opapp_rows $stream $item [expr {$depth + 1}] $columns
        set item [gui_list_get -id CoverageTable.1 -nextSibling $item]
    }
}
proc opapp_summary {stage} {
    global env opapp_seen opapp_count
    gui_list_expand -id CoverageTable.1 -all {<root>}
    set columns {}
    set header {Name Depth}
    for {set column 5} {$column < 32} {incr column} {
        if {[catch {gui_list_get_property -id CoverageTable.1 -column $column} label]} {break}
        set label [string trim $label]
        if {$label eq ""} {continue}
        lappend columns $column
        lappend header $label
    }
    if {![llength $columns]} {error "No summary columns"}
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) summary_$stage.csv] w]
    fconfigure $stream -encoding utf-8 -translation lf
    opapp_csv $stream $header
    array unset opapp_seen
    array set opapp_seen {}
    set opapp_count 0
    set failed [catch {opapp_rows $stream "" 0 $columns} message]
    close $stream
    if {$failed} {error $message}
    if {!$opapp_count} {error "Empty summary"}
    puts "OPAPP_SUMMARY $stage $opapp_count"
}
proc opapp_session {} {
    global env op1144_design op1144_test op1144_scopes op1144_keys op1144_targets
    global opapp_databases opapp_tests opapp_native
    source [file join $env(DVE_COVERAGE_OUTPUT) selection.tcl]
    if {[llength $opapp_databases] != 690 || [llength $opapp_tests] != 690} {error "Requires exact690 tests"}
    puts OPAPP_HELPERS_READY
    set deadline [expr {[clock seconds] + 60}]
    while {![file exists [file join $env(DVE_COVERAGE_OUTPUT) live-ready]]} {
        if {[clock seconds] >= $deadline} {error "Live ELF gate timeout"}
        after 100
    }
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) selected_tests.txt] w]
    foreach test $opapp_tests {puts $stream $test}
    close $stream
    gui_open_cov -hier $op1144_design -testdir $opapp_databases -test $opapp_tests -merge Operand1144Full690
    set tables {}
    foreach id [gui_get_window_ids] {if {[string match CoverageTable.* $id]} {lappend tables $id}}
    if {$tables ne "CoverageTable.1"} {error "Unexpected coverage table"}
    gui_list_expand -id CoverageTable.1 -all {<root>}
    op1144_save initial-empty.el 1
    op1144_audit raw 0
    opapp_summary raw
    gui_exclusion_file -load -file [list $opapp_native]
    gui_exclusion -id CoverageTable.1 -recalculate
    if {[gui_cov_excl_review -isEmpty] != 1} {error "Native checksum review not empty"}
    puts OPAPP_NATIVE_REVIEW_EMPTY
    op1144_audit applied 1
    op1144_save applied.el
    opapp_summary applied
    gui_exclusion -reset
    op1144_audit reset 0
    op1144_save reset-empty.el 1
    opapp_summary reset
}
if {![info exists opapp_library_only]} {
    set loaded [catch {opapp_load} load_message]
    if {$loaded} {
        puts "OPAPP_FAILED helper-load-gate=$load_message"
    } else {
        set failed [catch {opapp_session} message]
        set cleanup {}
        if {[catch {gui_exclusion -reset} detail]} {lappend cleanup $detail}
        if {[info exists op1144_scopes]} {
            if {[catch {op1144_audit final 0} detail]} {lappend cleanup $detail}
        }
        if {[catch {op1144_save final-empty.el 1} detail]} {lappend cleanup $detail}
        if {$failed || [llength $cleanup]} {puts "OPAPP_FAILED $message cleanup=$cleanup"} else {
            puts OPAPP_DONE_EXACT1144_FULL690
        }
    }
    gui_exit -noprompt
}
