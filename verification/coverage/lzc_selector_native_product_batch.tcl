# One product singleton measurement session; no final application or aggregate EL.
set lpd_test_only 1
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/lzc_selector_native_product_discover.tcl}
proc lpb_save {path empty} {
    gui_exclusion_file -save -file [list $path]
    lpd_require [expr {($empty && [file size $path] == 0) || (!$empty && [file size $path] > 0)}] "Global saved exclusion population differs"
}
proc lpb_bytes {path} {
    set stream [open $path r]
    set data [read $stream]
    close $stream
    return $data
}
proc lpb_signature {path target identity} {
    set seen 0
    set checks 0
    set scopes 0
    set expression [lindex $target 4]
    foreach line [split [lpb_bytes $path] "\n"] {
        set line [string trim $line]
        if {$line eq "" || [string match {//*} $line] || [string match {ANNOTATION:*} $line]} {continue}
        if {[regexp {^CHECKSUM: "([0-9]+) ([0-9]+)"$} $line unused module metric]} {
            incr checks
            lpd_require [expr {$module eq "3250293308" && $metric eq [lindex $target 5]}] "Native module/metric checksum differs"
        } elseif {[regexp {^INSTANCE: (.+)$} $line unused scope]} {
            incr scopes
            lpd_require [expr {$scope eq [lindex $target 2]}] "Native exact child differs"
        } elseif {[lindex $target 3] eq "cond"} {
            lpd_require [regexp {^Condition ([0-9]+) "([0-9]+)" "([^"]+) 1 -1" \(([0-9]+) "1"\)$} $line unused native point expr vector] "Not exact singleton true condition"
            lpd_require [expr {$point eq [lindex $target 6] && $expr eq $expression}] "Condition native signature differs"
            incr seen
        } else {
            lpd_require [regexp {^Branch ([0-9]+) "([0-9]+)" "([^"]+)" \(0\) "([^"]+)"$} $line unused native point expr signature] "Not exact singleton true branch"
            lpd_require [expr {$native eq $identity && $point eq [lindex $target 6] && $expr eq $expression && $signature eq "$expression 1"}] "Branch native signature differs"
            incr seen
        }
    }
    lpd_require [expr {$seen == 1 && $checks == 1 && $scopes == 1}] "Global EL is not exactly one approved child point"
}
proc lpb_branch_binding {target stream} {
    set scope [lindex $target 2]
    set expected [lindex $target 4]
    gui_list_action -id CoverageTable.1 -column Branch $scope
    gui_list_expand -id CovDetail.1 -all {<root>}
    set matches {}
    array set visited {}
    set parent [gui_list_get -id CovDetail.1 -firstChild]
    while {$parent ne "" && $parent ne "0"} {
        lpd_require [expr {![info exists visited($parent)] && [array size visited] < 128}] "Branch native parent traversal bound"
        set visited($parent) 1
        set path [gui_list_get -id CovDetail.1 -path $parent]
        set cells {}
        set matched 0
        for {set col 0} {$col < 6} {incr col} {
            set value {}
            set failed [catch {gui_list_get -id CovDetail.1 -text $col $parent} value]
            lappend cells [list $col $failed $value]
            if {!$failed && $value eq $expected} {set matched 1}
        }
        puts $stream [list parent $scope $path $cells]
        flush $stream
        if {$matched} {
            lpd_require [regexp {^Item([0-9]+)$} $path unused identity] "Unexpected native parent path"
            set arms {}
            set leaf [gui_list_get -id CovDetail.1 -firstChild $parent]
            while {$leaf ne "" && $leaf ne "0"} {
                lpd_require [expr {[llength $arms] < 2}] "Unexpected native branch child count"
                set meta [gui_list_get -id CovDetail.1 -meta $leaf]
                lpd_require [regexp {^Branch([0-9]+)\.([0-9]+)$} $meta unused id arm] "Unexpected native branch meta"
                lpd_require [expr {$id eq $identity}] "Native parent/leaf identity differs"
                lappend arms $arm
                set leaf [gui_list_get -id CovDetail.1 -nextSibling $leaf]
            }
            lpd_require [expr {[lsort $arms] eq {0 1}}] "Complete native branch true/false arms required"
            lappend matches $identity
        }
        set parent [gui_list_get -id CovDetail.1 -nextSibling $parent]
    }
    if {[llength $matches] != 1} {return {}}
    puts $stream [list binding $scope [lindex $matches 0] $expected]
    flush $stream
    return [lindex $matches 0]
}
proc lpb_row {row} {
    set scope [lindex $row 0]
    if {[lindex $row 1] eq "branch"} {
        gui_list_action -id CoverageTable.1 -column Branch $scope
        lpd_select branch "Branch[lindex $row 2].[lindex $row 4]"
        return branch
    }
    gui_list_action -id CoverageTable.1 -column Condition $scope
    lpd_select cond [lindex $row 3]
    lpd_select vector [lindex $row 4]
    return vector
}
proc lpb_audit {path rows active} {
    set stream [open $path w]
    puts $stream "position\tscope\tmetric\tnative_id\texpression\tvector\texcluded"
    set failed [catch {
        foreach row $rows {
            set listname [lpb_row $row]
            set value [gui_exclusion -id CovDetail.1 -list $listname -excluded -selected]
            lpd_require [expr {($value eq "0" || $value eq "1") && $value == ([lindex $row 5] == $active)}] "Protected/target native state differs"
            puts $stream "[lindex $row 5]\t[lindex $row 0]\t[lindex $row 1]\t[lindex $row 2]\t[lindex $row 3]\t[lindex $row 4]\t$value"
        }
    } message]
    close $stream
    if {$failed} {error $message}
}
proc lpb_session {} {
    global env lpd_design lpd_testdirs lpd_tests lpd_children lpb_targets lpb_rows lpb_output
    source $env(LZC_SELECTOR_NATIVE_PRODUCT_SELECTION)
    source $env(LZC_SELECTOR_NATIVE_BATCH_SELECTION)
    lpd_require [expr {[llength $lpd_tests] == 707 && [llength $lpb_rows] == 4200 && [llength $lpb_targets] == 120}] "Exact reviewed batch population required"
    gui_open_cov -hier $lpd_design -testdir $lpd_testdirs -test $lpd_tests -merge LZC707NativeSingletonMeasurementOnly
    gui_list_expand -id CoverageTable.1 -all {<root>}
    gui_cov_show_cond_ids -show 0
    lpb_save [file join $lpb_output initial-empty.el] 1
    lpb_audit [file join $lpb_output global-before.tsv] $lpb_rows -1
    foreach target $lpb_targets {
        set number [lindex $target 0]
        set case [file join $lpb_output [format "case-%03d" $number]]
        file mkdir $case
        set scope [lindex $target 2]
        set identity {}
        set active [lindex $target 7]
        if {[lindex $target 3] eq "branch"} {
            set stream [open [file join $case branch-parents.tcllist] w]
            set failed [catch {lpb_branch_binding $target $stream} identity]
            close $stream
            if {$failed} {error $identity}
            if {$identity eq ""} {
                puts "LZC_NATIVE_BATCH_HOLD $number exact_native_branch_expression_unbound"
                continue
            }
            set active -1
            foreach row $lpb_rows {
                if {[lindex $row 0] eq $scope && [lindex $row 1] eq "branch" && [lindex $row 2] eq $identity && [lindex $row 4] eq "0"} {
                    lpd_require [expr {$active == -1}] "Duplicate discovered native branch true arm"
                    set active [lindex $row 5]
                }
            }
            lpd_require [expr {$active >= 0}] "Resolved branch not in discovered native inventory"
        }
        set local {}
        foreach row $lpb_rows {if {[lindex $row 0] eq $scope} {lappend local $row}}
        lpb_save [file join $case initial-empty.el] 1
        lpb_audit [file join $case before.tsv] $local -1
        set listname [lpb_row [lindex $lpb_rows $active]]
        gui_exclude_items -id CovDetail.1 -list $listname -selected -annotation {Native singleton measurement only; no final processor exclusion application}
        gui_exclusion -id CoverageTable.1 -recalculate
        lpd_require [expr {[gui_cov_excl_review -isEmpty] == 1}] "Unexpected exclusion review state"
        lpb_audit [file join $case selected.tsv] $local $active
        set first [file join $case first.el]
        lpb_save $first 0
        lpb_signature $first $target $identity
        gui_exclusion -reset
        lpb_audit [file join $case reset.tsv] $local -1
        lpb_save [file join $case reset-empty.el] 1
        gui_exclusion_file -load -file [list $first]
        gui_exclusion -id CoverageTable.1 -recalculate
        lpd_require [expr {[gui_cov_excl_review -isEmpty] == 1}] "Unexpected reloaded review state"
        lpb_audit [file join $case reloaded.tsv] $local $active
        set second [file join $case second.el]
        lpb_save $second 0
        lpb_signature $second $target $identity
        lpd_require [expr {[lpb_bytes $first] eq [lpb_bytes $second]}] "Native signature save/reload bytes differ"
        gui_exclusion -reset
        lpb_audit [file join $case final.tsv] $local -1
        lpb_save [file join $case final-empty.el] 1
        puts "LZC_NATIVE_BATCH_SINGLETON_COMPLETE $number position=$active"
    }
    puts LZC_NATIVE_BATCH_SESSION_COMPLETE
}
if {![info exists lpb_test_only]} {
    set failed [catch {lpb_session} message]
    set cleanup {}
    if {[catch {gui_exclusion -reset} detail]} {lappend cleanup $detail}
    if {[info exists lpb_rows]} {
        if {[catch {lpb_audit [file join $lpb_output global-final.tsv] $lpb_rows -1} detail]} {lappend cleanup $detail}
        if {[catch {lpb_save [file join $lpb_output final-empty.el] 1} detail]} {lappend cleanup $detail}
    }
    if {$failed || [llength $cleanup]} {
        puts "LZC_NATIVE_BATCH_FAILED $message cleanup=$cleanup\n$::errorInfo"
    } else {puts LZC_NATIVE_BATCH_COMPLETE_PENDING_OFFLINE_VERIFICATION}
    gui_exit -noprompt
}
