# Tcl 8.4 only. Called by the unchanged hierarchy exporter after its raw report.
proc csr_require {condition message} {
    if {!$condition} {error $message}
}
proc csr_select {metas} {
    set old [gui_list_get_selected -id CovDetail.1 -list branch -flat]
    if {[llength $old]} {gui_list_select -id CovDetail.1 -list branch -unselect $old}
    if {[llength $metas]} {gui_list_select -id CovDetail.1 -list branch -select $metas}
    set actual [gui_list_get_selected -id CovDetail.1 -list branch -flat]
    csr_require [expr {[lsort $actual] eq [lsort $metas]}] "CSR selection differs"
}
proc csr_included {stage metas} {
    csr_select $metas
    set state [gui_exclusion -id CovDetail.1 -list branch -excluded -selected]
    csr_require [expr {$state == 0}] "CSR neighbor/reset exclusion at $stage"
    puts "CSR_INCLUDED $stage count=[llength $metas] excluded=0"
}
proc csr_check_python {stage} {
    global env csr_design
    puts [exec python3 -B [file join $env(CSR_REVIEW_BUNDLE) prepare_dve_waivers.py] --design $csr_design --output $env(DVE_COVERAGE_OUTPUT) --snapshot-sha256 $env(CSR_SNAPSHOT_SHA256) --session $stage]
}
proc csr_metadata {stage} {
    global csr_targets csr_all_keys env
    array set found {}
    set parent [gui_list_get -id CovDetail.1 -firstChild]
    while {$parent ne "" && $parent ne "0"} {
        set parentpath [gui_list_get -id CovDetail.1 -path $parent]
        csr_require [regexp {^Item([0-9]+)$} $parentpath unused parentid] "Unexpected CSR branch parent"
        set item [gui_list_get -id CovDetail.1 -firstChild $parent]
        while {$item ne "" && $item ne "0"} {
            set meta [gui_list_get -id CovDetail.1 -meta $item]
            set path [gui_list_get -id CovDetail.1 -path $item]
            csr_require [regexp {^(Branch|MISSING_ELSE)([0-9]+)\.([0-9]+)$} $meta unused kind sid vid] "Unexpected CSR metadata"
            csr_require [expr {$sid eq $parentid && $path eq "$parentpath.$meta"}] "CSR metadata/parent mismatch"
            csr_require [expr {[gui_list_get -id CovDetail.1 -childCount $item] == 0}] "CSR branch not a vector leaf"
            set key "$sid,$vid"
            csr_require [expr {![info exists found($key)]}] "Duplicate CSR vector"
            set found($key) [list $meta $path]
            set item [gui_list_get -id CovDetail.1 -nextSibling $item]
        }
        set parent [gui_list_get -id CovDetail.1 -nextSibling $parent]
    }
    csr_require [expr {[lsort [array names found]] eq [lsort $csr_all_keys] && [array size found] == 626}] "CSR full inventory differs"
    array set selected {}
    set wanted {}
    foreach row $csr_targets {
        set sid [lindex $row 0]
        set vid [lindex $row 1]
        set key "$sid,$vid"
        csr_require [expr {$key ne "3,187" && ![info exists selected($key)]}] "Forbidden/duplicate CSR target"
        csr_require [info exists found($key)] "Missing CSR target"
        csr_require [expr {[lindex $found($key) 0] eq [lindex $row 2] && [lindex $found($key) 1] eq [lindex $row 3]}] "CSR exact metadata changed"
        set selected($key) 1
        lappend wanted [lindex $found($key) 0]
    }
    set all {}
    set retained {}
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) "csr_metadata_$stage.tsv"] w]
    puts $stream "coordinate\tmeta\tpath\tselected"
    foreach key [lsort [array names found]] {
        set meta [lindex $found($key) 0]
        set path [lindex $found($key) 1]
        set selected_flag [info exists selected($key)]
        lappend all $meta
        if {!$selected_flag} {lappend retained $meta}
        puts $stream "$key\t$meta\t$path\t$selected_flag"
    }
    close $stream
    csr_require [expr {[llength $wanted] == 107 && [llength $retained] == 519}] "CSR selection/complement count differs"
    puts "CSR_METADATA $stage total=626 selected=107 retained=519"
    return [list $all $wanted $retained]
}
proc csr_summary {id filename} {
    global env seen row_count
    gui_list_expand -id $id -all {<root>}
    set columns {}
    set header {Name Depth}
    for {set column 5} {$column < 32} {incr column} {
        if {[catch {gui_list_get_property -id $id -column $column} label]} {break}
        set label [string trim $label]
        if {$label eq ""} {continue}
        lappend columns $column
        lappend header $label
    }
    csr_require [expr {[llength $columns] > 0}] "No coverage columns"
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) $filename] w]
    fconfigure $stream -encoding utf-8 -translation lf
    csv_row $stream $header
    array unset seen
    array set seen {}
    set row_count 0
    set failed [catch {export_rows $stream $id "" 0 $columns} message]
    close $stream
    if {$failed} {error $message}
    csr_require [expr {$row_count > 0}] "Empty CSR supplemental report"
}
proc apply_reviewed_waivers {id} {
    global env csr_scope csr_design csr_targets csr_all_keys waiver_scopes
    source [file join $env(CSR_REVIEW_BUNDLE) csr_selection.tcl]
    source [file join $env(DVE_COVERAGE_OUTPUT) waiver_plan.tcl]
    gui_exclusion_file -save -file [list [file join $env(DVE_COVERAGE_OUTPUT) initial-empty.el]]
    csr_check_python raw
    puts CSR_RAW_EMPTY
    gui_list_action -id $id -column Branch $csr_scope
    csr_require [expr {[gui_covdetail_query -id CovDetail.1 -name type] eq "Branch"}] "Not a CSR Branch detail view"
    gui_list_expand -id CovDetail.1 -all {<root>}
    set initial [csr_metadata before]
    csr_included before [lindex $initial 0]
    # One union load avoids replacing earlier scope exclusions with a second file.
    gui_exclusion_file -load -file [list [file join $env(DVE_COVERAGE_OUTPUT) points.el]]
    foreach {path recursive reason} $waiver_scopes {
        set args [list gui_exclude_items -id $id -annotation $reason]
        if {$recursive} {lappend args -recursive}
        lappend args [list $path]
        eval $args
    }
    gui_exclusion -id $id -recalculate
    csr_require [expr {[gui_cov_excl_review -isEmpty] == 1}] "Native exclusions need review"
    puts "CSR_REVIEW_EMPTY 1"
    gui_list_expand -id CovDetail.1 -all {<root>}
    set loaded [csr_metadata loaded]
    csr_included loaded [lindex $loaded 2]
    foreach meta [lindex $loaded 1] {
        csr_select [list $meta]
        csr_require [expr {[gui_exclusion -id CovDetail.1 -list branch -excluded -selected] == 1}] "Exact CSR target not excluded"
        puts "CSR_LOADED $meta excluded=1"
    }
    gui_exclusion_file -save -file [list [file join $env(DVE_COVERAGE_OUTPUT) exclusions.el]]
    csr_check_python saved
    puts CSR_NATIVE_SAVED_EXACT
    csr_summary $id summary_waived.csv.partial
    gui_exclusion -reset
    csr_included final [lindex $loaded 0]
    gui_exclusion_file -save -file [list [file join $env(DVE_COVERAGE_OUTPUT) final-empty.el]]
    csr_summary $id summary_after_reset.csv.partial
    csr_check_python reset
    puts CSR_SESSION_PROOF_DONE
    puts DVE_WAIVER_EXPORT_DONE
}
