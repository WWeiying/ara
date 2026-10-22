# Procedure-only import; the retained global exporter opens the database once.
uplevel #0 [list source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/report_native_full775.tcl}]
proc full776_masku_inventory {stage} {
    if {[llength $::full776_masku_scopes] != 26 || [llength [lsort -unique $::full776_masku_scopes]] != 26} {error "Exact26 MASKU scopes required"}
    set index 0
    foreach scope $::full776_masku_scopes {
        p740_root
        set token [p740_select $scope]
        if {$token ne $scope} {error "Exact canonical MASKU scope required"}
        gui_list_action -id CoverageTable.1 -column Toggle $token
        if {[gui_covdetail_query -id CovDetail.1 -name type] ne "Toggle"} {error "Not Toggle"}
        gui_list_expand -id CovDetail.1 -all {<root>}
        gui_process_events -mstime 100
        set columns {}; set labels {}
        for {set n 0} {$n<32} {incr n} {
            if {[catch {gui_list_get_property -id CovDetail.1 -column $n} label]} {break}
            if {[string trim $label] ne ""} {lappend columns $n; lappend labels [string trim $label]}
        }
        if {$labels ne "Variable Type Coverage Display"} {error "Unknown native MASKU column schema $labels"}
        set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) masku776_${stage}_${index}.tsv] {WRONLY CREAT EXCL}]
        puts $stream "handle\tpath\tmeta\tname\ttype\tcoverage\tdisplay\texcluded"
        set failed [catch {full775_walk [gui_list_get -id CovDetail.1 -firstChild] $stream $columns} message]
        close $stream
        if {$failed} {error $message}
        incr index
    }
    puts "FULL776_MASKU_NATIVE $stage $index"
}
rename combo_audit full776_retained_audit
proc combo_audit {stage mode active} {
    full776_retained_audit $stage $mode $active
    full776_masku_inventory $mode
}
