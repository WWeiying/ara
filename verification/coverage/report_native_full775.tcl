# Global procedure-only import: the exporter alone opens the full database.
uplevel #0 [list source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/report_native_full773_branch720.tcl}]
proc full775_walk {item stream columns} {
    while {$item ne "" && $item ne "0"} {
        set path [gui_list_get -id CovDetail.1 -path $item]
        set meta [gui_list_get -id CovDetail.1 -meta $item]
        set cells {}
        foreach column $columns {
            set value [string trim [gui_list_get -id CovDetail.1 -text $column $item]]
            if {[string first "\t" $value]>=0 || [string first "\n" $value]>=0} {error "Multiline native cell"}
            lappend cells $value
        }
        dw_select $path $meta
        set flag [gui_exclusion -id CovDetail.1 -excluded -selected]
        if {$flag ne "0" && $flag ne "1"} {error "Nonboolean singleton Toggle flag"}
        puts $stream [join [concat [list $item $path $meta] $cells [list $flag]] "\t"]
        full775_walk [gui_list_get -id CovDetail.1 -firstChild $item] $stream $columns
        set item [gui_list_get -id CovDetail.1 -nextSibling $item]
    }
}
proc full775_inventory {stage} {
    foreach family {mfpu rvh} {
        set index 0
        foreach scope [set ::full775_${family}_scopes] {
            p740_root
            set token [p740_select $scope]
            if {$token ne $scope} {error "Exact canonical scope required"}
            gui_list_action -id CoverageTable.1 -column Toggle $token
            if {[gui_covdetail_query -id CovDetail.1 -name type] ne "Toggle"} {error "Not Toggle"}
            gui_list_expand -id CovDetail.1 -all {<root>}
            gui_process_events -mstime 100
            set columns {}; set labels {}
            for {set n 0} {$n<32} {incr n} {
                if {[catch {gui_list_get_property -id CovDetail.1 -column $n} label]} {break}
                if {[string trim $label] ne ""} {lappend columns $n; lappend labels [string trim $label]}
            }
            if {$labels ne "Variable Type Coverage Display"} {error "Unknown native column schema $labels"}
            set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) ${family}775_${stage}_${index}.tsv] {WRONLY CREAT EXCL}]
            puts $stream "handle\tpath\tmeta\tname\ttype\tcoverage\tdisplay\texcluded"
            set failed [catch {full775_walk [gui_list_get -id CovDetail.1 -firstChild] $stream $columns} message]
            close $stream
            if {$failed} {error $message}
            incr index
        }
        puts "FULL775_NATIVE $family $stage $index"
    }
}
rename combo_audit full775_prior_audit
proc combo_audit {stage mode active} {
    full775_prior_audit $stage $mode $active
    full775_inventory $mode
}
