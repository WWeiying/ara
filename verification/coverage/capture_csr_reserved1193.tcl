# Independent partial-bit session. All selection variables live in the global namespace.
proc csr_need {ok why} {if {!$ok} {error $why}}
proc csr_flat {v} {
    while {[llength $v] == 1 && [lindex $v 0] ne $v} {set v [lindex $v 0]}
    return $v
}
proc csr_select {path} {
    foreach old [csr_flat [gui_list_get_selected -id CovDetail.1 -flat]] {
        if {$old ne ""} {gui_list_select -id CovDetail.1 -unselect [list $old]}
    }
    csr_need [expr {[gui_list_get_selected -id CovDetail.1 -count] == 0}] "Selection not cleared"
    gui_list_select -id CovDetail.1 -select [list $path]
    csr_need [expr {[gui_list_get_selected -id CovDetail.1 -count] == 1 &&
        [csr_flat [gui_list_get_selected -id CovDetail.1 -flat]] eq $path}] "Singleton readback differs"
}
proc csr_rows {item} {
    set result {}
    while {$item ne "" && $item ne "0"} {
        set path [gui_list_get -id CovDetail.1 -path $item]
        set meta [gui_list_get -id CovDetail.1 -meta $item]
        set name [string trim [gui_list_get -id CovDetail.1 -text 0 $item]]
        lappend result [list $path $meta $name]
        set result [concat $result [csr_rows [gui_list_get -id CovDetail.1 -firstChild $item]]]
        set item [gui_list_get -id CovDetail.1 -nextSibling $item]
    }
    return $result
}
proc csr_context {} {
    gui_list_action -id CoverageTable.1 -column Toggle $::csr_scope
    csr_need [expr {[gui_covdetail_query -id CovDetail.1 -name type] eq "Toggle"}] "Not Toggle"
    gui_list_expand -id CovDetail.1 -all {<root>}
    gui_process_events -mstime 100
}
proc csr_capture {stage} {
    csr_context
    set rows [csr_rows [gui_list_get -id CovDetail.1 -firstChild]]
    set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) objects-${stage}.tsv] w]
    puts $stream "path\tmeta\tname\texcluded"
    foreach row $rows {
        csr_select [lindex $row 0]
        set excluded [gui_exclusion -id CovDetail.1 -excluded -selected]
        puts $stream [join [concat $row [list $excluded]] "\t"]
    }
    close $stream
    # The installed command documents double click as compress/uncompress.
    # Exact per-bit inventory below is mandatory; no compressed group is accepted as a bit.
    foreach target $::csr_targets {
        if {[lindex $target 2] eq "vectornode"} {
            csr_select [lindex $target 1]
            gui_cov_tgl_double_click -id CovDetail.1 -item [lindex $target 1]
        }
    }
    gui_process_events -mstime 100
    set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) bits-${stage}.tsv] w]
    puts $stream "signal\tbit\tpath\tmeta\tname\t0to1\t1to0"
    foreach row [csr_rows [gui_list_get -id CovDetail.1 -firstChild]] {
        set name [lindex $row 2]
        foreach target $::csr_targets {
            set signal [lindex $target 0]
            set bit ""
            if {[lindex $target 2] eq "node" && $name eq $signal} {set bit 0}
            if {[string first "${signal}\[" $name] == 0 &&
                [regexp {\[([0-9]+)\]$} $name ignored actual]} {set bit $actual}
            if {$bit ne ""} {
                csr_select [lindex $row 0]
                set rise [gui_exclusion -id CovDetail.1 -excluded -selected -tgl_transition 0to1]
                set fall [gui_exclusion -id CovDetail.1 -excluded -selected -tgl_transition 1to0]
                puts $stream [join [concat [list $signal $bit] $row [list $rise $fall]] "\t"]
            }
        }
    }
    close $stream
    puts [exec $::csr_python -B $::csr_helper inventory --output $::env(DVE_COVERAGE_OUTPUT) --stage $stage]
}
proc csr_save {name} {
    gui_exclusion_file -save -file [list [file join $::env(DVE_COVERAGE_OUTPUT) $name]]
}
proc csr_reset {} {
    gui_exclusion -reset
    gui_exclusion -id CoverageTable.1 -recalculate
    gui_process_events -mstime 100
}
proc csr_load {name} {
    gui_exclusion_file -load -file [list [file join $::env(DVE_COVERAGE_OUTPUT) $name]]
    gui_exclusion -id CoverageTable.1 -recalculate
    gui_process_events -mstime 100
    csr_need [expr {[gui_cov_excl_review -isEmpty] == 1}] "Rejected/unreviewed native import"
}
proc csr_el {name} {
    puts [exec $::csr_python -B $::csr_helper el --output $::env(DVE_COVERAGE_OUTPUT) --file $name]
}
proc csr_session {} {
    uplevel #0 [list source [file join $::env(DVE_COVERAGE_OUTPUT) selection.tcl]]
    # Preserve actual API contract in the GUI log before touching any exclusion.
    help gui_cov_tgl_double_click
    help gui_exclusion
    gui_open_cov -hier $::fma_design -testdir [list $::fma_vdb] -test [list $::fma_test] -merge CSR1193NativeOnly
    gui_list_expand -id CoverageTable.1 -all {<root>}
    csr_save initial-empty.el
    csr_capture before
    csr_load candidate.el
    csr_capture selected
    csr_save first.el; csr_el first.el
    csr_reset
    csr_capture reset; csr_save reset-empty.el
    csr_load first.el
    csr_capture reloaded; csr_save second.el; csr_el second.el
    csr_reset
    csr_capture final; csr_save final-empty.el
    puts CSR1193_NATIVE_DONE
}
if {![info exists ::csr_test_only]} {
    if {[catch {csr_session} message]} {
        set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) error.txt] w]
        puts $stream $message; puts $stream $::errorInfo; close $stream
        puts "CSR1193_NATIVE_FAILED $message"
        # Cleanup steps are independent so a query failure cannot prevent global reset/save.
        catch {csr_reset} cleanup
        catch {csr_save cleanup-empty.el} cleanup
    }
    gui_exit -noprompt
}
