# Read-only clock topology comparison for the proven Ara image and loader.
if {[llength $argv] != 1} { error "Usage: loader_clock_compare.tcl DCP" }
open_checkpoint [lindex $argv 0]
foreach kind {IBUFDS BUFGCE MMCME4_ADV} {
    foreach cell [get_cells -hier -quiet -filter "REF_NAME == $kind"] {
        if {![regexp {sys_clk|ddr|u_mmcme_adv_inst} $cell]} { continue }
        puts "CELL $kind $cell LOC=[get_property LOC $cell] SITE=[get_property SITE $cell]"
        if {$kind ne "MMCME4_ADV"} { continue }
        set pin [get_pins -quiet $cell/CLKIN1]
        set net [get_nets -quiet -of_objects $pin]
        puts "MMCM_INPUT $pin NET=$net"
        if {[llength $net] != 1} { continue }
        foreach source [get_pins -quiet -of_objects [get_nets -segments $net] -filter {DIRECTION == OUT}] {
            puts "MMCM_SOURCE $source CELL=[get_cells -of_objects $source]"
        }
    }
}
close_design
exit 0
