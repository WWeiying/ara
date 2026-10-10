# One historical sample, one vector; Tcl8.4-safe and no inferred native IDs.
proc fma_need {ok why} {if {!$ok} {error $why}}
proc fma_save {name} {
    gui_exclusion_file -save -file [list [file join $::env(DVE_COVERAGE_OUTPUT) $name]]
}
proc fma_walk {item stream} {
    global fma_target_rows
    while {$item ne "" && $item ne "0"} {
        set path [gui_list_get -id CovDetail.1 -path $item]
        set meta [gui_list_get -id CovDetail.1 -meta $item]
        set name [string trim [gui_list_get -id CovDetail.1 -text 0 $item]]
        puts $stream "$item\t$path\t$meta\t$name"
        if {$name eq "product" || $name eq "product\[47:0\]"} {
            lappend fma_target_rows [list $path $meta $name]
        }
        fma_walk [gui_list_get -id CovDetail.1 -firstChild $item] $stream
        set item [gui_list_get -id CovDetail.1 -nextSibling $item]
    }
}
proc fma_bind {stage} {
    global fma_scope fma_target_rows
    gui_list_action -id CoverageTable.1 -column Toggle $fma_scope
    fma_need [expr {[gui_covdetail_query -id CovDetail.1 -name type] eq "Toggle"}] "Not a Toggle detail"
    gui_list_expand -id CovDetail.1 -all {<root>}
    gui_process_events -mstime 100
    set fma_target_rows {}
    set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) native_$stage.tsv] w]
    puts $stream "handle\tpath\tmeta\tname"
    fma_walk [gui_list_get -id CovDetail.1 -firstChild] $stream
    close $stream
    fma_need [expr {[llength $fma_target_rows] == 1}] "No unique native product row"
    return [lindex $fma_target_rows 0]
}
proc fma_select {row} {
    set old [gui_list_get_selected -id CovDetail.1 -flat]
    if {[llength $old]} {gui_list_select -id CovDetail.1 -unselect $old}
    set token [lindex $row 0]
    gui_list_select -id CovDetail.1 -select [list $token]
    set selected [gui_list_get_selected -id CovDetail.1 -flat]
    while {[llength $selected] == 1 && [lindex $selected 0] ne $selected} {set selected [lindex $selected 0]}
    fma_need [expr {$selected eq $token || $selected eq [lindex $row 1]}] "Product selection readback differs"
}
proc fma_session {} {
    global env fma_scope fma_design fma_vdb fma_test fma_python fma_helper
    source [file join $env(DVE_COVERAGE_OUTPUT) selection.tcl]
    foreach command {gui_list_get gui_list_select gui_exclude_items gui_exclusion gui_exclusion_file} {
        puts "FMA_NATIVE_HELP $command [help $command]"
    }
    gui_open_cov -hier $fma_design -testdir [list $fma_vdb] -test [list $fma_test] -merge FMAProductNativeOnly
    gui_list_expand -id CoverageTable.1 -all {<root>}
    fma_save initial-empty.el
    set before [fma_bind before]
    fma_select $before
    gui_exclude_items -id CovDetail.1 -selected -annotation {Approved unchanged FMA datapath integration scope; product[47:0] only; native format calibration, not population application}
    gui_exclusion -id CoverageTable.1 -recalculate
    fma_need [expr {[gui_cov_excl_review -isEmpty] == 1}] "Native exclusion needs review"
    set selected [fma_bind selected]
    fma_need [expr {$selected eq $before}] "Native target binding changed"
    fma_save first.el
    puts [exec $fma_python -B $fma_helper el --output $env(DVE_COVERAGE_OUTPUT) --file first.el]
    gui_exclusion -reset
    fma_bind reset
    fma_save reset-empty.el
    gui_exclusion_file -load -file [list [file join $env(DVE_COVERAGE_OUTPUT) first.el]]
    gui_exclusion -id CoverageTable.1 -recalculate
    fma_need [expr {[gui_cov_excl_review -isEmpty] == 1}] "Reload needs review"
    set reloaded [fma_bind reloaded]
    fma_need [expr {$reloaded eq $before}] "Reload native identity changed"
    fma_save second.el
    puts [exec $fma_python -B $fma_helper el --output $env(DVE_COVERAGE_OUTPUT) --file second.el]
    gui_exclusion -reset
    fma_bind final
    fma_save final-empty.el
    puts FMA_PRODUCT_NATIVE_CAPTURE_DONE
}
set failed [catch {fma_session} message]
if {$failed} {
    puts "FMA_PRODUCT_NATIVE_CAPTURE_FAILED $message"
    puts $::errorInfo
    catch {gui_exclusion -reset}
    catch {fma_save cleanup-empty.el}
}
gui_exit -noprompt
