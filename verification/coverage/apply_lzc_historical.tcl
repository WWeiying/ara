# Tcl 8.4; helper procedures are reused from the frozen capture without running it.
source [file join $env(DVE_COVERAGE_OUTPUT) capture-helpers.tcl]

proc lzc_formal_summary {id name} {
    global env seen row_count
    gui_list_expand -id $id -all {<root>}
    set columns {}
    set header {Name Depth}
    for {set column 5} {$column < 32} {incr column} {
        if {[catch {gui_list_get_property -id $id -column $column} label]} {break}
        set label [string trim $label]
        if {$label eq ""} {continue}
        lappend columns $column
        lappend header $label
    }
    if {![llength $columns]} {error "Missing summary columns"}
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) $name] w]
    fconfigure $stream -encoding utf-8 -translation lf
    csv_row $stream $header
    array unset seen
    array set seen {}
    set row_count 0
    set failed [catch {export_rows $stream $id "" 0 $columns} message]
    close $stream
    if {$failed} {error $message}
    if {$row_count == 0} {error "Empty formal summary"}
}

proc apply_reviewed_waivers {id} {
    global env lzc_batch_groups
    set stream ""
    set failed [catch {
        source [file join $env(DVE_COVERAGE_OUTPUT) groups.tcl]
        set count 0
        foreach group $lzc_batch_groups {incr count [llength [lindex $group 3]]}
        if {$count != 180 || [llength $lzc_batch_groups] != 120} {error "Not exact180/120"}
        set stream [open [file join $env(DVE_COVERAGE_OUTPUT) neighbor-audit.csv] w]
        fconfigure $stream -encoding utf-8 -translation lf
        csv_row $stream {Stage Scope Expression NativeNames Targets Retained TargetExcluded RetainedExcluded}
        # This is after raw export: prove it had no pre-existing exclusions.
        gui_exclusion_file -save -file [list [file join $env(DVE_COVERAGE_OUTPUT) initial-empty.el]]
        lzc_batch_audit $id $stream before 0
        gui_exclusion_file -load -file [list [file join $env(DVE_COVERAGE_OUTPUT) points.el]]
        gui_exclusion -id $id -recalculate
        if {[gui_cov_excl_review -isEmpty] != 1} {error "Native import requires review"}
        lzc_batch_audit $id $stream applied 1
        gui_exclusion_file -save -file [list [file join $env(DVE_COVERAGE_OUTPUT) exclusions.el]]
        lzc_formal_summary $id summary_waived.csv.partial
    } message]
    set cleanup_errors {}
    if {[catch {gui_exclusion -reset} cleanup]} {lappend cleanup_errors $cleanup}
    if {[catch {gui_exclusion -id $id -recalculate} cleanup]} {lappend cleanup_errors $cleanup}
    if {$stream ne ""} {
        if {[catch {lzc_batch_audit $id $stream final 0} cleanup]} {lappend cleanup_errors $cleanup}
    }
    if {[catch {
        gui_exclusion_file -save -file [list [file join $env(DVE_COVERAGE_OUTPUT) final-empty.el]]
    } cleanup]} {lappend cleanup_errors $cleanup}
    if {$stream ne "" && [catch {close $stream} cleanup]} {lappend cleanup_errors $cleanup}
    if {[llength $cleanup_errors]} {error "Final reset failed: $cleanup_errors; initial: $message"}
    if {$failed} {error $message}
    lzc_formal_summary $id summary_reset.csv.partial
    puts "LZC_FORMAL_WAIVER_DONE 180"
    puts "DVE_WAIVER_EXPORT_DONE"
}
