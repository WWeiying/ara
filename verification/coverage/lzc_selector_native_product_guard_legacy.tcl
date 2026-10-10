# Candidate library only: no session, design load, exclusion, or auto-selfcheck.
proc lpn_guard_exclude {args} {
    lpd_require $::lpn_global_before_complete "Singleton forbidden before complete global4200 audit"
    lpd_require [expr {[llength $args] == 7 && [lindex $args 0] eq "-id" &&
        [lindex $args 1] eq "CovDetail.1" && [lindex $args 2] eq "-list" &&
        ([lindex $args 3] eq "branch" || [lindex $args 3] eq "vector") &&
        [lindex $args 4] eq "-selected" && [lindex $args 5] eq "-annotation"}] "Guard call differs from sealed singleton contract"
    return [eval [linsert $args 0 gui_exclude_items]]
}
proc lpng_preflight {} {
    lpd_require [expr {!$::lpn_global_before_complete}] "Preflight requires closed global4200 gate"
    set failed [catch {
        lpn_guard_exclude -id CovDetail.1 -list branch -selected -annotation {Native singleton measurement only; no final processor exclusion application}
    } message]
    lpd_require [expr {$failed == 1 && $message eq "Singleton forbidden before complete global4200 audit"}] "Guard parser/preflight failed before design load"
    return [info patchlevel]
}
proc lpng_echo {args} {return $args}
proc lpng_list_preflight {} {
    set payloads [list {spaces and {balanced braces}} {semicolon; error INJECTED} {[error INJECTED] $not_a_variable}]
    lappend payloads [format {%c unbalanced opening brace} 123]
    lappend payloads [format {%c unbalanced closing brace} 125]
    foreach annotation $payloads {
        set words [list -id CovDetail.1 -list branch -selected -annotation $annotation]
        set actual [eval [linsert $words 0 lpng_echo]]
        lpd_require [expr {$actual eq $words && [lindex $actual 6] eq $annotation}] "Safe list forwarding differs"
    }
    return [llength $payloads]
}
