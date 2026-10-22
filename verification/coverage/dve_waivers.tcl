# Invoked only after the Python guard has matched the compiled design database.
proc apply_reviewed_waivers {id} {
    global env seen row_count
    source [file join $env(DVE_COVERAGE_OUTPUT) waiver_plan.tcl]
    # Loading an exclusion file replaces prior in-memory scope exclusions.
    gui_exclusion_file -load -file [list [file join $env(DVE_COVERAGE_OUTPUT) points.el]]
    foreach {path recursive reason} $waiver_scopes {
        set args [list gui_exclude_items -id $id -annotation $reason]
        if {$recursive} { lappend args -recursive }
        lappend args [list $path]
        eval $args
    }
    gui_exclusion -id $id -recalculate
    gui_exclusion_file -save -file [list [file join $env(DVE_COVERAGE_OUTPUT) exclusions.el]]
    gui_list_expand -id $id -all {<root>}
    set columns {}
    set header {Name Depth}
    for {set column 5} {$column < 32} {incr column} {
        if {[catch {gui_list_get_property -id $id -column $column} label]} { break }
        set label [string trim $label]
        if {$label eq ""} { continue }
        lappend columns $column
        lappend header $label
    }
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) summary_waived.csv.partial] w]
    fconfigure $stream -encoding utf-8 -translation lf
    csv_row $stream $header
    array unset seen
    array set seen {}
    set row_count 0
    set failed [catch {export_rows $stream $id "" 0 $columns} message]
    close $stream
    if {$failed} { error $message }
    if {$row_count == 0} { error "Empty waived report" }
    puts "DVE_WAIVER_EXPORT_DONE"
}
