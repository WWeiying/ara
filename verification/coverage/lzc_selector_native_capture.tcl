# Tcl 8.4. Standalone calibration only; each row captured separately, then reset.
proc lsn_require {ok message} {if {!$ok} {error $message}}
proc lsn_select {listname name} {
    set n [gui_list_get_selected -id CovDetail.1 -list $listname -count]
    while {$n > 0} {
        set old [gui_list_get_selected -id CovDetail.1 -list $listname -first]
        gui_list_select -id CovDetail.1 -list $listname -unselect [lindex $old 0]
        set after [gui_list_get_selected -id CovDetail.1 -list $listname -count]
        lsn_require [expr {$after < $n}] "Selection clearing did not progress"
        set n $after
    }
    gui_list_select -id CovDetail.1 -list $listname -select [list $name]
    set got [gui_list_get_selected -id CovDetail.1 -list $listname -flat]
    lsn_require [expr {[llength $got] == 1 && [lindex $got 0] eq $name}] "Singleton identity differs"
}
proc lsn_branches {} {
    global lsn_scope lsn_rows
    gui_list_action -id CoverageTable.1 -column Branch $lsn_scope
    lsn_require [expr {[gui_covdetail_query -id CovDetail.1 -name type] eq "Branch"}] "Not branch view"
    gui_list_expand -id CovDetail.1 -all {<root>}
    array set seen {}
    set keys {}
    set parent [gui_list_get -id CovDetail.1 -firstChild]
    while {$parent ne "" && $parent ne "0"} {
        lsn_require [expr {![info exists seen($parent)]}] "Branch tree cycle"
        set seen($parent) 1
        set path [gui_list_get -id CovDetail.1 -path $parent]
        lsn_require [regexp {^Item([0-9]+)$} $path unused sid] "Unknown branch parent"
        set item [gui_list_get -id CovDetail.1 -firstChild $parent]
        while {$item ne "" && $item ne "0"} {
            lsn_require [expr {![info exists seen($item)]}] "Branch leaf cycle"
            set seen($item) 1
            set meta [gui_list_get -id CovDetail.1 -meta $item]
            set leafpath [gui_list_get -id CovDetail.1 -path $item]
            lsn_require [regexp {^Branch([0-9]+)\.([0-9]+)$} $meta unused id vector] "Unknown branch leaf"
            lsn_require [expr {$id eq $sid && $leafpath eq "$path.$meta" &&
                [gui_list_get -id CovDetail.1 -childCount $item] == 0}] "Branch path/ID differs"
            lappend keys "$id,$vector"
            set item [gui_list_get -id CovDetail.1 -nextSibling $item]
        }
        set parent [gui_list_get -id CovDetail.1 -nextSibling $parent]
    }
    set expected {}
    foreach row $lsn_rows {
        if {[lindex $row 0] eq "branch"} {lappend expected "[lindex $row 1],[lindex $row 2]"}
    }
    lsn_require [expr {[lsort $keys] eq [lsort $expected]}] "Complete branch inventory differs"
}
proc lsn_row {row} {
    global lsn_scope lsn_rows
    set metric [lindex $row 0]
    if {$metric eq "branch"} {
        gui_list_action -id CoverageTable.1 -column Branch $lsn_scope
        lsn_select branch "Branch[lindex $row 1].[lindex $row 2]"
        puts "LSN_NATIVE_BRANCH id=[lindex $row 1] vector=[lindex $row 2] columns=[list [gui_list_get_selected -id CovDetail.1 -list branch -flat -columns {ID Coverage}]]"
        return branch
    }
    gui_list_action -id CoverageTable.1 -column Condition $lsn_scope
    lsn_require [expr {[gui_covdetail_query -id CovDetail.1 -name type] eq "Condition"}] "Not condition view"
    lsn_select cond [lindex $row 3]
    set names [gui_list_get_selected -id CovDetail.1 -list vector -all -flat]
    set expected {}
    foreach candidate $lsn_rows {
        if {[lindex $candidate 0] eq "cond" && [lindex $candidate 1] eq [lindex $row 1]} {
            lappend expected [lindex $candidate 2]
        }
    }
    lsn_require [expr {[lsort $names] eq [lsort $expected]}] "Complete condition vector table differs"
    puts "LSN_NATIVE_CONDITION id=[lindex $row 1] expression=[list [lindex $row 3]] names=[list $names] columns=[list [gui_list_get_selected -id CovDetail.1 -list vector -all -flat -columns {ID Coverage 1}]]"
    lsn_select vector [lindex $row 2]
    return vector
}
proc lsn_audit {stage target} {
    global lsn_rows lsn_output
    lsn_branches
    set stream [open [file join $lsn_output "$stage.tsv"] w]
    puts $stream "position\tmetric\tid\tvector\texcluded"
    set failed [catch {
        set index 0
        foreach row $lsn_rows {
            set listname [lsn_row $row]
            set actual [gui_exclusion -id CovDetail.1 -list $listname -excluded -selected]
            lsn_require [expr {($actual eq "0" || $actual eq "1") && $actual == ($index == $target)}] "Protected/target state differs: $stage position=$index"
            puts $stream "$index\t[lindex $row 0]\t[lindex $row 1]\t[lindex $row 2]\t$actual"
            incr index
        }
    } message]
    close $stream
    if {$failed} {error $message}
}
proc lsn_save {name empty} {
    global lsn_output
    set path [file join $lsn_output $name]
    gui_exclusion_file -save -file [list $path]
    if {$empty} {
        lsn_require [expr {[file size $path] == 0}] "Global exclusion state is not empty"
    } else {lsn_require [expr {[file size $path] > 0}] "Native singleton capture is empty"}
}
proc lsn_same_file {first second} {
    global lsn_output
    set a [open [file join $lsn_output $first] r]
    set left [read $a]
    close $a
    set b [open [file join $lsn_output $second] r]
    set right [read $b]
    close $b
    lsn_require [expr {$left eq $right}] "Native saved signatures differ after reload"
}
proc lsn_session {} {
    global env lsn_scope lsn_vdb lsn_test lsn_targets lsn_rows lsn_output
    source $env(LZC_SELECTOR_NATIVE_SELECTION)
    lsn_require [expr {[string match "lzc_selector_native_*.dut" $lsn_scope]}] "Standalone scope required"
    gui_open_cov -hier $lsn_vdb -testdir [list $lsn_vdb] -test [list $lsn_test] -merge LZCSelectorNativeCalibrationOnly
    lsn_save initial-empty.el 1
    lsn_audit before -1
    foreach target $lsn_targets {
        set listname [lsn_row [lindex $lsn_rows $target]]
        gui_exclude_items -id CovDetail.1 -list $listname -selected -annotation {Standalone native identity experiment only; not product exclusion approval}
        gui_exclusion -id CoverageTable.1 -recalculate
        lsn_require [expr {[gui_cov_excl_review -isEmpty] == 1}] "Selection requires review"
        lsn_audit "selected-$target" $target
        lsn_save "first-$target.el" 0
        gui_exclusion -reset
        lsn_audit "reset-$target" -1
        lsn_save "reset-$target.el" 1
        gui_exclusion_file -load -file [list [file join $lsn_output "first-$target.el"]]
        gui_exclusion -id CoverageTable.1 -recalculate
        lsn_require [expr {[gui_cov_excl_review -isEmpty] == 1}] "Reload requires review"
        lsn_audit "reloaded-$target" $target
        lsn_save "second-$target.el" 0
        lsn_same_file "first-$target.el" "second-$target.el"
        gui_exclusion -reset
    }
}
if {![info exists lsn_library_only]} {
    set failed [catch {lsn_session} message]
    set cleanup {}
    if {[catch {gui_exclusion -reset} detail]} {lappend cleanup $detail}
    if {[info exists lsn_rows]} {
        if {[catch {lsn_audit final -1} detail]} {lappend cleanup $detail}
        if {[catch {lsn_save final-empty.el 1} detail]} {lappend cleanup $detail}
    }
    if {$failed || [llength $cleanup]} {
        puts "LZC_SELECTOR_NATIVE_FAILED $message cleanup=$cleanup"
    } else {puts LZC_SELECTOR_NATIVE_CAPTURE_COMPLETE_PENDING_SEMANTIC_REVIEW}
    gui_exit -noprompt
}
