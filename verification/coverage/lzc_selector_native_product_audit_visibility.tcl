# Library-only successor. Source loading never opens DVE or runs a session.
set lpb_test_only 1
source {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/lzc_selector_native_product_batch.tcl}
rename lpb_row lpa_frozen_row
rename lpb_audit lpa_frozen_audit
set lpa_validated_scope {}
proc lpa_validate_branch_inventory {scope} {
    global lpa_expected
    lpd_require [info exists lpa_expected($scope)] "No observed native branch inventory for exact child"
    set actual {}
    array set seen {}
    set parent [gui_list_get -id CovDetail.1 -firstChild]
    while {$parent ne "" && $parent ne "0"} {
        lpd_require [expr {![info exists seen($parent)] && [array size seen] < 256}] "Native branch tree bound/cycle"
        set seen($parent) 1
        set path [gui_list_get -id CovDetail.1 -path $parent]
        set leaf [gui_list_get -id CovDetail.1 -firstChild $parent]
        while {$leaf ne "" && $leaf ne "0"} {
            lpd_require [expr {![info exists seen($leaf)] && [array size seen] < 256}] "Native branch leaf bound/cycle"
            set seen($leaf) 1
            set meta [gui_list_get -id CovDetail.1 -meta $leaf]
            set leafpath [gui_list_get -id CovDetail.1 -path $leaf]
            lpd_require [expr {[gui_list_get -id CovDetail.1 -childCount $leaf] == 0 && $leafpath eq "$path.$meta"}] "Native leaf parent/path differs"
            lappend actual [list $path $meta]
            set leaf [gui_list_get -id CovDetail.1 -nextSibling $leaf]
        }
        set parent [gui_list_get -id CovDetail.1 -nextSibling $parent]
    }
    lpd_require [expr {[lsort $actual] eq [lsort $lpa_expected($scope)]}] "Complete native branch parent/meta inventory differs"
}
proc lpb_row {row} {
    global lpa_binding lpa_expected lpa_validated_scope
    if {[lindex $row 1] ne "branch"} {
        set lpa_validated_scope {}
        # Condition/vector ListViews follow the successful discovery path, not a branch tree.
        return [lpa_frozen_row $row]
    }
    set position [lindex $row 5]
    lpd_require [info exists lpa_binding($position)] "No discovery-backed native token for protected branch position"
    set bound $lpa_binding($position)
    set scope [lindex $row 0]
    lpd_require [expr {[llength $bound] == 5 && [lindex $bound 0] eq $scope &&
        [lindex $bound 3] eq [lindex $row 2] && [lindex $bound 4] eq [lindex $row 4]}] "Protected position/discovery identity differs"
    lpd_require [regexp {^Branch([0-9]+)\.([01])$} [lindex $bound 2] unused identity arm] "Invalid observed native token"
    lpd_require [expr {$identity eq [lindex $bound 3] && $arm eq [lindex $bound 4] &&
        [lindex $bound 1] eq "Item$identity" && [info exists lpa_expected($scope)] &&
        [lsearch -exact $lpa_expected($scope) [list [lindex $bound 1] [lindex $bound 2]]] >= 0}] "Native token/parent binding differs"
    gui_list_action -id CoverageTable.1 -column Branch $scope
    lpd_require [expr {[gui_covdetail_query -id CovDetail.1 -name type] eq "Branch"}] "Not native branch detail"
    gui_list_expand -id CovDetail.1 -all {<root>}
    if {$lpa_validated_scope ne $scope} {
        lpa_validate_branch_inventory $scope
        set lpa_validated_scope $scope
    }
    # Selection uses the observed native meta verbatim, never XML or a reconstructed ID.
    lpd_select branch [lindex $bound 2]
    return branch
}
proc lpb_audit {path rows active} {
    global lpa_validated_scope
    set lpa_validated_scope {}
    return [lpa_frozen_audit $path $rows $active]
}
