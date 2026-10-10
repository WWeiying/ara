# HOST Tcl API model only. No Synopsys tool or real native file is generated.
set root [lindex $argv 0]
set fault [lindex $argv 1]
set env(DVE_COVERAGE_OUTPUT) [pwd]
set env(OPERAND_BUNDLE) [pwd]
set env(OPERAND_SNAPSHOT_SHA256) [string repeat a 64]
source selection.tcl
foreach s $oq_scopes {
    set mock_specs($s) {}
    foreach k $oq_keys($s) {
        set sid [lindex [split $k ,] 0]
        if {[lsearch -exact $mock_specs($s) $sid] < 0} {lappend mock_specs($s) $sid}
    }
}
set f [open fixture.native r]
set mock_native [read $f]
close $f
set mock_scope {}
set mock_selected {}
set mock_phase before
array set mock_excluded {}
proc gui_list_action {args} {set ::mock_scope [lindex $args end]; set ::mock_selected {}}
proc gui_list_expand {args} {return}
proc gui_covdetail_query {args} {return Branch}
proc gui_list_get {args} {
    set flag [lindex $args 2]
    set handle [lindex $args 3]
    set keys $::oq_keys($::mock_scope)
    set specs $::mock_specs($::mock_scope)
    if {$flag eq "-firstChild"} {
        if {$handle eq ""} {return p[lindex $specs 0]}
        set sid [string range $handle 1 end]
        if {$::fault eq "missing_leaf" && $sid == 4} {return 0}
        foreach k $keys {if {[lindex [split $k ,] 0] eq $sid} {return v$k}}
        return 0
    }
    if {$flag eq "-nextSibling"} {
        if {[string index $handle 0] eq "p"} {
            set pos [lsearch -exact $specs [string range $handle 1 end]]
            set next [lindex $specs [expr {$pos + 1}]]
            if {$next eq ""} {return 0}
            return p$next
        }
        set k [string range $handle 1 end]
        set next [lindex $keys [expr {[lsearch -exact $keys $k] + 1}]]
        if {$next ne "" && [lindex [split $next ,] 0] eq [lindex [split $k ,] 0]} {return v$next}
        return 0
    }
    if {$flag eq "-childCount"} {return 0}
    if {[string index $handle 0] eq "p"} {return Item[string range $handle 1 end]}
    set k [split [string range $handle 1 end] ,]
    set sid [lindex $k 0]
    set vid [lindex $k 1]
    if {$flag eq "-meta"} {return Branch$sid.$vid}
    if {$flag eq "-path"} {
        if {$::fault eq "bad_parent" && $sid == 4} {return Item0.Branch$sid.$vid}
        return Item$sid.Branch$sid.$vid
    }
    error "Unmodeled list flag $flag"
}
proc gui_list_get_selected {args} {return $::mock_selected}
proc gui_list_select {args} {
    if {[lindex $args 4] eq "-unselect"} {set ::mock_selected {}; return}
    set ::mock_selected [lindex $args 5]
    if {$::fault eq "selection_extra"} {lappend ::mock_selected Foreign}
}
proc mock_key {meta} {
    regexp {([0-9]+)\.([0-9]+)$} $meta unused sid vid
    return "$::mock_scope|$sid,$vid"
}
proc gui_exclude_items {args} {
    if {[lindex $args 1] ne "CovDetail.1"} {return}
    foreach m $::mock_selected {set ::mock_excluded([mock_key $m]) 1}
    set ::mock_phase selected
}
proc gui_exclusion {args} {
    if {[lindex $args 0] eq "-reset"} {
        array unset ::mock_excluded
        array set ::mock_excluded {}
        set ::mock_phase reset
        return
    }
    if {[lindex $args 2] eq "-recalculate"} {return}
    if {$::fault eq "initial_dirty" && $::mock_phase eq "before"} {return 1}
    foreach m $::mock_selected {if {[info exists ::mock_excluded([mock_key $m])]} {return 1}}
    return 0
}
proc gui_cov_excl_review {args} {return [expr {$::fault ne "review_pending"}]}
proc gui_exclusion_file {args} {
    set filename [lindex [lindex $args 2] 0]
    if {[lindex $args 0] eq "-load"} {
        foreach s $::oq_scopes {foreach k $::oq_targets($s) {set ::mock_excluded($s|$k) 1}}
        set ::mock_phase reloaded
        set s [lindex $::oq_scopes 0]
        if {$::fault eq "load_missing"} {unset ::mock_excluded($s|[lindex $::oq_targets($s) 0])}
        if {$::fault eq "load_neighbor"} {set ::mock_excluded($s|0,0) 1}
        return
    }
    set f [open $filename w]
    if {[array size ::mock_excluded]} {puts -nonewline $f $::mock_native}
    close $f
}
proc gui_list_get_property {args} {if {[lindex $args end] == 5} {return Line}; return {}}
proc csv_row {stream values} {puts $stream [join $values ,]}
proc export_rows {args} {set ::row_count 1}
rename exec mock_real_exec
proc exec {args} {
    set i [lsearch -exact $args --session]
    set stage [lindex $args [expr {$i + 1}]]
    if {$::fault eq "signature_changed" && $stage eq "second"} {error "Full native record mismatch"}
    if {$stage eq "first"} {
        set h [mock_real_exec sha256sum first.el]
        return "OQ_CALLBACK first\nOQ_FIRST_SHA [lindex $h 0]"
    }
    return "OQ_CALLBACK $stage"
}
# The real gap58 failure is modeled; no helper may define reserved 'view'.
rename proc mock_core_proc
mock_core_proc proc {name arguments body} {
    if {$name eq "view"} {error "Cannot create procedure named 'view' - existing command"}
    uplevel 1 [list mock_core_proc $name $arguments $body]
}
if {$fault eq "helper_collision"} {proc oq_view {} {return}}
if {[catch {source [file join $root dve_operand.tcl]; apply_reviewed_waivers CoverageTable.1} message]} {
    puts "MOCK_FAILED $message"
} else {puts DVE_COVERAGE_EXPORT_DONE}
