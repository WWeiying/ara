# Protocol-only successor. Original candidate, partial-bit authority and protection are unchanged.
set ::btb_library_only 1
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/capture_btb_bit0_132.tcl}
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/apply_points740_v4.tcl}
proc btb_root {} {
    # Existing qualified protocol: root restore, exact singleton selection/readback,
    # then re-root the selected token. No full-hierarchy metrics collection.
    p740_root
    set token [p740_select $::btb_scope]
    btb_need [expr {$token eq $::btb_scope}] "Foreign selected BTB token"
    gui_covtable_setroot -id CoverageTable.1 $token
    gui_process_events -mstime 100
    gui_exclusion -id CoverageTable.1 -recalculate
    gui_process_events -mstime 100
    set row [gui_list_get -id CoverageTable.1 -firstChild]
    set path ""
    set name ""
    set next ""
    if {$row ne "" && $row ne "0"} {
        set path [gui_list_get -id CoverageTable.1 -path $row]
        set name [string trim [gui_list_get -id CoverageTable.1 -text 0 $row]]
        set next [gui_list_get -id CoverageTable.1 -nextSibling $row]
    }
    set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) root-contract.tsv] a]
    puts $stream [join [list $::btb_stage_name $::btb_scope $token $row $path $name $next] "\t"]
    close $stream
    puts [list BTB132_ROOT_OBSERVED $::btb_stage_name $::btb_scope $token $row $path $name $next]
    btb_need [expr {$row ne "" && $row ne "0" && $path eq $name &&
        ($name eq "i_btb" || $name eq "btb") && ($next eq "" || $next eq "0")}] "Nonunique/foreign BTB root"
    set ::btb_root_path $path
    set ::btb_root_name $name
    return $row
}
proc btb_capture {stage} {
    set ::btb_stage_name $stage
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
    set values [list $stage $::btb_scope $::btb_root_path $::btb_root_name]
    foreach label {Score Line Toggle FSM Condition Branch} {
        btb_need [info exists metrics($label)] "Missing root metric"
        lappend values $metrics($label)
    }
    btb_csv $stream $values;close $stream
    if {$stage eq "before" || $stage eq "final"} {
        gui_list_action -id CoverageTable.1 -column Toggle $::btb_root_path
        btb_need [expr {[gui_covdetail_query -id CovDetail.1 -name type] eq "Toggle"}] "Not native Toggle"
        gui_list_expand -id CovDetail.1 -all {<root>}
        gui_process_events -mstime 100
        set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) objects_${stage}.tsv] w]
        puts $stream "path\tmeta\tname"
        btb_rows $stream [gui_list_get -id CovDetail.1 -firstChild]
        close $stream
    }
}
proc btb_main {} {
    set failed [catch {btb_session} message]
    set info ""
    if {$failed} {set info $::errorInfo}
    set reset_failed [catch {btb_reset} reset_message]
    set save_failed [catch {btb_save cleanup-empty.el} save_message]
    if {$failed || $reset_failed || $save_failed} {
        set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) error.txt] w]
        puts $stream [list $message $reset_message $save_message]
        puts $stream $info;close $stream
        puts "BTB132_NATIVE_FAILED $message $reset_message $save_message"
    } else {
        puts BTB132_NATIVE_DONE
    }
    flush stdout
    # Installed ucliLoadCci.tcl redirects exit(args) to gui_exit(args).
    # GUI success is not qualification: Python still requires no error and all five stages.
    gui_exit -noprompt
}
if {![info exists ::btb_v2_library_only]} {btb_main}
