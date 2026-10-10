proc csv_row {stream values} {
    set quoted {}
    foreach value $values {
        lappend quoted "\"[string map [list \" \"\"] $value]\""
    }
    puts $stream [join $quoted ,]
}

proc export_rows {stream id parent depth columns} {
    global seen row_count
    if {$depth > 256} {
        error "Coverage summary tree exceeds exporter limits"
    }
    if {$parent eq ""} {
        set item [gui_list_get -id $id -firstChild]
    } else {
        set item [gui_list_get -id $id -firstChild $parent]
    }
    while {$item ne "" && $item ne "0"} {
        if {$row_count >= 100000} { error "Coverage summary tree exceeds exporter limits" }
        if {[info exists seen($item)]} { error "Repeated coverage item handle" }
        set seen($item) 1
        set name [gui_list_get -id $id -text 0 $item]
        set values [list $name $depth]
        foreach column $columns {
            set value [string trim [gui_list_get -id $id -text $column $item]]
            if {$value eq ""} { set value NA }
            lappend values $value
        }
        if {[string trim $name] ne ""} {
            csv_row $stream $values
            incr row_count
        }
        if {[gui_list_get -id $id -childCount $item] > 0} {
            export_rows $stream $id $item [expr {$depth + 1}] $columns
        }
        set item [gui_list_get -id $id -nextSibling $item]
    }
}

proc export_summary {} {
    global env seen row_count
    set input [open [file join $env(DVE_COVERAGE_OUTPUT) inputs.txt] r]
    fconfigure $input -encoding utf-8
    set databases [split [string trimright [read $input] "\n"] "\n"]
    close $input
    set design [lindex $databases 0]
    if {![file isfile [file join $design snps coverage db design verilog.design.xml]]} {
        error "First input must contain the compiled coverage design"
    }
    set testdirs {}
    set tests {}
    set rejected {}
    foreach database $databases {
        set testroot [file join $database snps coverage db testdata]
        set found {}
        if {[file isdirectory $testroot]} {
            foreach test [lsort [glob -nocomplain -types d -directory $testroot *]] {
                set datafiles [glob -nocomplain -types f -directory $test *.data.xml]
                set complete [expr {[llength $datafiles] > 0}]
                foreach datafile $datafiles {
                    if {![file readable $datafile] || [file size $datafile] == 0} { set complete 0 }
                }
                if {$complete} {
                    lappend found [file join [file rootname $database] [file tail $test]]
                } else {
                    lappend rejected $test
                }
            }
        }
        if {[llength $found] > 0} {
            lappend testdirs $database
            foreach test $found {
                if {[lsearch -exact $tests $test] >= 0} { error "Duplicate coverage test: $test" }
                lappend tests $test
            }
        } elseif {$database ne $design} {
            lappend rejected $testroot
        }
    }
    if {[llength $rejected] > 0} {
        set manifest [open [file join $env(DVE_COVERAGE_OUTPUT) rejected_tests.txt] w]
        fconfigure $manifest -encoding utf-8 -translation lf
        foreach test $rejected { puts $manifest $test }
        close $manifest
        error "Incomplete coverage test inputs; see rejected_tests.txt: $rejected"
    }
    if {[llength $tests] == 0} { error "No coverage tests found" }
    puts "DVE_SELECTED_TESTS: $tests"
    set manifest [open [file join $env(DVE_COVERAGE_OUTPUT) selected_tests.txt] w]
    fconfigure $manifest -encoding utf-8 -translation lf
    foreach test $tests { puts $manifest $test }
    close $manifest
    gui_open_cov -hier $design -testdir $testdirs -test $tests -merge MergedTest
    set tables {}
    foreach id [gui_get_window_ids] {
        if {[string match CoverageTable.* $id]} { lappend tables $id }
    }
    if {[llength $tables] != 1} {
        error "Expected exactly one DVE coverage summary table, found: $tables"
    }
    set id [lindex $tables 0]
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
    if {[llength $columns] == 0} { error "No coverage columns found" }
    set partial [file join $env(DVE_COVERAGE_OUTPUT) summary.csv.partial]
    set stream [open $partial w]
    fconfigure $stream -encoding utf-8 -translation lf
    csv_row $stream $header
    array set seen {}
    set row_count 0
    set failed [catch {export_rows $stream $id "" 0 $columns} message]
    close $stream
    if {$failed} { error $message }
    if {$row_count == 0} { error "Empty coverage summary; no result exported" }
    if {[info exists env(DVE_REVIEWED_WAIVERS)]} {
        source $env(DVE_REVIEWED_WAIVERS)
        apply_reviewed_waivers $id
    }
    puts "DVE_COVERAGE_EXPORT_DONE"
}

if {[catch {export_summary} message]} {
    puts "DVE_COVERAGE_EXPORT_FAILED: $message"
}
gui_exit -noprompt

