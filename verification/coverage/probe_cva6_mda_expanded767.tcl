# Installed DVE native commands; display expansion only, never exclusions.
proc mda_expand_one {scope name output} {
    gui_list_action -id CoverageTable.1 -column Toggle $scope
    if {[gui_covdetail_query -id CovDetail.1 -name type] ne "Toggle"} {error "Not Toggle"}
    set matches {}
    set item [gui_list_get -id CovDetail.1 -firstChild]
    while {$item ne "" && $item ne "0"} {
        if {[gui_list_get -id CovDetail.1 -text 0 $item] eq $name} {
            lappend matches [gui_list_get -id CovDetail.1 -path $item]
        }
        set item [gui_list_get -id CovDetail.1 -nextSibling $item]
    }
    if {[llength $matches] != 1} {error "Missing or ambiguous exact native MDA $name"}
    set old [gui_list_get_selected -id CovDetail.1 -flat]
    while {[llength $old] == 1 && [lindex $old 0] ne $old} {set old [lindex $old 0]}
    if {[llength $old]} {gui_list_select -id CovDetail.1 -unselect $old}
    gui_list_select -id CovDetail.1 -select $matches
    gui_set_pref_value -category CoverageDetail -key tglMda -value 4096
    if {![gui_cov_tgl_can_expand_mda -id CovDetail.1]} {error "Native MDA is not expandable"}
    gui_cov_tgl_expand_mda -id CovDetail.1
    gui_process_events -mstime 100
    if {[gui_cov_tgl_can_compress -id CovDetail.1 -opt uncompress]} {
        gui_cov_tgl_compress -id CovDetail.1 -opt uncompress
        gui_process_events -mstime 100
    }
    if {[file exists $output]} {error "Fresh expansion output"}
    set columns {}; set labels {}
    for {set i 0} {$i < 32} {incr i} {
        if {[catch {gui_list_get_property -id CovDetail.1 -column $i} label]} {break}
        if {[string trim $label] ne ""} {lappend columns $i; lappend labels $label}
    }
    if {[llength $columns] == 0} {error "Missing expanded column labels"}
    set stream [open $output {WRONLY CREAT EXCL}]
    puts $stream [list scope $scope signal $name columns $columns labels $labels]
    set code [catch {mda_read_walk [gui_list_get -id CovDetail.1 -firstChild] 0 $stream $columns} message]
    close $stream
    if {$code} {error $message}
}
