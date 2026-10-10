# Tcl8.4. Reuse sealed singleton-vector primitives; no GUI IDs guessed.
if {![info exists env(MASK_SNAPSHOT_BASE_TCL)]} {error "Missing absolute native helper"}
if {[file pathtype $env(MASK_SNAPSHOT_BASE_TCL)] ne "absolute"} {error "Relative native helper"}
source $env(MASK_SNAPSHOT_BASE_TCL)
foreach helper {lzc_batch_point lzc_batch_select lzc_batch_audit} {
    if {![llength [info procs $helper]]} {error "Missing native primitive $helper"}
}

proc apply_reviewed_waivers {id} {
    global env lzc_batch_groups
    set stream ""
    set failed [catch {
        source [file join $env(DVE_COVERAGE_OUTPUT) groups.tcl]
        set total 0
        foreach group $lzc_batch_groups {incr total [llength [lindex $group 3]]}
        if {$total != 24 || [llength $lzc_batch_groups] != 36} {error "Exact24/36 required"}
        set stream [open [file join $env(DVE_COVERAGE_OUTPUT) neighbor-audit.csv] w]
        fconfigure $stream -encoding utf-8 -translation lf
        csv_row $stream {Stage Scope Expression NativeNames Targets Retained TargetExcluded RetainedExcluded}
        gui_exclusion_file -save -file [list [file join $env(DVE_COVERAGE_OUTPUT) initial-empty.el]]
        lzc_batch_audit $id $stream before 0
        foreach group $lzc_batch_groups {
            set targets [lindex $group 3]
            if {![llength $targets]} {continue}
            lzc_batch_point $id $group
            foreach vector $targets {
                lzc_batch_select [list $vector]
                gui_exclude_items -id CovDetail.1 -list vector -selected \
                    -annotation {MaskM StA snapshot zero native qualification only; branch HOLD; no approval}
            }
        }
        gui_exclusion -id $id -recalculate
        lzc_batch_audit $id $stream selected 1
        gui_exclusion_file -save -file [list [file join $env(DVE_COVERAGE_OUTPUT) first.el]]
        gui_exclusion -reset
        lzc_batch_audit $id $stream reset 0
        gui_exclusion_file -save -file [list [file join $env(DVE_COVERAGE_OUTPUT) reset-empty.el]]
        gui_exclusion_file -load -file [list [file join $env(DVE_COVERAGE_OUTPUT) first.el]]
        gui_exclusion -id $id -recalculate
        if {[gui_cov_excl_review -isEmpty] != 1} {error "Import requires review"}
        lzc_batch_audit $id $stream reloaded 1
        gui_exclusion_file -save -file [list [file join $env(DVE_COVERAGE_OUTPUT) second.el]]
    } message]
    set cleanup_errors {}
    if {[catch {gui_exclusion -reset} message2]} {lappend cleanup_errors $message2}
    if {$stream ne "" && [info exists lzc_batch_groups]} {
        if {[catch {lzc_batch_audit $id $stream final 0} message2]} {lappend cleanup_errors $message2}
    }
    if {[catch {
        gui_exclusion_file -save -file [list [file join $env(DVE_COVERAGE_OUTPUT) final-empty.el]]
    } message2]} {lappend cleanup_errors $message2}
    if {$stream ne "" && [catch {close $stream} message2]} {lappend cleanup_errors $message2}
    if {[llength $cleanup_errors]} {error "Final cleanup failed: $cleanup_errors; capture: $message"}
    if {$failed} {error $message}
    puts "MASK_STORE_COND24_CAPTURE_DONE 24"
}
