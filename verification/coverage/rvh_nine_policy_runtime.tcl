# Tcl8.4. RVH selectors and state are private; no dbg_* command or array replacement.
namespace eval rvh9 {variable before_complete 0}
proc rvh9::selection {raw} {
    set kept {}
    foreach token $raw {
        if {$token eq ""} {continue}
        lpd_require [regexp {^(Branch|MISSING_ELSE|MISSING_DEFAULT)[0-9]+\.[0-9]+$} $token] "RVH9 invalid nonempty token"
        lappend kept $token
    }
    lpd_require [expr {[llength [lsort -unique $kept]]==[llength $kept]}] "RVH9 duplicate token"
    return $kept
}
proc rvh9::select {meta} {
    lpd_require [regexp {^(Branch|MISSING_ELSE|MISSING_DEFAULT)[0-9]+\.[0-9]+$} $meta] "RVH9 invalid desired leaf"
    set old [rvh9::selection [gui_list_get_selected -id CovDetail.1 -list branch -flat]]
    if {[llength $old]} {gui_list_select -id CovDetail.1 -list branch -unselect $old}
    gui_list_select -id CovDetail.1 -list branch -select [list $meta]
    set got [rvh9::selection [gui_list_get_selected -id CovDetail.1 -list branch -flat]]
    lpd_require [expr {[llength $got]==1 && [lindex $got 0] eq $meta}] "RVH9 singleton readback differs"
}
proc rvh9::metadata {scope} {
    variable keys; variable expected
    gui_list_action -id CoverageTable.1 -column Branch $scope
    lpd_require [expr {[gui_covdetail_query -id CovDetail.1 -name type] eq "Branch"}] "RVH9 wrong type"
    gui_list_expand -id CovDetail.1 -all {<root>}
    array set found {}; array set seen {}
    set parent [gui_list_get -id CovDetail.1 -firstChild]
    while {$parent ne "" && $parent ne "0"} {
        set pp [gui_list_get -id CovDetail.1 -path $parent]
        lpd_require [expr {![info exists seen($pp)]}] "RVH9 tree cycle"
        set seen($pp) 1
        lpd_require [regexp {^Item([0-9]+)$} $pp unused parentid] "RVH9 unknown parent"
        set item [gui_list_get -id CovDetail.1 -firstChild $parent]
        while {$item ne "" && $item ne "0"} {
            set meta [gui_list_get -id CovDetail.1 -meta $item]
            set path [gui_list_get -id CovDetail.1 -path $item]
            lpd_require [regexp {^(Branch|MISSING_ELSE|MISSING_DEFAULT)([0-9]+)\.([0-9]+)$} $meta unused kind sid vid] "RVH9 unknown leaf"
            set key "$sid,$vid"
            lpd_require [expr {$sid eq $parentid && $path eq "$pp.$meta" && [gui_list_get -id CovDetail.1 -childCount $item]==0}] "RVH9 path/leaf mismatch"
            lpd_require [expr {![info exists found($key)] && [info exists expected($scope|$key)]}] "RVH9 duplicate/extra key"
            lpd_require [expr {[list $meta $path] eq $expected($scope|$key)}] "RVH9 measured binding changed"
            set found($key) [list $meta $path]
            set item [gui_list_get -id CovDetail.1 -nextSibling $item]
        }
        set parent [gui_list_get -id CovDetail.1 -nextSibling $parent]
    }
    lpd_require [expr {[lsort [array names found]] eq [lsort $keys($scope)]}] "RVH9 incomplete inventory"
    return [array get found]
}
proc rvh9::audit {stage active} {
    global env
    variable scopes; variable keys; variable targets
    set stream [open [file join $env(DVE_COVERAGE_OUTPUT) rvh states_$stage.tsv] w]
    puts $stream "scope\tmetric\tcoordinate\tmeta\tpath\texcluded"
    set count 0
    set failed [catch {
        foreach scope $scopes {
            array unset metadata
            array set metadata [rvh9::metadata $scope]
            foreach key $keys($scope) {
                set meta [lindex $metadata($key) 0];set path [lindex $metadata($key) 1]
                rvh9::select $meta
                set actual [gui_exclusion -id CovDetail.1 -list branch -excluded -selected]
                set wanted [expr {$active && [lsearch -exact $targets($scope) $key]>=0}]
                lpd_require [expr {($actual eq "0" || $actual eq "1") && $actual==$wanted}] "RVH9 target/protection mismatch"
                puts $stream "$scope\tbranch\t$key\t$meta\t$path\t$actual"
                incr count
            }
        }
    } message]
    close $stream
    qbsapp_root
    if {$failed} {error $message}
    lpd_require [expr {$count==1780}] "RVH9 incomplete full audit"
    puts "NINE_RVH_AUDIT $stage 1780"
}
proc nine_initialize {} {
    global env
    source [file join $env(DVE_COVERAGE_OUTPUT) eight-library.tcl]
    eight_initialize
    source [file join $env(DVE_COVERAGE_OUTPUT) rvh9-selection.tcl]
    set count 0;set targets 0
    foreach scope $::rvh9::scopes {
        incr count [llength $::rvh9::keys($scope)]
        incr targets [llength $::rvh9::targets($scope)]
    }
    lpd_require [expr {$count==1780 && $targets==247 && [llength $::rvh9::scopes]==14}] "RVH9 exact inventory required"
    rename qbs_audit nine_eight_audit
    proc qbs_audit {stage active} {
        nine_eight_audit $stage $active
        rvh9::audit $stage $active
        puts "NINE_FULL_AUDIT $stage 25446"
        if {$stage eq "before" && !$active} {set ::rvh9::before_complete 1}
    }
    rename seven_load nine_eight_load
    proc seven_load {path} {
        lpd_require [expr {$::rvh9::before_complete==1}] "Complete25446 before gate closed"
        nine_eight_load $path
    }
    set body [info body qbsapp_session]
    set body [seven_replace_once $body {combined-eight.el} {combined-nine.el}]
    set needle {lpd_require [expr {[lpb_bytes [file join $env(DVE_COVERAGE_OUTPUT) applied.el]] eq
        [lpb_bytes [file join $env(DVE_COVERAGE_OUTPUT) reloaded.el]]}] "Combined EL actual reload bytes differ"}
    set replacement {puts [exec $::rvh9::python -B $::rvh9::driver check-roundtrip --output $env(DVE_COVERAGE_OUTPUT) --contract-seal $::rvh9::callback_seal]}
    set body [seven_replace_once $body $needle $replacement]
    set body [seven_replace_once $body {puts EIGHT_ACTUAL_RELOAD_EXACT5892} {puts EIGHT_ACTUAL_RELOAD_EXACT5892
    puts NINE_ACTUAL_RELOAD_SIGNATURE6139}]
    proc qbsapp_session {} $body
    puts NINE_RUNTIME_INSTALLED
}
if {![info exists nine_library_only]} {
    set failed [catch {nine_initialize; qbsapp_session} message]
    if {$failed} {puts "NINE_ERROR $message\n$::errorInfo"}
    set cleanup {}
    if {[catch {gui_exclusion -reset} detail]} {lappend cleanup $detail}
    if {[llength [info commands nine_eight_audit]]} {
        if {[catch {qbsapp_root; qbs_audit final 0} detail]} {lappend cleanup $detail}
    } else {lappend cleanup {Incomplete nine initialization}}
    if {[llength [info commands dbg_save]]} {
        if {[catch {dbg_save final-empty.el 1} detail]} {lappend cleanup $detail}
    } else {lappend cleanup {Missing native save}}
    if {$failed || [llength $cleanup]} {puts "NINE_FAILED $message cleanup=$cleanup"} else {
        puts SIX_COMBO_DONE_EXACT5808
        puts EIGHT_DONE_EXACT5892
        puts NINE_DONE_EXACT6139
    }
    gui_exit -noprompt
}
