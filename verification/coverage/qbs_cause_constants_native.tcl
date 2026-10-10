# Absolute sources are required: DVE evaluates its entry script without info script.
set ::csr_test_only 1
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/capture_csr_reserved1193.tcl}
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/apply_points740_v4.tcl}
proc csv_row {stream fields} {
    set quoted {}
    foreach field $fields {lappend quoted "\"[string map [list \" \"\"] $field]\""}
    puts $stream [join $quoted ,]
}
proc qc_host {mode args} {
    return [eval [linsert $args 0 exec $::qc_python -B $::qc_helper $mode --output $::env(DVE_COVERAGE_OUTPUT) --seal $::env(QBS_CAUSE_CONSTANTS_SEAL)]]
}
proc qc_capture {stage} {
    set index 0
    foreach scope $::qc_scopes {
        p740_root
        set ::csr_scope $scope
        csr_context
        set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) native_${stage}_${index}.tsv] w]
        puts $stream "handle\tpath\tmeta\tname\texcluded"
        foreach row [qc_rows [gui_list_get -id CovDetail.1 -firstChild]] {
            csr_select [lindex $row 1]
            set flag [gui_exclusion -id CovDetail.1 -excluded -selected]
            puts $stream [join [concat $row [list $flag]] "\t"]
        }
        close $stream
        puts [qc_host inventory --stage $stage --index $index]
        incr index
    }
    p740_summary $stage
}
proc qc_rows {item} {
    set result {}
    while {$item ne "" && $item ne "0"} {
        lappend result [list $item [gui_list_get -id CovDetail.1 -path $item] [gui_list_get -id CovDetail.1 -meta $item] [string trim [gui_list_get -id CovDetail.1 -text 0 $item]]]
        set result [concat $result [qc_rows [gui_list_get -id CovDetail.1 -firstChild $item]]]
        set item [gui_list_get -id CovDetail.1 -nextSibling $item]
    }
    return $result
}
proc qc_session {} {
    uplevel #0 [list source [file join $::env(DVE_COVERAGE_OUTPUT) selection.tcl]]
    gui_open_cov -hier $::qc_design -testdir [list $::qc_sample] -test [list $::qc_test] -merge QBSCauseConstantsOnly
    gui_list_expand -id CoverageTable.1 -all {<root>}
    puts "QBS_CAUSE_CONSTANTS_SELECTED $::qc_test"
    csr_save initial-empty.el; puts [qc_host el --stage before]; qc_capture before
    puts [qc_host bind]
    csr_load candidate.el
    csr_save first.el; puts [qc_host el --stage selected]; qc_capture selected
    csr_reset
    csr_save reset-empty.el; puts [qc_host el --stage reset]; qc_capture reset
    csr_load first.el
    csr_save second.el; puts [qc_host el --stage reloaded]; qc_capture reloaded
    csr_reset
    csr_save final-empty.el; puts [qc_host el --stage final]; qc_capture final
    csr_reset; csr_save cleanup-empty.el
    puts QBS_CAUSE_CONSTANTS_NATIVE_DONE
}
if {![info exists ::qc_test_only]} {
    if {[catch {qc_session} message]} {
        set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) error.txt] w]
        puts $stream $message; puts $stream $::errorInfo; close $stream
        puts "QBS_CAUSE_CONSTANTS_FAILED $message"
        catch {csr_reset} cleanup
        catch {csr_save cleanup-empty.el} cleanup
    }
    gui_exit -noprompt
}
