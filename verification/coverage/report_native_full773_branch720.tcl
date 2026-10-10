# Procedure-only frozen imports; one database open remains owned by the exporter.
uplevel #0 [list source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/report_native_full771.tcl}]
set ::op1144_library_only 1
uplevel #0 [list source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/capture_operand_1144.tcl}]

proc branch773_tokens {value} {
    set result {}
    foreach item $value {
        if {[regexp {^(Branch|MISSING_ELSE)[0-9]+\.[0-9]+$} $item]} {
            lappend result $item
        } else {
            foreach token $item {
                if {![regexp {^(Branch|MISSING_ELSE)[0-9]+\.[0-9]+$} $token]} {error "Unknown branch selection token"}
                lappend result $token
            }
        }
    }
    if {[llength $result] != [llength [lsort -unique $result]]} {error "Duplicate branch selection"}
    return $result
}
proc op1144_select {metas} {
    set old [branch773_tokens [gui_list_get_selected -id CovDetail.1 -list branch -flat]]
    foreach token $old {gui_list_select -id CovDetail.1 -list branch -unselect [list $token]}
    if {[llength $metas]} {gui_list_select -id CovDetail.1 -list branch -select $metas}
    set actual [branch773_tokens [gui_list_get_selected -id CovDetail.1 -list branch -flat]]
    if {[lsort $actual] ne [lsort $metas]} {error "Exact branch selection differs"}
}
rename op1144_metadata branch773_original_metadata
proc op1144_metadata {scope} {
    p740_root
    return [branch773_original_metadata $scope]
}
proc op1144_audit {stage active} {
    set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) states_$stage.tsv] {WRONLY CREAT EXCL}]
    puts $stream "scope\tcoordinate\tmeta\tpath\texcluded"
    set count 0
    set failed [catch {
        foreach scope $::op1144_scopes {
            array unset metadata
            array set metadata [op1144_metadata $scope]
            foreach key $::op1144_keys($scope) {
                set meta [lindex $metadata($key) 0]
                set path [lindex $metadata($key) 1]
                set wanted [expr {$active && [lsearch -exact $::op1144_targets($scope) $key] >= 0}]
                op1144_select [list $meta]
                set actual [gui_exclusion -id CovDetail.1 -list branch -excluded -selected]
                if {($actual ne "0" && $actual ne "1") || $actual != $wanted} {error "Singleton branch exclusion differs"}
                puts $stream "$scope\t$key\t$meta\t$path\t$actual"
                incr count
            }
        }
    } message]
    close $stream
    if {$failed} {error $message}
    puts "BRANCH773_AUDIT $stage $count"
}
rename combo_audit branch773_original_audit
proc combo_audit {stage mode active} {
    branch773_original_audit $stage $mode $active
    op1144_audit $stage $active
}
rename p740_summary branch773_original_summary
proc p740_summary {stage} {
    branch773_original_summary $stage
    if {$stage eq "applied"} {op1144_audit after_root 1}
}
