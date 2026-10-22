# Tcl8.4: exact serialized attributes, no order dependence or duplicate identities.
proc nem_records {raw} {
    if {$raw eq "" || [string index $raw end] ne "\n"} {error "Incomplete native stream"}
    if {[regexp {[^\x0a\x20-\x7e]} $raw]} {error "Noncanonical native bytes"}
    if {[string first "\n\n" $raw]>=0} {error "Unexpected blank native directive"}
    set owner {}
    set pending {}
    set header {}
    set count 0
    set block_kind {}
    set result {}
    array set seen {}
    foreach line [split $raw "\n"] {
        if {$line eq ""} {continue}
        if {[regexp {^CHECKSUM: "([0-9]+) ([0-9]+)"$} $line -> module metric]} {
            if {$pending ne "" || ($owner ne "" && $count==0) || $header ne ""} {error "Incomplete native block"}
            set header [list $module $metric]
            set owner {}
            set count 0
            set block_kind {}
            continue
        }
        if {[regexp {^INSTANCE: ?([A-Za-z_][A-Za-z0-9_]*(?:\[[0-9]+\])?(?:\.[A-Za-z_][A-Za-z0-9_]*(?:\[[0-9]+\])?)*)$} $line -> scope]} {
            if {$header eq "" || $owner ne ""} {error "Invalid native instance"}
            set owner [list $scope [lindex $header 0] [lindex $header 1]]
            set header {}
            continue
        }
        if {[regexp {^ANNOTATION: "((?:\\[\x20-\x7e]|[^"\\\n])*)"$} $line -> annotation]} {
            if {$owner eq "" || $pending ne ""} {error "Invalid native annotation"}
            set pending [list $annotation]
            continue
        }
        set kind {}
        if {[regexp {^Branch ([0-9]+) "([0-9]+)" "((?:\\[\x20-\x7e]|[^"\\\n])*)" \(([0-9]+)\) "((?:\\[\x20-\x7e]|[^"\\\n])*)"$} $line -> native checksum expression selector signature]} {
            set kind Branch
        } elseif {[regexp {^Condition ([0-9]+) "([0-9]+)" "((?:\\[\x20-\x7e]|[^"\\\n])*)" \(([0-9]+) "([01]+)"\)$} $line -> native checksum expression selector signature]} {
            set kind Condition
        }
        if {$kind eq "" || $owner eq "" || $pending eq ""} {error "Unknown/incomplete native directive"}
        if {$block_kind ne "" && $block_kind ne $kind} {error "Mixed native metric block"}
        set block_kind $kind
        set key [list [lindex $owner 0] $kind $native $selector]
        if {[info exists seen($key)]} {error "Duplicate native identity"}
        set seen($key) 1
        lappend result [concat $owner [list $kind $native $checksum $expression $selector $signature [lindex $pending 0]]]
        set pending {}
        incr count
    }
    if {$owner eq "" || $count==0 || $pending ne "" || $header ne ""} {error "Incomplete native tail"}
    return [lsort $result]
}

proc nem_require_equal {left right} {
    set a [nem_records $left]
    set b [nem_records $right]
    if {$a ne $b} {error "Exact native identity/attribute multiset differs"}
    return [llength $a]
}

proc nem_install {} {
    set body [info body qbsapp_session]
    set needle {lpd_require [expr {[lpb_bytes [file join $env(DVE_COVERAGE_OUTPUT) applied.el]] eq
        [lpb_bytes [file join $env(DVE_COVERAGE_OUTPUT) reloaded.el]]}] "Combined EL actual reload bytes differ"}
    set replacement {set nem_count [nem_require_equal [lpb_bytes [file join $env(DVE_COVERAGE_OUTPUT) applied.el]] [lpb_bytes [file join $env(DVE_COVERAGE_OUTPUT) reloaded.el]]]
    lpd_require [expr {$nem_count==5892}] "Exact5892 semantic reload population differs"
    puts EIGHT_NATIVE_ATTRIBUTE_MULTISET_EXACT5892}
    proc qbsapp_session {} [seven_replace_once $body $needle $replacement]
    puts EIGHT_NATIVE_MULTISET_HELPER_INSTALLED
}
