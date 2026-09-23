# Read-only evidence for REQP-1869 and the board's fabric_ready CDC-11 fanout.
# No ties, reset logic, timing exceptions or DRC/CDC severities are changed.
namespace eval fpga_warning_details {}

proc fpga_warning_details::driver {pin} {
    set nets [get_nets -quiet -segments -of_objects $pin]
    if {![llength $nets]} { return [dict create kind UNCONNECTED drivers {} ports {}] }
    set drivers [get_pins -quiet -leaf -of_objects $nets -filter {DIRECTION == OUT}]
    set ports [get_ports -quiet -of_objects $nets -filter {DIRECTION != OUT}]
    set detail {}
    foreach source $drivers {
        set cell [get_cells -quiet -of_objects $source]
        if {[llength $cell] != 1} { error "Missing/ambiguous driver cell: $source" }
        lappend detail [list [get_property NAME $source] [get_property REF_NAME $cell]]
    }
    set kind LOGIC
    if {[llength $ports]} {
        set kind EXTERNAL
    } elseif {![llength $detail]} {
        set kind UNDRIVEN
    } elseif {[llength $detail] != 1} {
        set kind MULTIPLE
    } elseif {[lindex $detail 0 1] in {GND VCC}} {
        set kind [lindex $detail 0 1]
    }
    return [dict create kind $kind drivers $detail ports $ports]
}

proc fpga_warning_details::uram {out} {
    set cells [get_cells -quiet -hierarchical -filter {REF_NAME == URAM288}]
    puts $out "URAM288_COUNT=[llength $cells]"
    if {![llength $cells]} { error "No URAM288 cells found; cannot audit the reported cascade inputs" }
    set review 0
    foreach cell $cells {
        set name [get_property NAME $cell]
        foreach side {A B} {
            set order [get_property CASCADE_ORDER_$side $cell]
            puts $out [list URAM $name SIDE $side CASCADE_ORDER $order]
            if {$order ni {NONE FIRST MIDDLE LAST}} { error "Unknown cascade order on $name/$side: $order" }
            # MIDDLE/LAST consume the preceding RAM's outputs, not ground.
            if {$order ni {NONE FIRST}} { continue }
            foreach group {ADDR BWE DIN DOUT EN RDACCESS RDB_WR SBITERR DBITERR} \
                    width {23 9 72 72 1 1 1 1 1} {
                set prefix CAS_IN_${group}_$side
                set pins [get_pins -quiet -of_objects $cell -filter \
                    "DIRECTION == IN && REF_PIN_NAME =~ ${prefix}*"]
                puts $out "CASCADE_GROUP $name/$prefix PINS=[llength $pins] EXPECTED=$width"
                if {[llength $pins] != $width} { incr review }
                foreach pin $pins {
                    set connection [driver $pin]
                    puts $out [list CASCADE_PIN [get_property NAME $pin] {*}$connection]
                    if {[dict get $connection kind] ne "GND"} { incr review }
                }
            }
        }
    }
    # This includes pins beyond those named by REQP-1869; it is not a DRC count.
    puts $out "URAM_NON_GND_OR_MISSING_ITEMS=$review"
}

proc fpga_warning_details::cell {name} {
    set cells [get_cells -quiet -hierarchical -filter [format {NAME == "%s"} $name]]
    if {[llength $cells] != 1} { error "Missing/ambiguous CDC cell: $name" }
    return $cells
}

proc fpga_warning_details::fanout {out cell} {
    set q [get_pins -quiet -of_objects $cell -filter {REF_PIN_NAME == Q}]
    if {[llength $q] != 1} { error "Missing/ambiguous Q pin: $cell" }
    set ends [all_fanout -flat -endpoints_only -trace_arcs all -from $q]
    puts $out [list FANOUT [get_property NAME $q] COUNT [llength $ends]]
    set names {}
    foreach end $ends {
        set name [get_property NAME $end]
        puts $out [list ENDPOINT $name]
        lappend names $name
    }
    return [lsort -unique $names]
}

proc fpga_warning_details::ready {out} {
    fanout $out [cell i_dram_wrapper/fabric_ready_o_reg]
    set first [cell {gen_status_sync[2].i_sync/reg_q_reg[0]}]
    set last [cell {gen_status_sync[2].i_sync/reg_q_reg[1]}]
    set first_ends [fanout $out $first]
    set last_ends [fanout $out $last]
    set observation [expr {$first_ends eq [list {gen_status_sync[2].i_sync/reg_q_reg[1]/D}] &&
                          [llength $last_ends] > 0}]
    foreach end $last_ends {
        if {![string match i_vio/* $end]} { set observation 0 }
    }
    foreach reg [concat $first $last] {
        set c [get_pins -quiet -of_objects $reg -filter {REF_PIN_NAME == C}]
        if {[llength $c] != 1} { error "Missing/ambiguous clock pin: $reg" }
        puts $out [list STATUS_REG [get_property NAME $reg] \
            ASYNC_REG [get_property ASYNC_REG $reg] CLOCKS [get_clocks -quiet -of_objects $c]]
    }
    puts $out "VIO_TWO_STAGE_OBSERVATION_FANOUT_ONLY=$observation"
    puts $out "NOTE: fanout evidence only, not a CDC waiver or physical synchronizer signoff."
}

proc fpga_warning_details::write {dir} {
    file mkdir $dir
    set path [file join $dir warning_details.rpt]
    set out [open $path {WRONLY CREAT EXCL}]
    set code [catch {
        puts $out "Read-only URAM/ready-fanout evidence from the currently open netlist."
        puts $out "MANUAL_REVIEW_REQUIRED=1"
        uram $out
        ready $out
        puts $out "COLLECTION_COMPLETE=1"
    } result options]
    if {$code} { puts $out [list COLLECTION_ERROR $result] }
    set close_code [catch {close $out} close_result close_options]
    if {$code} { return -options $options $result }
    if {$close_code} { return -options $close_options $close_result }
    return $path
}
