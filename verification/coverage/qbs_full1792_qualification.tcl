# Qualification in a disposable session only. Never final application.
set qs_test_only 1
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/qbs_nested_singleton11.tcl}
rename qbf_emit qn_log
proc qbf_emit {row} {
    global qn_meta
    if {[lindex $row 0] eq "object"} {
        set key [list [lindex $row 1] [lindex $row 2]]
        qbf_require [expr {![info exists qn_meta($key)]}] "Duplicate observed native object"
        set qn_meta($key) [lindex $row 6]
    }
    qn_log $row
}
proc qn_signature {path empty} {
    global qn_expected qs_annotation qn_scope_names
    set data [qs_bytes $path]
    if {$empty} {qbf_require [expr {$data eq ""}] "Global population not empty"; return}
    qbf_require [expr {[string length $data] < 4194304 && ![regexp {[^\x09\x0a\x20-\x7e]} $data] && [string index $data end] eq "\n"}] "Invalid native bytes"
    set scope {}; set checksum {}; set populated 0; set count 0; set annotations 0
    array set seen {}; array set identities {}; array set vectors {}
    foreach line [split $data "\n"] {
        if {$line eq ""} {continue}
        if {[regexp {^CHECKSUM: "([0-9]+) ([0-9]+)"$} $line unused module metric]} {
            qbf_require [expr {$scope eq "" || $populated}] "Whole instance forbidden"
            set checksum [list $module $metric]; set scope {}; set populated 0
            qbf_require [expr {$checksum eq {1651389237 2947893042}}] "Wrong module/metric"
        } elseif {[regexp {^INSTANCE: (.+)$} $line unused next_scope]} {
            qbf_require [expr {$checksum ne "" && ($scope eq "" || $populated) && [lsearch -exact $qn_scope_names $next_scope] >= 0}] "Wrong/whole scope"
            set scope $next_scope; set populated 0
        } elseif {[regexp {^ANNOTATION: "([^"]+)"$} $line unused value]} {
            qbf_require [expr {$scope ne ""}] "Annotation without scope"
            if {[regexp {^vcs_gen_start:row=[0-3],b=[0-9]+:vcs_gen_end:(.+)$} $value unused stripped]} {set value $stripped}
            qbf_require [expr {$value eq $qs_annotation}] "Foreign annotation"
            incr annotations
        } else {
            qbf_require [expr {$scope ne ""}] "Point without scope"
            qbf_require [regexp {^Condition ([0-9]+) "([0-9]+)" "([^"]+) ([0-9]+) (-?[0-9]+)" \(([0-9]+) "([01]+)"\)$} $line unused id point expression width bit vid vector] "Non-vector/whole Condition forbidden"
            set key [list $scope $expression $vector]
            qbf_require [expr {[info exists qn_expected($key)] && ![info exists seen($key)] && $bit eq "-1" && [list $point $width] eq $qn_expected($key)}] "Extra/duplicate/changed signature"
            set seen($key) 1; set populated 1; incr count
            set identity [list $scope $id]
            if {[info exists identities($identity)]} {qbf_require [expr {$identities($identity) eq $expression}] "Condition ID alias"}
            set identities($identity) $expression
            set vk [list $scope $id $vid]
            if {[info exists vectors($vk)]} {qbf_require [expr {$vectors($vk) eq $vector}] "Vector ID alias"}
            set vectors($vk) $vector
        }
    }
    qbf_require [expr {$count == 1792 && [array size seen] == [array size qn_expected] && $populated && $annotations > 0}] "Incomplete1792 signature"
}
proc qn_save {name empty} {
    global qs_output
    set path [file join $qs_output $name]
    gui_exclusion_file -save -file [list $path]
    qn_signature $path $empty
    qn_log [list saved $name]
}
proc qn_view {scope} {
    gui_list_action -id CoverageTable.1 -column Condition $scope
    qbf_require [expr {[gui_covdetail_query -id CovDetail.1 -name type] eq "Condition"}] "Wrong native metric"
}
proc qn_audit {stage active} {
    global qn_scopes qn_meta
    set count 0; set targets 0
    foreach bank $qn_scopes {
        set scope [lindex $bank 0]; qn_view $scope
        foreach group [lindex $bank 1] {
            set expression [lindex $group 0]; set names [lindex $group 2]; set target [lindex $group 3]
            set key [list $scope $expression]
            qbf_require [expr {[info exists qn_meta($key)]}] "Actual native selector absent"
            qs_select cond $qn_meta($key)
            set actual {}
            foreach token [gui_list_get_selected -id CovDetail.1 -list vector -all -flat] {lappend actual [qbf_name $token]}
            qbf_require [expr {[lsort $actual] eq [lsort $names]}] "Native truth table changed"
            foreach vector $names {
                qs_select vector $vector
                set observed [gui_exclusion -id CovDetail.1 -list vector -excluded -selected]
                set expected [expr {$active && [lsearch -exact $target $vector] >= 0}]
                qbf_require [expr {($observed eq "0" || $observed eq "1") && $observed == $expected}] "Target/neighbor protection differs"
                qn_log [list audit $stage $scope $expression $qn_meta($key) $vector $observed]
                incr count; incr targets $expected
            }
        }
    }
    qbf_require [expr {$count == 3584 && $targets == (1792 * $active)}] "Audit population differs"
    qn_log [list stage $stage $count $targets]
}
proc qn_run {} {
    global qbf_scopes qn_scopes qn_meta qs_annotation qs_output
    qn_save initial-empty.el 1
    array set qn_meta {}
    foreach bank $qbf_scopes {qbf_scope [lindex $bank 0] [lindex $bank 1]}
    qbf_require [expr {[array size qn_meta] == 1344}] "Full actual object mapping incomplete"
    qn_audit before 0; qn_save before-empty.el 1
    set count 0
    foreach bank $qn_scopes {
        set scope [lindex $bank 0]; qn_view $scope
        foreach group [lindex $bank 1] {
            qs_select cond $qn_meta([list $scope [lindex $group 0]])
            foreach vector [lindex $group 3] {
                qs_select vector $vector
                gui_exclude_items -id CovDetail.1 -list vector -selected -annotation $qs_annotation
                incr count
            }
        }
    }
    qbf_require [expr {$count == 1792}] "Exact temporary population required"
    gui_exclusion -id CoverageTable.1 -recalculate
    qn_audit selected 1; qn_save first.el 0
    gui_exclusion -reset
    qn_audit reset 0; qn_save reset-empty.el 1
    gui_exclusion_file -load -file [list [file join $qs_output first.el]]
    gui_exclusion -id CoverageTable.1 -recalculate
    qn_audit reloaded 1; qn_save second.el 0
    qbf_require [expr {[qs_bytes [file join $qs_output first.el]] eq [qs_bytes [file join $qs_output second.el]]}] "Reload native signature drift"
    gui_exclusion -reset
    qn_audit final 0; qn_save final-empty.el 1
    qn_log [list complete FULL1792_SIGNATURE_PROTECTION_ONLY_NOT_APPLICATION]
}
if {![info exists qn_test_only]} {
    source $env(QBS_FULL1792_SELECTION)
    set qbf_stream [open [file join $qs_output native-qualification.tcllist] w]
    set failed [catch {
        gui_open_cov -hier $qs_design -testdir $qs_testdir -test $qs_test -merge QBSFull1792QualificationOnly
        gui_list_expand -id CoverageTable.1 -all {<root>}
        qn_run
    } message]
    set cleanup_failed [catch {gui_exclusion -reset; qn_save cleanup-empty.el 1} cleanup]
    qn_log [list terminal $failed $message $cleanup_failed $cleanup]
    close $qbf_stream
    if {$failed || $cleanup_failed} {puts "QBS_FULL1792_HOLD $message cleanup=$cleanup"} else {puts QBS_FULL1792_CAPTURED_PENDING_INDEPENDENT_INSPECT}
    gui_exit -noprompt
}
