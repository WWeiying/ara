# Prepare-only library. No load/exclusion/session entry; not sourced by full764.
# Installed DVE preferencesCovMainMenu.tcl:269..296 binds Show Ratio to this API.
proc native_toggle_ratio_row {scope expected_name stream stage} {
    p740_root
    set token [p740_select $scope]
    if {$token ne $scope} {error "Ratio scope selection differs"}
    set failed [catch {
        gui_covtable_setroot -id CoverageTable.1 $token
        gui_cov_show_value -switch true
        gui_process_events -mstime 100
        set item [gui_list_get -id CoverageTable.1 -firstChild]
        if {$item eq "" || $item eq "0"} {error "Missing ratio root"}
        set name [string trim [gui_list_get -id CoverageTable.1 -text 0 $item]]
        set path [gui_list_get -id CoverageTable.1 -path $item]
        set sibling [gui_list_get -id CoverageTable.1 -nextSibling $item]
        if {$name ne $expected_name || $path ne $name || ($sibling ne "" && $sibling ne "0")} {
            error "Ratio root identity differs"
        }
        set found 0
        for {set column 5} {$column < 32} {incr column} {
            if {[catch {gui_list_get_property -id CoverageTable.1 -column $column} label]} {break}
            if {[string trim $label] eq "Toggle"} {
                incr found
                set raw [string trim [gui_list_get -id CoverageTable.1 -text $column $item]]
                csv_row $stream [list $stage $scope $token $name $raw]
            }
        }
        if {$found != 1} {error "Ratio Toggle field missing/ambiguous"}
    } message]
    set cleanup [catch {gui_cov_show_value -switch false; p740_root} detail]
    if {$failed} {error $message}
    if {$cleanup} {error "Ratio display restoration failed: $detail"}
}
