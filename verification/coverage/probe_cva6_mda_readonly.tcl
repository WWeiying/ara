# Procedures only. Caller owns one pinned database and exact selected test list.
# No open, exclusion, recalculate, load, save, reset, or database mutation here.
proc mda_read_walk {item depth stream columns} {
    while {$item ne "" && $item ne "0"} {
        set values [list $depth $item [gui_list_get -id CovDetail.1 -path $item] [gui_list_get -id CovDetail.1 -meta $item]]
        foreach col $columns {lappend values [gui_list_get -id CovDetail.1 -text $col $item]}
        puts $stream $values
        mda_read_walk [gui_list_get -id CovDetail.1 -firstChild $item] [expr {$depth+1}] $stream $columns
        set item [gui_list_get -id CovDetail.1 -nextSibling $item]
    }
}
proc mda_read_scope {scope output} {
    if {[file exists $output]} {error "Fresh readonly evidence required"}
    if {$scope ne "ara_tb.dut.i_ara_soc.i_system.i_ariane.issue_stage_i.i_issue_read_operands" &&
        $scope ne "ara_tb.dut.i_ara_soc.i_system.i_ariane.issue_stage_i.i_issue_read_operands.gen_asic_regfile.i_ariane_regfile" &&
        $scope ne "ara_tb.dut.i_ara_soc.i_system.i_ariane.issue_stage_i.i_scoreboard"} {error "Unreviewed MDA scope"}
    gui_list_action -id CoverageTable.1 -column Toggle $scope
    if {[gui_covdetail_query -id CovDetail.1 -name type] ne "Toggle"} {error "Not Toggle detail"}
    gui_list_expand -id CovDetail.1 -all {<root>}
    gui_process_events -mstime 100
    set columns {}; set labels {}
    for {set i 0} {$i < 32} {incr i} {
        if {[catch {gui_list_get_property -id CovDetail.1 -column $i} label]} {break}
        if {[string trim $label] ne ""} {lappend columns $i; lappend labels $label}
    }
    if {[llength $columns] == 0} {error "No native detail columns"}
    set stream [open $output {WRONLY CREAT EXCL}]
    puts $stream [list scope $scope columns $columns labels $labels]
    set code [catch {mda_read_walk [gui_list_get -id CovDetail.1 -firstChild] 0 $stream $columns} message]
    close $stream
    if {$code} {error $message}
}
