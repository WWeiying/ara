# Loaded as unmanaged Tcl (FILE_TYPE TCL), after generated IP clocks.
# Keep these names tied to the retained cdc_fifo_gray hierarchy. A missing
# endpoint must fail, not silently leave the DDR crossing unconstrained.
namespace eval ara_cdc {}

proc ara_cdc::require {objects description {count -1}} {
    if {![llength $objects] || ($count >= 0 && [llength $objects] != $count)} {
        error "CDC: expected $description (count $count), got [llength $objects]"
    }
    return $objects
}

proc ara_cdc::clock_at {pin} {
    set pin [require [get_pins -quiet $pin] "clock pin $pin" 1]
    set clock [require [get_clocks -quiet -of_objects $pin] "clock on $pin" 1]
    if {[get_property PERIOD $clock] < 3.0} {
        error "CDC: $clock is faster than the 3 ns crossing bound"
    }
    return $clock
}

proc ara_cdc::pointer_inputs {root} {
    set regs [require [get_cells -quiet -hierarchical -filter \
        "NAME =~ $root/gen_sync* && REF_NAME =~ FD*"] "pointer synchronizers in $root" 12]
    set first {}
    foreach reg $regs {
        if {[regexp {\/reg_q_reg\[0\]$} [get_property NAME $reg]]} { lappend first $reg }
    }
    require $first "six first-stage Gray pointer registers in $root" 6
    set_property ASYNC_REG TRUE $regs
    return [require [get_pins -quiet -of_objects $first -filter {REF_PIN_NAME == D}] \
        "first-stage D pins in $root" 6]
}

proc ara_cdc::apply {} {
    set root i_dram_wrapper/gen_cdc.i_axi_cdc_mig
    foreach channel {aw w ar b r} {
        if {$channel in {aw w ar}} { set source src; set dest dst } \
        else { set source dst; set dest src }
        set src $root/i_axi_cdc_$source/i_cdc_fifo_gray_src_$channel
        set dst $root/i_axi_cdc_$dest/i_cdc_fifo_gray_dst_$channel
        set src_clock [clock_at $src/src_clk_i]
        set dst_clock [clock_at $dst/dst_clk_i]
        if {$src_clock eq $dst_clock} { error "CDC: $channel unexpectedly has only one clock" }
        set forward [pointer_inputs $dst]
        set reverse [pointer_inputs $src]
        set spill [require [get_cells -quiet -hierarchical -filter \
            "NAME =~ $dst/i_spill_register/* && REF_NAME =~ FD*"] "spill registers in $dst"]
        set data [require [get_pins -quiet -of_objects $spill -filter {REF_PIN_NAME == D}] \
            "spill register D pins in $dst"]
        # Only receiving D pins are exceptions. Stage 1 -> stage 2 remains
        # normally timed. The data mux must settle before the synchronized
        # write pointer permits capture in the destination spill register.
        set_max_delay -datapath_only 3.0 -from $src_clock -to $forward
        set_max_delay -datapath_only 3.0 -from $dst_clock -to $reverse
        set_max_delay -datapath_only 3.0 -from $src_clock -to $data
        puts "CDC: $channel $src_clock -> $dst_clock; data=[llength $data], pointers=6+6, max=3ns"
    }
    # POR assertion is asynchronous; each rstgen synchronizes deassertion.
    foreach pin {i_rstgen/rst_ni i_dram_wrapper/i_ui_rstgen/rst_ni} {
        set_false_path -through [require [get_pins -quiet $pin] "reset input $pin" 1]
    }
    set status_regs [get_cells -quiet -hierarchical -filter \
        {NAME =~ gen_status_sync*.i_sync/reg_q_reg* && REF_NAME =~ FD*}]
    if {![llength $status_regs] && [info exists ::ara_cdc_inspect_legacy] &&
        $::ara_cdc_inspect_legacy} {
        puts "WARNING: CDC: legacy netlist has no VIO status synchronizers; re-synthesis is required to verify the board fix."
    } else {
        require $status_regs "eight VIO status synchronizer registers" 8
        set status_first {}
        foreach reg $status_regs {
            if {[regexp {\/reg_q_reg\[0\]$} [get_property NAME $reg]]} {
                lappend status_first $reg
            }
        }
        require $status_first "four VIO first-stage registers" 4
        set_property ASYNC_REG TRUE $status_regs
        set_false_path -to [require [get_pins -quiet -of_objects $status_first \
            -filter {REF_PIN_NAME == D}] "four VIO first-stage D pins" 4]
        puts "CDC: four independent VIO status bits synchronized; only first-stage D pins excepted"
    }
}

ara_cdc::apply
