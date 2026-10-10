# Diagnostic second-pass export, Tcl 8.4. The original run stays untouched.
source $env(LZC_FROZEN_HOOK)
rename lzc_formal_summary lzc_frozen_summary
proc lzc_formal_summary {id name} {
    set snapshot [string map {.csv.partial _firstpass.csv.partial} $name]
    lzc_frozen_summary $id $snapshot
    # Test whether materialized lazy nodes/idle GUI work leave stale text.
    update idletasks
    gui_list_expand -id $id -all {<root>}
    gui_exclusion -id $id -recalculate
    update idletasks
    lzc_frozen_summary $id $name
}
