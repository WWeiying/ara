# Local five-phase partial-bit session; loaded only by a parent-reviewed worker.
set ::csr_test_only 1
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/capture_csr_reserved1193.tcl}
unset ::csr_test_only
proc qb_call {args} {
    return [eval exec [list $::qb_python -B $::qb_helper] $args [list --output $::env(DVE_COVERAGE_OUTPUT) --seal $::env(QBS7612_SEAL)]]
}
proc qb_columns {} {
    set columns {}; set labels {}
    for {set column 0} {$column < 32} {incr column} {
        if {[catch {gui_list_get_property -id CovDetail.1 -column $column} label]} {break}
        if {[string trim $label] ne ""} {lappend labels [string trim $label]; lappend columns $column}
    }
    csr_need [expr {$labels eq "Variable Type Coverage Display" && [lindex $columns 0] == 0}] "Unknown native Toggle columns $labels"
    return $columns
}
proc qb_capture {stage} {
    set index 0
    foreach instance $::qb_instances {
        set scope [lindex $instance 0]
        set targets [lindex $instance 1]
        gui_list_action -id CoverageTable.1 -column Toggle $scope
        csr_need [expr {[gui_covdetail_query -id CovDetail.1 -name type] eq "Toggle"}] "Actual Toggle context"
        gui_list_expand -id CovDetail.1 -all {<root>}
        gui_process_events -mstime 100
        set columns [qb_columns]
        puts "QBS7612_NATIVE_COLUMNS $stage $index $columns"
        set rows [csr_rows [gui_list_get -id CovDetail.1 -firstChild]]
        set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) native_${stage}_${index}.tsv] {WRONLY CREAT EXCL}]
        puts $stream "path\tmeta\tname\ttype\tcoverage\texcluded"
        foreach row $rows {
            set path [lindex $row 0]
            csr_select $path
            set type [string trim [gui_list_get -id CovDetail.1 -text [lindex $columns 1] $path]]
            set coverage [string trim [gui_list_get -id CovDetail.1 -text [lindex $columns 2] $path]]
            set flag [gui_exclusion -id CovDetail.1 -excluded -selected]
            puts $stream [join [concat $row [list $type $coverage $flag]] "\t"]
        }
        close $stream
        set paths {}
        foreach target $targets {
            set label [lindex $target 1]
            set matches {}
            foreach row $rows {if {[lindex $row 2] eq $label} {lappend matches [lindex $row 0]}}
            csr_need [expr {[llength $matches] == 1}] "Unique actual hit vector"
            set path [lindex $matches 0]
            lappend paths $path
            csr_select $path
            gui_cov_tgl_double_click -id CovDetail.1 -item $path
        }
        gui_process_events -mstime 100
        set bitcolumns [qb_columns]
        set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) bits_${stage}_${index}.tsv] {WRONLY CREAT EXCL}]
        puts $stream "signal\tbit\tpath\tmeta\tname\tcoverage\t0to1\t1to0"
        foreach row [csr_rows [gui_list_get -id CovDetail.1 -firstChild]] {
            set name [lindex $row 2]
            foreach target $targets {
                set signal [lindex $target 0]
                if {[string first "${signal}\[" $name] == 0 && [regexp {\[([0-9]+)\]$} $name ignored bit]} {
                    set path [lindex $row 0]
                    csr_select $path
                    set coverage [string trim [gui_list_get -id CovDetail.1 -text [lindex $bitcolumns 2] $path]]
                    set rise [gui_exclusion -id CovDetail.1 -excluded -selected -tgl_transition 0to1]
                    set fall [gui_exclusion -id CovDetail.1 -excluded -selected -tgl_transition 1to0]
                    puts $stream [join [concat [list $signal $bit] $row [list $coverage $rise $fall]] "\t"]
                }
            }
        }
        close $stream
        foreach path $paths {gui_cov_tgl_double_click -id CovDetail.1 -item $path}
        gui_process_events -mstime 100
        incr index
    }
    puts [qb_call inventory --stage $stage]
}
proc qb_session {} {
    uplevel #0 [list source [file join $::env(DVE_COVERAGE_OUTPUT) selection.tcl]]
    puts [qb_call check]
    help gui_cov_tgl_double_click
    help gui_exclusion
    set dirs [glob -types d -directory [file join $::qb_sample snps coverage db testdata] *]
    csr_need [expr {[llength $dirs] == 1}] "One actual admitted QBS sample"
    set actual [file join [file rootname $::qb_sample] [file tail [lindex $dirs 0]]]
    csr_need [expr {$actual eq $::qb_test}] "Actual native QBS test identity"
    set deadline [expr {[clock seconds] + 60}]
    while {![file exists [file join $::env(DVE_COVERAGE_OUTPUT) live-ready]]} {
        if {[clock seconds] >= $deadline} {error "Actual owning executable gate absent"}
        after 100
    }
    gui_open_cov -hier $::qb_design -testdir [list $::qb_sample] -test [list $::qb_test] -merge Qbs7612LocalOnly
    set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) selected_tests.txt] {WRONLY CREAT EXCL}]
    puts $stream $actual; close $stream
    gui_list_expand -id CoverageTable.1 -all {<root>}
    csr_save initial-empty.el
    csr_need [expr {[file size [file join $::env(DVE_COVERAGE_OUTPUT) initial-empty.el]] == 0}] "Initial global empty EL"
    qb_capture before
    puts [qb_call bind]
    puts [qb_call binding]
    csr_load candidate.el
    qb_capture applied
    csr_save first.el
    puts [qb_call el --file first.el]
    csr_reset
    qb_capture reset
    csr_save reset-empty.el
    csr_load first.el
    qb_capture reloaded
    csr_save second.el
    puts [qb_call el --file second.el]
    csr_reset
    qb_capture final
    csr_save final-empty.el
}
if {![info exists ::qb_test_only]} {
    set failed [catch {qb_session} message]
    if {$failed} {
        set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) error.txt] {WRONLY CREAT EXCL}]
        puts $stream "$message\n$::errorInfo"; close $stream
        puts "QBS7612_FAILED $message"
    }
    set cleanup {}
    if {[catch {csr_reset} detail]} {lappend cleanup $detail}
    if {[catch {csr_save cleanup-empty.el} detail]} {lappend cleanup $detail}
    if {!$failed && ![llength $cleanup]} {puts QBS7612_FIVE_PHASE_DONE}
    if {[llength $cleanup]} {puts "QBS7612_FAILED cleanup=$cleanup"}
    gui_exit -noprompt
}
