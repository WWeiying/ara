# Read-only library for an already opened linked checkpoint. No timing update.
namespace eval fpga_control_trace {}
proc fpga_control_trace::property {name object} {
    if {$name ni [list_property $object]} {return {<unavailable>}}
    return [get_property $name $object]
}
proc fpga_control_trace::write {exact_net output} {
    # Filter by exact string after enumeration: RTL array brackets must not be
    # interpreted as glob patterns by get_nets.
    set matches {}
    foreach net [get_nets -hierarchical -quiet] {
        if {[get_property NAME $net] eq $exact_net} {lappend matches $net}
    }
    if {[llength $matches] != 1} {error "Expected one exact net: $exact_net"}
    set segments [get_nets -quiet -segments -of_objects $matches]
    set pins [get_pins -quiet -leaf -of_objects $segments]
    set f [open $output {WRONLY CREAT EXCL}]
    set code [catch {
        puts $f [list NET $exact_net SEGMENTS $segments]
        set histogram [dict create]
        set drivers 0
        foreach pin $pins {
            set direction [get_property DIRECTION $pin]
            set cell [get_cells -quiet -of_objects $pin]
            set ref [get_property REF_NAME $cell]
            set port [get_property REF_PIN_NAME $pin]
            puts $f [list PIN $direction [get_property NAME $pin] $ref $port]
            if {$direction eq "IN"} {
                dict incr histogram [list $ref $port]
            } elseif {$direction eq "OUT"} {
                incr drivers
                puts $f [list DRIVER $cell INIT [property INIT $cell] LOC [property LOC $cell]]
                foreach input [get_pins -quiet -of_objects $cell -filter {DIRECTION == IN}] {
                    puts $f [list DRIVER_INPUT [get_property NAME $input] \
                        [get_nets -quiet -of_objects $input]]
                }
            }
        }
        puts $f [list DRIVERS $drivers LOAD_TYPES $histogram]
        if {$drivers != 1} {error "Unexpected leaf driver count: $drivers"}
    } message options]
    close $f
    if {$code} {return -options $options $message}
}
