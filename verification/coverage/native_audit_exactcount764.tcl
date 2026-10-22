# Procedure-only successor utility. No GUI commands, load, exclusion, or exit.
# Count all observed names once; require the same singleton predicate as qc_audit.
proc native764_exact_names {seen wanted} {
    array set counts {}
    foreach name $seen {
        if {![info exists counts($name)]} {set counts($name) 0}
        incr counts($name)
    }
    foreach name $wanted {
        if {![info exists counts($name)] || $counts($name) != 1} {
            error "Missing/ambiguous exact source object $name"
        }
    }
}
