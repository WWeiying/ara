set ::release_finalize_test_mode true
source [file join [file dirname [info script]] .. ethernet release_finalize_routed.tcl]
rename complete_repair::clock_signature complete_repair::original_clock_signature
rename complete_repair::async_signature complete_repair::original_async_signature
rename complete_repair::route_integrity complete_repair::original_route_integrity
proc complete_repair::clock_signature {} {
    return [expr {$::case eq "clock" && $::done ? "changed" : "original"}]
}
proc complete_repair::async_signature {} {
    return [expr {$::case eq "async" && $::done ? "changed" : "original"}]
}
proc complete_repair::route_integrity {} {
    lappend ::calls route_check
    if {$::case eq "route"} {error "Bad route"}
}
proc check_pulsed_latches {out {reject true}} {
    lappend ::calls [list pslt $reject]
    if {$reject && $::case eq "pslt"} {error "PSLT remains"}
}
proc route_design {args} {
    if {$args ne "-finalize"} {error "Only vendor finalize permitted"}
    lappend ::calls finalize
    set ::done true
    if {$::case eq "tool"} {error "Finalize failed"}
}
foreach case {pass clock async route pslt tool} {
    set calls {}
    set done false
    set failed [catch {release_finalize::optimize unused} message]
    if {$failed != ($case ne "pass")} {error "$case: $message"}
    if {$case eq "pass" && $calls ne {{pslt false} finalize route_check {pslt true}}} {
        error "Missing strict PSLT recheck: $calls"
    }
    if {$case eq "tool" && $calls ne {{pslt false} finalize}} {error "Continued after tool failure"}
    puts "PASS release finalize $case"
}
