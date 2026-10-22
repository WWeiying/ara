# Single-session observation only. No exclusions, resets, saves, or bitmap decoding.
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/apply_points740_v4.tcl}

proc vd_query {command} {
    set rc [catch {uplevel #0 $command} value]
    set detail {}; if {$rc} {set detail $::errorInfo}
    return [list $rc $value $detail]
}
proc vd_record {stream value} {
    set bytes [encoding convertto utf-8 $value]
    puts -nonewline $stream "[string length $bytes]\n${bytes}\n"
}
proc vd_walk {stream item parent depth columns} {
    global vd_seen vd_rows
    while {$item ne "" && $item ne "0"} {
        if {[info exists vd_seen($item)]} {error "Repeated raw handle $item"}
        set vd_seen($item) 1
        set fields {}
        foreach key {path meta} {
            lappend fields [list $key [vd_query [list gui_list_get -id CovDetail.1 -$key $item]]]
        }
        lappend fields [list name [vd_query [list gui_list_get -id CovDetail.1 -text 0 $item]]]
        foreach c $columns {
            lappend fields [list text $c [vd_query [list gui_list_get -id CovDetail.1 -text $c $item]]]
        }
        set child [vd_query [list gui_list_get -id CovDetail.1 -firstChild $item]]
        set sibling [vd_query [list gui_list_get -id CovDetail.1 -nextSibling $item]]
        vd_record $stream [list rawrow $depth $parent $item $fields $child $sibling]
        incr vd_rows
        if {[lindex $child 0] || [lindex $sibling 0]} {error "Raw tree navigation failed"}
        vd_walk $stream [lindex $child 1] $item [expr {$depth + 1}] $columns
        set item [lindex $sibling 1]
    }
}
proc vd_capture {stage action} {
    global vd_seen vd_rows
    set stream [open [file join $::env(DVE_COVERAGE_OUTPUT) ${stage}.frames] {WRONLY CREAT EXCL}]
    fconfigure $stream -translation binary -encoding binary
    vd_record $stream [list snapshot $stage $::vd_scope $::vd_test]
    vd_record $stream [list action $action]
    foreach command [list [list gui_covdetail_query -id CovDetail.1 -name type] \
            [list gui_list_get_selected -id CovDetail.1 -flat] \
            [list gui_list_get_selected -id CovDetail.1 -count] \
            [list gui_list_get_selected -id CoverageTable.1 -flat] \
            [list gui_get_current_view]] {
        vd_record $stream [list context $command [vd_query $command]]
    }
    foreach view {tglListView tglDetailListView} {
        foreach key {names orders widths} {
            set command [list gui_get_state_value -category Layout_CovDetail_$view -key $key]
            vd_record $stream [list context $command [vd_query $command]]
        }
    }
    set header {}; set probes {}; set valid 1
    for {set c 0} {$c < 8} {incr c} {
        set result [vd_query [list gui_list_get_property -id CovDetail.1 -column $c]]
        vd_record $stream [list column_probe $c $result]
        lappend probes $result
        lappend header [lindex $result 1]
        if {[lindex $result 0]} {set valid 0}
    }
    set schema unknown; set count 8
    set main [list Variable { } {  } {   } Type Coverage Display {}]
    set detail [list Variable { } {  } {   } 0->1 1->0 {} {}]
    if {$valid && $header eq $main} {set schema tglListView; set count 7}
    if {$valid && $header eq $detail} {set schema tglDetailListView; set count 6}
    vd_record $stream [list schema $schema $count]
    set columns {}
    for {set c 0} {$c < $count} {incr c} {
        lappend columns $c
        vd_record $stream [list column $c [lindex $probes $c]]
    }
    set root [vd_query [list gui_list_get -id CovDetail.1 -firstChild]]
    vd_record $stream [list root $root]
    catch {unset vd_seen}; array set vd_seen {}; set vd_rows 0
    set rc [catch {
        if {[lindex $root 0]} {error "Raw root query failed"}
        vd_walk $stream [lindex $root 1] {} 0 $columns
        if {$schema eq "unknown"} {error "Unknown full column schema; raw eight-column tree retained"}
    } value]
    vd_record $stream [list end $rc $value $vd_rows]
    close $stream
    if {$rc} {error $value}
}
proc vd_click {path} {
    set steps {}
    set old [vd_query [list gui_list_get_selected -id CovDetail.1 -flat]]
    lappend steps [list selected_before $old]
    if {![lindex $old 0]} {
        foreach token [lindex $old 1] {
            lappend steps [list unselect $token [vd_query [list gui_list_select -id CovDetail.1 -unselect [list $token]]]]
        }
    }
    lappend steps [list select $path [vd_query [list gui_list_select -id CovDetail.1 -select [list $path]]]]
    lappend steps [list selected_readback [vd_query [list gui_list_get_selected -id CovDetail.1 -flat]]]
    lappend steps [list double_click $path [vd_query [list gui_cov_tgl_double_click -id CovDetail.1 -item $path]]]
    lappend steps [list events [vd_query [list gui_process_events -mstime 100]]]
    return $steps
}
proc vd_session {} {
    uplevel #0 [list source [file join $::env(DVE_COVERAGE_OUTPUT) selection.tcl]]
    foreach name {gui_cov_tgl_double_click gui_covdetail_query gui_list_get gui_list_get_property gui_list_select gui_get_state_value gui_get_current_view} {
        puts [list installed_help $name [vd_query [list help $name]]]
    }
    set dirs [glob -types d -directory [file join $::vd_vdb snps coverage db testdata] *]
    if {[llength $dirs] != 1 || [file join [file rootname $::vd_vdb] [file tail [lindex $dirs 0]]] ne $::vd_test} {
        error "Exactly one admitted PASS sample required"
    }
    gui_open_cov -hier $::vd_design -testdir [list $::vd_vdb] -test [list $::vd_test] -merge C910VectorDiscoveryOnly
    p740_root
    if {[p740_select $::vd_scope] ne $::vd_scope} {error "Exact single scope"}
    gui_list_action -id CoverageTable.1 -column Toggle $::vd_scope
    gui_list_expand -id CovDetail.1 -all {<root>}
    gui_process_events -mstime 100
    vd_capture initial [list setup_only]
    vd_capture click1 [vd_click {initial_divisor_in[55:0]}]
    vd_capture click2 [vd_click {initial_remainder_in[60:0]}]
    vd_capture click3_restore_probe [vd_click {initial_divisor_in[55:0]}]
    set f [open [file join $::env(DVE_COVERAGE_OUTPUT) discovery-done.txt] {WRONLY CREAT EXCL}]
    puts $f C910_SINGLE_SCOPE_DISCOVERY_DONE_NOT_QUALIFICATION; close $f
}
if {![info exists ::vd_host_test_only]} {
    if {[catch {vd_session} message]} {
        set f [open [file join $::env(DVE_COVERAGE_OUTPUT) discovery-error.txt] {WRONLY CREAT EXCL}]
        puts $f $message; puts $f $::errorInfo; close $f
        puts [list DISCOVERY_FAILED $message]
    }
    gui_exit -noprompt
}
