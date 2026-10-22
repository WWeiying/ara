# Independent five-phase partial packed cause session. No session on test-only source.
set csr_test_only 1
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/capture_csr_reserved1193.tcl}
unset csr_test_only
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/apply_points740_v4.tcl}

proc s60_gate {mode stage} {
    puts [exec $::s60_python -B $::s60_helper $mode --output $::env(DVE_COVERAGE_OUTPUT) \
        --seal $::env(CAUSE60_CONFIG_SEAL) --stage $stage]
}
proc s60_save {name} {
    gui_exclusion_file -save -file [list [file join $::env(DVE_COVERAGE_OUTPUT) $name]]
}
proc s60_reset {} {
    gui_exclusion -reset
    gui_exclusion -id CoverageTable.1 -recalculate
    gui_process_events -mstime 100
}
proc s60_load {name} {
    gui_exclusion_file -load -file [list [file join $::env(DVE_COVERAGE_OUTPUT) $name]]
    gui_exclusion -id CoverageTable.1 -recalculate
    gui_process_events -mstime 100
    csr_need [expr {[gui_cov_excl_review -isEmpty] == 1}] "Unresolved/rejected partial cause import"
}
proc s60_rows {item} {
    set result {}
    while {$item ne "" && $item ne "0"} {
        lappend result [list $item [gui_list_get -id CovDetail.1 -path $item] \
            [gui_list_get -id CovDetail.1 -meta $item] \
            [string trim [gui_list_get -id CovDetail.1 -text 0 $item]]]
        set result [concat $result [s60_rows [gui_list_get -id CovDetail.1 -firstChild $item]]]
        set item [gui_list_get -id CovDetail.1 -nextSibling $item]
    }
    return $result
}
proc s60_capture {stage} {
    set index 0
    foreach group $::s60_groups {
        set scope [lindex $group 0]
        set targets [lindex $group 1]
        csr_need [expr {[p740_select $scope] eq $scope}] "Exact scope readback"
        gui_list_action -id CoverageTable.1 -column Toggle $scope
        csr_need [expr {[gui_covdetail_query -id CovDetail.1 -name type] eq "Toggle"}] "Not Toggle"
        gui_list_expand -id CovDetail.1 -all {<root>}
        gui_process_events -mstime 100
        set columns {}
        for {set col 0} {$col < 32} {incr col} {
            if {[catch {gui_list_get_property -id CovDetail.1 -column $col} label]} {break}
            if {[string trim $label] ne ""} {lappend columns [string trim $label]}
        }
        csr_need [expr {$columns eq "Variable Type Coverage Display"}] "Exact native columns required"
        set rows [s60_rows [gui_list_get -id CovDetail.1 -firstChild]]
        set f [open [file join $::env(DVE_COVERAGE_OUTPUT) objects_${stage}_${index}.tsv] w]
        puts $f "handle\tpath\tmeta\tname\ttype\tcoverage\tdisplay\t0to1\t1to0"
        foreach row $rows {
            set handle [lindex $row 0]
            set path [lindex $row 1]
            csr_select $path
            set role [string trim [gui_list_get -id CovDetail.1 -text 1 $handle]]
            set coverage [string trim [gui_list_get -id CovDetail.1 -text 2 $handle]]
            set display [string trim [gui_list_get -id CovDetail.1 -text 3 $handle]]
            set rise [gui_exclusion -id CovDetail.1 -excluded -selected -tgl_transition 0to1]
            set fall [gui_exclusion -id CovDetail.1 -excluded -selected -tgl_transition 1to0]
            puts $f [join [concat $row [list $role $coverage $display $rise $fall]] "\t"]
        }
        close $f
        set paths {}
        foreach signal $targets {
            set full "${signal}\[63:0\]"
            set matches {}
            foreach row $rows {if {[lindex $row 3] eq $full} {lappend matches [lindex $row 1]}}
            csr_need [expr {[llength $matches] == 1}] "Unique actual packed cause full path required"
            set path [lindex $matches 0]
            csr_select $path
            gui_cov_tgl_double_click -id CovDetail.1 -item $path
            lappend paths $path
        }
        gui_process_events -mstime 100
        set f [open [file join $::env(DVE_COVERAGE_OUTPUT) bits_${stage}_${index}.tsv] w]
        puts $f "signal\tbit\tpath\tmeta\tname\tcoverage\t0to1\t1to0"
        foreach row [s60_rows [gui_list_get -id CovDetail.1 -firstChild]] {
            set name [lindex $row 3]
            if {[regexp {^(.*\.cause)\[([0-9]+)\]$} $name ignored signal bit] &&
                [lsearch -exact $targets $signal] >= 0} {
                set path [lindex $row 1]
                csr_select $path
                set coverage [string trim [gui_list_get -id CovDetail.1 -text 2 [lindex $row 0]]]
                set rise [gui_exclusion -id CovDetail.1 -excluded -selected -tgl_transition 0to1]
                set fall [gui_exclusion -id CovDetail.1 -excluded -selected -tgl_transition 1to0]
                puts $f [join [concat [list $signal $bit] [lrange $row 1 end] [list $coverage $rise $fall]] "\t"]
            }
        }
        close $f
        foreach path $paths {gui_cov_tgl_double_click -id CovDetail.1 -item $path}
        gui_process_events -mstime 100
        incr index
    }
    s60_gate inventory $stage
}
proc s60_session {} {
    uplevel #0 [list source [file join $::env(DVE_COVERAGE_OUTPUT) selection.tcl]]
    s60_gate check before
    help gui_list_get
    help gui_cov_tgl_double_click
    help gui_exclusion
    set dirs [glob -types d -directory [file join $::s60_vdb snps coverage db testdata] *]
    csr_need [expr {[llength $dirs] == 1}] "One admitted PASS sample"
    set actual [file join [file rootname $::s60_vdb] [file tail [lindex $dirs 0]]]
    csr_need [expr {$actual eq $::s60_test}] "Actual test identity"
    set f [open [file join $::env(DVE_COVERAGE_OUTPUT) selected_tests.txt] w]
    puts $f $actual; close $f
    gui_open_cov -hier $::s60_design -testdir [list $::s60_vdb] -test [list $actual] -merge ScoreboardCause60LocalOnly
    p740_root
    s60_save initial-empty.el
    s60_gate el before
    s60_capture before
    s60_load candidate.el
    s60_capture selected
    s60_save first.el
    s60_gate el selected
    s60_reset
    s60_capture reset
    s60_save reset-empty.el
    s60_gate el reset
    s60_load first.el
    s60_capture reloaded
    s60_save second.el
    s60_gate el reloaded
    s60_reset
    s60_capture final
    s60_save final-empty.el
    s60_gate el final
    puts SCOREBOARD_CAUSE60_FIVE_PHASE_DONE
}
if {![info exists ::s60_test_only]} {
    if {[catch {s60_session} message]} {
        set f [open [file join $::env(DVE_COVERAGE_OUTPUT) error.txt] w]
        puts $f $message; puts $f $::errorInfo; close $f
        puts "SCOREBOARD_CAUSE60_FAILED $message"
        catch {s60_reset} cleanup
        catch {s60_save cleanup-empty.el} cleanup
    }
    gui_exit -noprompt
}
