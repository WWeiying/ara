# Scope-only successor. All native selection and protection rules are unchanged.
proc fma_need {ok why} {if {!$ok} {error $why}}
proc fma_save {name} {
    gui_exclusion_file -save -file [list [file join $::env(DVE_COVERAGE_OUTPUT) $name]]
}
proc fma_walk {item stream} {
    global fma_names fma_rows fma_seen
    while {$item ne "" && $item ne "0"} {
        set path [gui_list_get -id CovDetail.1 -path $item]
        set meta [gui_list_get -id CovDetail.1 -meta $item]
        set name [string trim [gui_list_get -id CovDetail.1 -text 0 $item]]
        puts $stream "$item\t$path\t$meta\t$name"
        lappend fma_seen $name
        if {[lsearch -exact $fma_names $name] >= 0} {lappend fma_rows [list $path $meta $name]}
        fma_walk [gui_list_get -id CovDetail.1 -firstChild $item] $stream
        set item [gui_list_get -id CovDetail.1 -nextSibling $item]
    }
}
proc fma_bind {stage instance} {
    global fma_names fma_rows fma_seen
    set fma_names [lindex $instance 1]
    set fma_rows {}
    set fma_seen {}
    gui_list_action -id CoverageTable.1 -column Toggle [lindex $instance 0]
    fma_need [expr {[gui_covdetail_query -id CovDetail.1 -name type] eq "Toggle"}] "Not Toggle"
    gui_list_expand -id CovDetail.1 -all {<root>}
    gui_process_events -mstime 100
    set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) native_${stage}_[lindex $instance 2].tsv] w]
    puts $stream "handle\tpath\tmeta\tname"
    fma_walk [gui_list_get -id CovDetail.1 -firstChild] $stream
    close $stream
    fma_need [expr {[llength $fma_rows] == [llength $fma_names] && [llength $fma_names] == 51}] "Wrong target count"
    foreach name $fma_names {
        set count 0
        foreach seen $fma_seen {if {$seen eq $name} {incr count}}
        fma_need [expr {$count == 1}] "Missing/ambiguous exact target $name"
    }
    return $fma_rows
}
proc fma_flat {selected} {
    while {[llength $selected] == 1 && [lindex $selected 0] ne $selected} {set selected [lindex $selected 0]}
    return $selected
}
proc fma_select {row} {
    set old [fma_flat [gui_list_get_selected -id CovDetail.1 -flat]]
    if {[llength $old]} {gui_list_select -id CovDetail.1 -unselect $old}
    set token [lindex $row 0]
    gui_list_select -id CovDetail.1 -select [list $token]
    set selected [fma_flat [gui_list_get_selected -id CovDetail.1 -flat]]
    fma_need [expr {$selected eq $token || $selected eq [lindex $row 1]}] "Selection readback differs"
}
proc fma_reset {} {
    gui_exclusion -reset
    gui_exclusion -id CoverageTable.1 -recalculate
    gui_process_events -mstime 100
}
proc fma_stage {stage name} {
    foreach instance $::fma_instances {fma_bind $stage $instance}
    fma_save $name
    puts [exec $::fma_python -B $::fma_helper stage --output $::env(DVE_COVERAGE_OUTPUT) --seal $::fma_seal --stage $stage]
}
proc fma_session {} {
    global env fma_instances fma_scope fma_design fma_vdb fma_test fma_python fma_helper
    source [file join $env(DVE_COVERAGE_OUTPUT) selection.tcl]
    set ::fma_seal $env(FMA_EXPANDED_CONFIG_SEAL)
    gui_open_cov -hier $fma_design -testdir [list $fma_vdb] -test [list $fma_test] -merge FMAExpanded612NativeOnly
    gui_list_expand -id CoverageTable.1 -all {<root>}
    fma_stage initial initial-empty.el
    foreach instance $fma_instances {
        set rows [fma_bind selection $instance]
        foreach row $rows {
            fma_select $row
            gui_exclude_items -id CovDetail.1 -selected -annotation {Reviewed unchanged FP32/FP64 local FMA numerical arithmetic integration scope; all other objects and children retained; not IEEE certification}
        }
    }
    gui_exclusion -id CoverageTable.1 -recalculate
    fma_need [expr {[gui_cov_excl_review -isEmpty] == 1}] "Apply needs review"
    fma_stage apply first.el
    fma_reset
    fma_stage reset reset-empty.el
    gui_exclusion_file -load -file [list [file join $env(DVE_COVERAGE_OUTPUT) first.el]]
    gui_exclusion -id CoverageTable.1 -recalculate
    fma_need [expr {[gui_cov_excl_review -isEmpty] == 1}] "Reload needs review"
    fma_stage reload second.el
    fma_reset
    fma_stage final final-empty.el
    puts FMA_EXPANDED_NATIVE_CAPTURE_DONE
}
if {[catch {fma_session} message]} {
    puts "FMA_EXPANDED_NATIVE_CAPTURE_FAILED $message"
    puts $::errorInfo
    if {[catch {fma_reset; fma_save cleanup-empty.el} cleanup]} {puts "FMA_EXPANDED_CLEANUP_FAILED $cleanup"}
}
gui_exit -noprompt
