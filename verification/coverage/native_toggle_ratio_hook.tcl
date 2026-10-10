# Future unsealed consumers only. No design load, exclusion, or automatic install.
# Show Ratio API is bound by installed preferencesCovMainMenu.tcl:269..296.
namespace eval nr_counts {}
proc nr_counts::row {scope label stream stage} {
    p740_root
    set token [p740_select $scope]
    if {$token ne $scope} {error "Ratio token differs"}
    set failed [catch {
        gui_covtable_setroot -id CoverageTable.1 $scope
        gui_cov_show_value -switch true
        gui_process_events -mstime 100
        set item [gui_list_get -id CoverageTable.1 -firstChild]
        if {$item eq "" || $item eq "0"} {error "Missing ratio root"}
        set path [gui_list_get -id CoverageTable.1 -path $item]
        set name [string trim [gui_list_get -id CoverageTable.1 -text 0 $item]]
        set next [gui_list_get -id CoverageTable.1 -nextSibling $item]
        if {$path ne $label || $name ne $label || ($next ne "" && $next ne "0")} {
            error "Ratio root label/uniqueness differs"
        }
        set seen {}
        for {set column 5} {$column < 32} {incr column} {
            if {[catch {gui_list_get_property -id CoverageTable.1 -column $column} metric]} {break}
            set metric [string trim $metric]
            if {[lsearch -exact {Score Line Toggle FSM Condition Branch} $metric] >= 0} {
                if {[lsearch -exact $seen $metric] >= 0} {error "Duplicate ratio metric"}
                lappend seen $metric
                set raw [gui_list_get -id CoverageTable.1 -text $column $item]
                csv_row $stream [list $stage $scope $token $item $path $name $column $metric $raw]
            }
        }
        if {[lsort $seen] ne [lsort {Score Line Toggle FSM Condition Branch}]} {error "Missing ratio metric"}
    } message]
    set cleanup [catch {gui_cov_show_value -switch false; p740_root} detail]
    if {$failed} {error $message}
    if {$cleanup} {error "Ratio restore failed: $detail"}
}
proc nr_counts::audit {stage} {
    if {[lsearch -exact {raw applied reset reloaded final} $stage] < 0} {error "Unknown ratio stage"}
    set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) ratios_$stage.csv] {WRONLY CREAT EXCL}]
    csv_row $stream {Stage Scope Token Handle GUIPath Name Column Metric NativeRawText}
    set failed [catch {
        foreach root $::native_ratio_roots {nr_counts::row [lindex $root 0] [lindex $root 1] $stream $stage}
    } message]
    close $stream
    if {$failed} {error $message}
}
proc nr_counts::install {roots} {
    if {[llength [info procs ::p740_summary]] != 1 || [llength [info procs ::nr_counts::percent_summary]]} {
        error "Ratio install requires one existing owned percentage procedure; no double install"
    }
    if {![llength $roots]} {error "Empty bound ratio roots"}
    set scopes {}
    foreach root $roots {
        if {[llength $root] != 2 || [lindex $root 1] eq "" ||
            [lsearch -exact $scopes [lindex $root 0]] >= 0} {error "Invalid/duplicate bound ratio roots"}
        lappend scopes [lindex $root 0]
    }
    set ::native_ratio_roots $roots
    rename ::p740_summary ::nr_counts::percent_summary
    proc ::p740_summary {stage} {
        nr_counts::percent_summary $stage
        nr_counts::audit $stage
    }
}
