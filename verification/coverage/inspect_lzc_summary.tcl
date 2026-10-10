# Independent single-VDB diagnostic; no new selector exclusions.
source $env(LZC_FROZEN_HOOK)
rename lzc_formal_summary lzc_cached_summary
proc lzc_summary_step {label command} {
    puts "LZC_SUMMARY_STEP_BEGIN $label"
    set code [catch {uplevel 1 $command} result]
    puts "LZC_SUMMARY_STEP_END $label code=$code result=[list $result]"
    if {$code != 0} {error "Summary step $label failed: code=$code result=[list $result]"}
    return $result
}
proc lzc_formal_summary {id name} {
    global env
    lzc_cached_summary $id [string map {.csv.partial _cached.csv.partial} $name]
    set scope {ara_tb.dut.i_ara_soc.i_system}
    set failed [catch {
        lzc_summary_step metric [list gui_list_action -id $id -column Condition $scope]
        if {[gui_covdetail_query -id CovDetail.1 -name type] ne "Condition"} {error "Wrong reselected metric"}
        lzc_summary_step root [list gui_covtable_setroot -id $id $scope]
        lzc_summary_step cumulative [list gui_covtable_show -id $id -show Instances -cumulative 1]
        lzc_summary_step refresh [list gui_exclusion -id $id -update]
        lzc_cached_summary $id [string map {.csv.partial _system_percent.csv.partial} $name]
        lzc_summary_step ratio [list gui_cov_show_value -switch true]
        lzc_cached_summary $id [string map {.csv.partial _system_ratio.csv.partial} $name]
    } message]
    set cleanup [catch {
        lzc_summary_step percent [list gui_cov_show_value -switch false]
        lzc_summary_step restore [list gui_covtable_setroot -id $id ara_tb]
    } cleanup_message]
    if {$cleanup} {error "Summary restore failed: $cleanup_message; initial: $message"}
    if {$failed} {error $message}
    lzc_cached_summary $id $name
}
rename apply_reviewed_waivers lzc_frozen_apply
proc apply_reviewed_waivers {id} {
    global env
    set failed [catch {lzc_frozen_apply $id} message]
    # Avoid the diagnosed DVCDW424 without accepting/saving VDB mutations.
    gui_exclusion -reset
    gui_exclusion_file -save -file [list [file join $env(DVE_COVERAGE_OUTPUT) exit-empty.el]]
    if {$failed} {error $message}
    puts "LZC_SINGLE_SUMMARY_INSPECTION_DONE"
}
