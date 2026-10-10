# Tcl8.4. ONE first Line row; readonly selection/API evidence, no exclusions.
proc cp_record {key code value} {
    binary scan [encoding convertto utf-8 $value] H* hex
    puts $::cp_stream [join [list $key $code $hex] "\t"]
    flush $::cp_stream
}
proc cp_query {key command} {
    set code [catch {eval $command} value]
    cp_record $key $code $value
    return [list $code $value]
}
proc cp_need {ok reason} {if {!$ok} {error $reason}}
proc cp_main {} {
    global cp_design cp_vdb cp_test cp_scope cp_library cp_stream
    uplevel #0 [list source [file join $::env(DVE_COVERAGE_OUTPUT) selection.tcl]]
    uplevel #0 [list source $cp_library]
    set cp_stream [open [file join $::env(DVE_COVERAGE_OUTPUT) row-api.tsv] {WRONLY CREAT EXCL}]
    puts $cp_stream "key\tcode\tutf8hex"
    foreach command {gui_list_get_selected gui_list_get gui_list_get_meta gui_list_select} {help $command}
    gui_open_cov -hier $cp_design -testdir [list $cp_vdb] -test [list $cp_test] -merge OneRowReadonlyAPI
    gui_exclusion_file -save -file [list [file join $::env(DVE_COVERAGE_OUTPUT) before-empty.el]]
    p740_root
    p740_select $cp_scope
    gui_list_action -id CoverageTable.1 -column Line $cp_scope
    cp_need [expr {[gui_covdetail_query -id CovDetail.1 -name type] eq "Line"}] "Not Line detail"
    gui_list_expand -id CovDetail.1 -all {<root>}
    gui_process_events -mstime 100
    set item [gui_list_get -id CovDetail.1 -firstChild]
    cp_need [expr {$item ne "" && $item ne "0"}] "No first Line row"
    cp_record original_handle 0 $item
    set path [gui_list_get -id CovDetail.1 -path $item]
    set meta [gui_list_get -id CovDetail.1 -meta $item]
    cp_record original_path 0 $path
    cp_record original_meta 0 $meta
    cp_record original_name 0 [gui_list_get -id CovDetail.1 -text 0 $item]
    cp_query pre_count [list gui_list_get_selected -id CovDetail.1 -count]
    cp_query pre_flat [list gui_list_get_selected -id CovDetail.1 -flat]
    cp_need [expr {[gui_list_get_selected -id CovDetail.1 -count] == 0}] "Unexpected preselection; no arbitrary cleanup"
    gui_list_select -id CovDetail.1 -select [list $path]
    foreach {key options} {
        count {-count} first {-first} flat {-flat} first_flat {-first -flat}
        unique_first {-first -unique_names} object_id {-first -object_id}
    } {cp_query $key [concat [list gui_list_get_selected -id CovDetail.1] $options]}
    set first [lindex [cp_query first_repeat [list gui_list_get_selected -id CovDetail.1 -first]] 1]
    set candidates [list $item $path $meta $first]
    if {![catch {lindex $first 0} one]} {
        cp_record first_lindex1 0 $one; lappend candidates $one
        if {![catch {lindex $one 0} two]} {cp_record first_lindex2 0 $two; lappend candidates $two}
    }
    set index 0
    foreach token $candidates {
        cp_record candidate_${index} 0 $token
        foreach property {path meta} {
            cp_query candidate_${index}_${property} [list gui_list_get -id CovDetail.1 -$property $token]
        }
        cp_query candidate_${index}_text [list gui_list_get -id CovDetail.1 -text 0 $token]
        incr index
    }
    gui_exclusion_file -save -file [list [file join $::env(DVE_COVERAGE_OUTPUT) after-empty.el]]
    close $cp_stream
    puts CVXIF_ONE_ROW_READONLY_DONE
}
if {![info exists ::cp_test_only]} {
    if {[catch {cp_main} message]} {
        puts "CVXIF_ONE_ROW_READONLY_FAILED $message"
        set f [open [file join $::env(DVE_COVERAGE_OUTPUT) error.txt] {WRONLY CREAT EXCL}]
        puts $f $message; puts $f $::errorInfo; close $f
    }
    gui_exit -noprompt
}
