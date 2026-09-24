# Read the archived implementation only. No board connection or design edits.
namespace eval axi_inspect {}

proc axi_inspect::drivers {pin stream} {
    set nets [get_nets -segments -of_objects $pin]
    if {![llength $nets]} {
        puts $stream "PIN $pin NO_NET"
        return ?
    }
    set pins [get_pins -leaf -of_objects $nets -filter {DIRECTION == OUT}]
    set constants {}
    foreach driver $pins {
        set cells [get_cells -of_objects $driver]
        set ref [get_property REF_NAME $cells]
        puts $stream "PIN $pin DRIVER=$driver REF=$ref"
        switch -- $ref {
            GND { lappend constants 0 }
            VCC { lappend constants 1 }
            default { lappend constants ? }
        }
    }
    if {[llength $constants] != 1} { return ? }
    return [lindex $constants 0]
}

proc axi_inspect::inspect {checkpoint output} {
    open_checkpoint $checkpoint
    set stream [open [file join $output axi_netlist.rpt] w]
    fconfigure $stream -encoding utf-8
    set code [catch {
        puts $stream "CHECKPOINT $checkpoint"
        puts $stream "VIVADO [version -short]"
        puts $stream "STATIC_ONLY: ? means dynamic, optimized, or unresolved; not a sampled bus value."
        set matches [get_cells -hier -filter {NAME =~ */i_jtag_mem}]
        if {[llength $matches] != 1} { error "Expected one i_jtag_mem; found $matches" }
        set cell [lindex $matches 0]
        puts $stream "JTAG_CELL=$cell"
        if {[get_property IS_BLACKBOX $cell]} { error "JTAG IP is a black box in this checkpoint" }
        array set counts {}
        array set size_bits {}
        foreach pin [lsort -dictionary [get_pins -of_objects $cell]] {
            set name [string range [get_property NAME $pin] [expr {[string length $cell] + 1}] end]
            if {![regexp {^m_axi_([a-z]+)(\[([0-9]+)\])?$} $name unused field bus bit]} { continue }
            if {![info exists counts($field)]} { set counts($field) 0 }
            incr counts($field)
            if {$field in {arsize awsize arlen awlen arburst awburst}} {
                set value [axi_inspect::drivers $pin $stream]
                if {$field in {arsize awsize} && $bit ne ""} { set size_bits($field,$bit) $value }
            }
        }
        foreach field {araddr arlen arsize arburst rdata rvalid rready rlast awaddr awlen awsize awburst wdata wstrb} {
            if {![info exists counts($field)]} { set counts($field) 0 }
            puts $stream "WIDTH $field=$counts($field)"
        }
        foreach field {arsize awsize} {
            set bits ""
            foreach bit {2 1 0} {
                if {[info exists size_bits($field,$bit)]} {
                    append bits $size_bits($field,$bit)
                } else { append bits ? }
            }
            puts $stream "SIZE $field bits=$bits EXPECTED_64BIT_FULL_WIDTH=011"
        }
        # Preserve small, relevant logic blocks for subsequent netlist comparison.
        # Missing optimized hierarchy is reported, never silently replaced by current RTL.
        foreach leaf {i_read_unit i_write_unit i_ar_splitter i_aw_splitter} {
            set matches [get_cells -hier -filter "NAME =~ *gen_llc.i_llc*/$leaf"]
            puts $stream "LLC_BLOCK $leaf CELLS=$matches"
            if {[llength $matches] == 1} {
                set netlist [file join $output ${leaf}.v]
                if {[catch {
                    write_verilog -cell [lindex $matches 0] -mode funcsim -include_xilinx_libs $netlist
                } export_error]} {
                    puts $stream "NETLIST_EXPORT_ERROR $leaf: $export_error"
                } else { puts $stream "NETLIST $netlist" }
            }
        }
        puts $stream "INSPECTION_COMPLETE"
    } message options]
    close $stream
    close_design
    if {$code} { return -options $options $message }
}

if {![info exists ::axi_inspect_library_only]} {
    if {[catch {
        if {[llength $argv] != 2} { error "Expected checkpoint and output directory" }
        axi_inspect::inspect {*}$argv
    } message options]} {
        puts stderr [dict get $options -errorinfo]
        exit 1
    }
    exit 0
}
