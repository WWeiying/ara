# Identity observation only: exclusion attributes are deliberately not queried.
proc point789_walk {item stream columns} {
    while {$item ne "" && $item ne "0"} {
        cv_need [expr {![info exists ::point_seen($item)]}] "Duplicate/cyclic detail handle"
        set ::point_seen($item) 1
        set path [gui_list_get -id CovDetail.1 -path $item]
        set meta [gui_list_get -id CovDetail.1 -meta $item]
        set name [string trim [gui_list_get -id CovDetail.1 -text 0 $item]]
        set cells {}
        foreach column $columns {lappend cells [gui_list_get -id CovDetail.1 -text $column $item]}
        foreach value [list $path $meta $name $cells] {
            cv_need [expr {[string first "\t" $value] < 0 && [string first "\n" $value] < 0}] "Multiline identity cell"
        }
        puts $stream [join [list $path $meta $name UNOBSERVED $cells] "\t"]
        point789_walk [gui_list_get -id CovDetail.1 -firstChild $item] $stream $columns
        set item [gui_list_get -id CovDetail.1 -nextSibling $item]
    }
}
proc point789_snapshot {metric} {
    p740_root
    p740_select $::point_scope
    gui_list_action -id CoverageTable.1 -column $metric $::point_scope
    cv_need [expr {[gui_covdetail_query -id CovDetail.1 -name type] eq $metric}] "Wrong detail metric"
    gui_list_expand -id CovDetail.1 -all {<root>}
    gui_process_events -mstime 100
    set columns {}; set labels {}
    for {set c 0} {$c < 32} {incr c} {
        if {[catch {gui_list_get_property -id CovDetail.1 -column $c} label]} {break}
        if {[string trim $label] ne ""} {lappend columns $c; lappend labels $label}
    }
    cv_need [expr {[llength $columns] > 0}] "No native columns"
    set f [open [file join $::env(DVE_COVERAGE_OUTPUT) observed_${metric}_0.columns] {WRONLY CREAT EXCL}]
    puts $f $labels; close $f
    set f [open [file join $::env(DVE_COVERAGE_OUTPUT) observed_${metric}_0.tsv] {WRONLY CREAT EXCL}]
    puts $f "path\tmeta\tname\texcluded\tcells"
    catch {unset ::point_seen}
    set failed [catch {point789_walk [gui_list_get -id CovDetail.1 -firstChild] $f $columns} message]
    close $f
    if {$failed} {error $message}
}
proc point789_session {} {
    uplevel #0 [list source [file join $::env(DVE_COVERAGE_OUTPUT) selection.tcl]]
    set ::cv_test_only 1
    uplevel #0 [list source $::point_library]
    uplevel #0 [list source $::point_selector]
    gui_open_cov -hier $::cv_design -testdir [list $::cv_vdb] -test [list $::cv_test] -merge PointIdentityReadOnly
    foreach metric {Line Branch} {point789_snapshot $metric}
    puts POINT789_READONLY_DONE
}
if {![info exists ::point_test_only]} {
    if {[catch {point789_session} message]} {
        set f [open [file join $::env(DVE_COVERAGE_OUTPUT) error.txt] {WRONLY CREAT EXCL}]
        puts $f $message; puts $f $::errorInfo; close $f
        puts "POINT789_READONLY_FAILED $message"
    }
    # DVE's exit shim passes positional arguments to gui_exit; never use exit 1.
    gui_exit -noprompt
}
