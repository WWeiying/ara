# Local singleton measurement only; no final waiver application.
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/qbs_full_nested_native_body.tcl}
proc qs_clear {view} {
    foreach token [gui_list_get_selected -id CovDetail.1 -list $view -flat] {
        set name [qbf_name $token]
        if {$name ne ""} {gui_list_select -id CovDetail.1 -list $view -unselect [list $name]}
    }
    foreach token [gui_list_get_selected -id CovDetail.1 -list $view -flat] {
        qbf_require [expr {[qbf_name $token] eq ""}] "Previous selection remains"
    }
}
proc qs_select {view name} {
    qs_clear $view
    gui_list_select -id CovDetail.1 -list $view -select [list $name]
    qbf_require [expr {[gui_list_get_selected -id CovDetail.1 -list $view -count] == 1 &&
        [qbf_name [gui_list_get_selected -id CovDetail.1 -list $view -flat]] eq $name}] "Exact selection differs"
}
proc qs_bytes {path} {
    set stream [open $path r]
    fconfigure $stream -translation binary -encoding binary
    set data [read $stream]
    close $stream
    return $data
}
proc qs_signature {path empty} {
    global qs_scope qs_expression qs_module qs_metric qs_point qs_width qs_annotation
    set data [qs_bytes $path]
    if {$empty} {qbf_require [expr {$data eq ""}] "Global EL not empty"; return {}}
    qbf_require [expr {![regexp {[^\x09\x0a\x20-\x7e]} $data] && [string index $data end] eq "\n"}] "Invalid native EL bytes"
    set records {}
    foreach line [split $data "\n"] {if {$line ne ""} {lappend records $line}}
    qbf_require [expr {[llength $records] == 4}] "Global singleton EL shape differs"
    qbf_require [expr {[lindex $records 0] eq "CHECKSUM: \"$qs_module $qs_metric\"" &&
        [lindex $records 1] eq "INSTANCE: $qs_scope"}] "Native scope/checksums differ"
    set annotation [lindex $records 2]
    qbf_require [regexp {^ANNOTATION: "([^"]+)"$} $annotation unused value] "Invalid annotation"
    if {[regexp {^vcs_gen_start:row=0,b=0:vcs_gen_end:(.+)$} $value unused stripped]} {set value $stripped}
    qbf_require [expr {$value eq $qs_annotation}] "Annotation differs"
    qbf_require [regexp {^Condition ([0-9]+) "([0-9]+)" "([^"]+)" \(([0-9]+) "([01]+)"\)$} [lindex $records 3] unused id checksum shape vid vector] "Not singleton Condition/vector EL"
    qbf_require [expr {$checksum eq $qs_point && $shape eq "$qs_expression $qs_width -1" && $vector eq "11"}] "Native point/expression/vector differs"
    return [list $id $vid]
}
proc qs_save {name empty} {
    global qs_output
    set path [file join $qs_output $name]
    gui_exclusion_file -save -file [list $path]
    set signature [qs_signature $path $empty]
    qbf_emit [list saved $name $signature]
    return $signature
}
proc qs_audit {stage active} {
    global qs_meta qs_parent
    foreach group [list [list $qs_meta {01 10 11}] [list $qs_parent {00 01 10}]] {
        set meta [lindex $group 0]; set names [lindex $group 1]
        qs_select cond $meta
        set actual {}
        foreach token [gui_list_get_selected -id CovDetail.1 -list vector -all -flat] {lappend actual [qbf_name $token]}
        qbf_require [expr {[lsort $actual] eq [lsort $names]}] "Actual neighbor truth table differs"
        foreach vector $names {
            qs_select vector $vector
            set excluded [gui_exclusion -id CovDetail.1 -list vector -excluded -selected]
            set expected [expr {$active && $meta eq $qs_meta && $vector eq "11"}]
            qbf_require [expr {($excluded eq "0" || $excluded eq "1") && $excluded == $expected}] "Neighbor exclusion differs"
            qbf_emit [list audit $stage $meta $vector $excluded]
        }
    }
}
proc qs_run {} {
    global qs_scope qs_parent qs_expression qs_meta qbf_seen qbf_nodes qbf_matches
    gui_cov_show_cond_ids -show 0
    gui_list_action -id CoverageTable.1 -column Condition $qs_scope
    qbf_require [expr {[gui_covdetail_query -id CovDetail.1 -name type] eq "Condition"}] "Wrong view"
    gui_list_expand -id CovDetail.1 -all {<root>}
    set parents {}; array set seen {}; set n 0
    set handle [gui_list_get -id CovDetail.1 -firstChild]
    while {$handle ne "" && $handle ne "0"} {
        qbf_require [expr {$n < 8192 && ![info exists seen($handle)]}] "Root traversal bound/cycle"
        set seen($handle) 1; incr n
        if {[gui_list_get -id CovDetail.1 -meta $handle] eq $qs_parent} {lappend parents $handle}
        set handle [gui_list_get -id CovDetail.1 -nextSibling $handle]
    }
    qbf_require [expr {[llength $parents] == 1}] "Unique actual parent absent"
    set parent [lindex $parents 0]
    qbf_require [expr {[gui_list_get -id CovDetail.1 -path $parent] eq $qs_parent}] "Parent path differs"
    array set qbf_seen {}; set qbf_nodes 0; set qbf_matches {}
    qbf_children $parent 0 $qs_parent $qs_parent $qs_expression
    qbf_require [expr {[llength $qbf_matches] == 1}] "Unique actual nested object absent"
    set object [lindex $qbf_matches 0]; set qs_meta [lindex $object 2]
    qbf_emit [list object $qs_scope $qs_expression $qs_parent $object]
    qs_save initial-empty.el 1
    qs_audit before 0
    qs_save before-empty.el 1
    qs_select cond $qs_meta; qs_select vector 11
    global qs_annotation
    gui_exclude_items -id CovDetail.1 -list vector -selected -annotation $qs_annotation
    gui_exclusion -id CoverageTable.1 -recalculate
    qs_audit selected 1
    set first [qs_save first.el 0]
    gui_exclusion -reset
    qs_audit reset 0; qs_save reset-empty.el 1
    global qs_output
    gui_exclusion_file -load -file [list [file join $qs_output first.el]]
    gui_exclusion -id CoverageTable.1 -recalculate
    qs_audit reloaded 1
    set second [qs_save second.el 0]
    qbf_require [expr {$first eq $second && [qs_bytes [file join $qs_output first.el]] eq [qs_bytes [file join $qs_output second.el]]}] "Reload signature drift"
    gui_exclusion -reset
    qs_audit final 0; qs_save final-empty.el 1
    qbf_emit [list complete SINGLETON11_SIGNATURE_PROTECTION_ONLY_FULL1792_HOLD]
}
if {![info exists qs_test_only]} {
    source $env(QBS_SINGLETON_SELECTION)
    set qbf_stream [open [file join $qs_output native-singleton.tcllist] w]
    set failed [catch {
        gui_open_cov -hier $qs_design -testdir $qs_testdir -test $qs_test -merge QBSSingleton11MeasurementOnly
        gui_list_expand -id CoverageTable.1 -all {<root>}
        qs_run
    } message]
    set cleanup_failed [catch {gui_exclusion -reset; qs_save cleanup-empty.el 1} cleanup]
    qbf_emit [list terminal $failed $message $cleanup_failed $cleanup]
    close $qbf_stream
    if {$failed || $cleanup_failed} {puts "QBS_SINGLETON_HOLD $message cleanup=$cleanup"} else {puts QBS_SINGLETON_CAPTURED_FULL1792_HOLD}
    gui_exit -noprompt
}
