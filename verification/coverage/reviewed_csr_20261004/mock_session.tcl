# Offline API model only. No DVE, native .el serialization, or external command.
set fixture [lindex $argv 0]
set hook [lindex $argv 1]
set scenario [lindex $argv 2]
source $fixture
set parents {}
array set children {}
array set paths {}
array set excluded {}
array set saved {}
set expected {}
foreach row $mock_rows {
    set meta [lindex $row 0]
    set path [lindex $row 1]
    set parent [lindex [split $path .] 0]
    if {![info exists children($parent)]} {
        set children($parent) {}
        lappend parents $parent
    }
    lappend children($parent) $meta
    set paths($meta) $path
    if {[lindex $row 2]} {lappend expected $meta}
}
if {$scenario eq "missing_metadata"} {
    set p [lindex $parents end]
    set children($p) [lrange $children($p) 0 end-1]
}
set selection {}
set loads 0
set saves 0
set observers 0
set resets 0
set callbacks 0
set summaries 0
proc insist {value message} {if {!$value} {error "MOCK_ASSERT $message"}}
proc gui_list_action {args} {return}
proc gui_covdetail_query {args} {return Branch}
proc gui_list_expand {args} {return}
proc gui_list_get {args} {
    insist [expr {[lrange $args 0 1] eq "-id CovDetail.1"}] "wrong detail view"
    set op [lindex $args 2]
    set handle [lindex $args end]
    if {$op eq "-firstChild"} {
        if {[llength $args] == 3} {return [lindex $::parents 0]}
        return [lindex $::children($handle) 0]
    }
    if {$op eq "-nextSibling"} {
        if {[info exists ::children($handle)]} {
            set siblings $::parents
        } else {
            set parent [lindex [split $::paths($handle) .] 0]
            set siblings $::children($parent)
        }
        return [lindex $siblings [expr {[lsearch -exact $siblings $handle] + 1}]]
    }
    if {[info exists ::children($handle)]} {
        insist [expr {$op eq "-path"}] "parent query"
        return $handle
    }
    set meta $handle
    if {$::scenario eq "metadata_alias" && $handle eq "Branch3.22"} {set meta MISSING_ELSE3.22}
    if {$::scenario eq "duplicate_metadata" && $handle eq "Branch3.23"} {set meta Branch3.22}
    switch -- $op {
        -meta {return $meta}
        -path {
            set parent [lindex [split $::paths($handle) .] 0]
            return "$parent.$meta"
        }
        -childCount {return 0}
        default {error "unsupported mock list API $args"}
    }
}
proc gui_list_get_selected {args} {return $::selection}
proc gui_list_select {args} {
    set op [lindex $args 4]
    set metas [lindex $args 5]
    foreach meta $metas {insist [info exists ::paths($meta)] "unknown selection"}
    if {$op eq "-unselect"} {
        insist [expr {[lsort $metas] eq [lsort $::selection]}] "unselect mismatch"
        set ::selection {}
    } elseif {$op eq "-select"} {
        set ::selection $metas
        if {$::scenario eq "selection_neighbor" && $metas eq "Branch3.22"} {lappend ::selection Branch3.21}
    } else {error "unsupported mock select API"}
}
proc gui_exclusion_file {args} {
    insist [expr {[llength $args] == 3 && [lindex $args 1] eq "-file" && [llength [lindex $args 2]] == 1}] "one exclusion file"
    set name [file tail [lindex [lindex $args 2] 0]]
    if {[lindex $args 0] eq "-save"} {
        incr ::saves
        set ::saved($name) [array names ::excluded]
    } elseif {[lindex $args 0] eq "-load"} {
        insist [expr {$name eq "points.el" && $::loads == 0 && [array size ::excluded] == 0}] "one clean union load"
        incr ::loads
        foreach meta $::expected {set ::excluded($meta) 1}
        if {$::scenario eq "missing_loaded"} {unset ::excluded(Branch3.22)}
        if {$::scenario eq "neighbor_loaded"} {set ::excluded(Branch3.21) 1}
        puts "All exclusions successfully imported and applied."
    } else {error "unsupported mock exclusion-file API"}
}
proc gui_exclude_items {args} {
    insist [expr {[lrange $args 0 1] eq "-id CoverageTable.1" && [lindex $args 4] eq "-recursive"}] "observer API"
    set path [lindex [lindex $args end] 0]
    insist [expr {[lsearch -exact $::mock_observers $path] >= 0}] "foreign observer"
    incr ::observers
}
proc gui_exclusion {args} {
    if {$args eq "-reset"} {
        incr ::resets
        if {$::scenario ne "reset_dirty"} {array unset ::excluded; array set ::excluded {}}
        return
    }
    if {[lindex $args end] eq "-recalculate"} {return}
    insist [expr {$args eq "-id CovDetail.1 -list branch -excluded -selected"}] "state API"
    foreach meta $::selection {if {[info exists ::excluded($meta)]} {return 1}}
    return 0
}
proc gui_cov_excl_review {args} {
    insist [expr {$args eq "-isEmpty"}] "review API"
    return [expr {$::scenario ne "review_pending"}]
}
proc gui_list_get_property {args} {
    set column [lindex $args 3]
    if {$column > 9} {error "end of columns"}
    return [lindex {Line Condition Branch FSM Toggle} [expr {$column - 5}]]
}
proc csv_row {stream values} {puts $stream [join $values ,]}
proc export_rows {stream id parent depth columns} {
    incr ::summaries
    set ::row_count 1
    puts $stream "ara_tb,0,1,2,3,4,5"
}
rename exec {}
proc exec {args} {
    insist [expr {[llength $args] == 11 && [lrange $args 0 1] eq "python3 -B" && [lindex $args 9] eq "--session"}] "validator API"
    insist [expr {[lindex $args 7] eq "--snapshot-sha256" && [lindex $args 8] eq $::env(CSR_SNAPSHOT_SHA256)}] "reviewed root binding"
    set stage [lindex $args 10]
    incr ::callbacks
    if {$stage eq "raw"} {
        if {$::scenario eq "raw_mismatch"} {error "MOCK_RAW_MISMATCH"}
        insist [expr {$::loads == 0 && [llength $::saved(initial-empty.el)] == 0}] "raw not empty"
    } elseif {$stage eq "saved"} {
        if {$::scenario eq "native_mismatch"} {error "MOCK_NATIVE_MISMATCH"}
        insist [expr {[lsort $::saved(exclusions.el)] eq [lsort $::expected] && $::observers == 10}] "wrong saved set"
    } elseif {$stage eq "reset"} {
        insist [expr {[llength $::saved(final-empty.el)] == 0 && $::summaries == 2}] "bad final reset/raw"
    } else {error "unsupported validator stage"}
    return "CSR_RUNTIME_CHECK_OK $stage"
}
source $hook
# Every retained core command exists in Tcl 8.4; unavailable/new commands vanish.
set allowed {array break catch close continue error eval expr fconfigure file for foreach global if incr info join lappend lindex linsert list llength lrange lsearch lsort open proc puts read regexp rename return set source split string switch unset while insist exec gui_list_action gui_covdetail_query gui_list_expand gui_list_get gui_list_get_selected gui_list_select gui_exclusion_file gui_exclude_items gui_exclusion gui_cov_excl_review gui_list_get_property csv_row export_rows}
foreach command [info commands csr_*] {lappend allowed $command}
lappend allowed apply_reviewed_waivers
set removed {}
foreach command [info commands] {
    if {[lsearch -exact $allowed $command] < 0} {
        lappend removed $command
        rename $command {}
    }
}
set failure [catch {apply_reviewed_waivers CoverageTable.1} message]
if {$scenario eq "ok"} {
    insist [expr {!$failure && $loads == 1 && $observers == 10 && $saves == 3 && $resets == 1 && $callbacks == 3 && [array size excluded] == 0}] "happy path incomplete: $message"
} else {
    insist $failure "fault not rejected"
    puts "MOCK_REJECTED $message"
}
puts "MOCK_RESULT $scenario PASS loads=$loads observers=$observers resets=$resets"
puts "MOCK_REMOVED $removed"
