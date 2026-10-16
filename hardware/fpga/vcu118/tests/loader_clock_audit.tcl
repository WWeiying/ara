# Inspect the isolated loader's DDR reference clock without modifying the design.
if {[llength $argv] != 1} { error "Usage: loader_clock_audit.tcl OPT_DCP" }
open_checkpoint [lindex $argv 0]
set cells [get_cells -hier -quiet -filter {REF_NAME == BUFGCE}]
foreach cell $cells {
    if {![string match *sys_clk_250* $cell]} { continue }
    puts "BUFFER $cell"
    foreach pin [get_pins -of_objects $cell] {
        puts "PIN $pin DIR=[get_property DIRECTION $pin] NET=[get_nets -of_objects $pin]"
    }
}
foreach name {
    {loader_bd_i/sys_clk_250_buffer/U0/IBUF_OUT[0]}
    {loader_bd_i/sys_clk_250_buffer/U0/IBUF_OUT_BUFG[0]}
} {
    set net [get_nets -quiet $name]
    if {[llength $net] != 1} { error "Expected DDR reference net $name" }
    puts "NET $net"
    foreach property {CLOCK_BUFFER_TYPE CLOCK_DEDICATED_ROUTE CLOCK_ROOT} {
        puts "PROPERTY $property=[get_property $property $net]"
    }
    foreach pin [get_pins -of_objects [get_nets -segments $net]] {
        puts "LOAD $pin REF_PIN_NAME=[get_property REF_PIN_NAME $pin]"
    }
}
close_design
exit 0
