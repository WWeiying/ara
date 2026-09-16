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

# A virtual zero-delay pad reference makes these paths visible to input/CDC
# reports. It is not an external synchronous clock: the first-stage-only
# datapath constraint below overrides phase/setup and excludes only its hold.
# The physical 20/70 ns budgets are unchanged.
proc ara_cdc::async_input {pad capture budget} {
    if {![llength [get_clocks -quiet ara_async_pad]]} {
        create_clock -name ara_async_pad -period 1000.0
    }
    set_input_delay -clock ara_async_pad -min 0.0 $pad
    set_input_delay -clock ara_async_pad -max 0.0 $pad
    set_max_delay -datapath_only $budget -from $pad -to $capture
}

proc ara_cdc::ddr_reset {} {
    set ui [clock_at i_dram_wrapper/gen_cdc.i_axi_cdc_mig/i_axi_cdc_dst/i_cdc_fifo_gray_src_r/src_clk_i]
    set port [require [get_ports -quiet c0_ddr4_reset_n] "DDR reset output" 1]
    # Routed evidence: UI-clocked cal_RESET_n_reg -> OBUF -> reset_n.
    # Bound the on-chip propagation to one UI cycle. This is NOT an invented
    # DDR CK setup/hold requirement; MIG owns the long reset/CKE sequencing.
    set_max_delay -datapath_only [get_property PERIOD $ui] -from $ui -to $port
    puts "CDC: DDR reset output bounded to one UI period; no internal reset recovery exceptions"
}

proc ara_cdc::debug_clock {} {
    if {[info exists ::ara_cdc_inspect_legacy] && $::ara_cdc_inspect_legacy} { return }
    set core [require [get_debug_cores -quiet dbg_hub] "debug hub core" 1]
    set vio [require [get_pins -quiet i_vio/clk] "VIO clock pin" 1]
    set clock [clock_at i_vio/clk]
    set period [get_property PERIOD $clock]
    if {abs($period - 20.0) > 0.001} { error "CDC: expected 50 MHz VIO clock, got $period ns" }
    set net [require [get_nets -quiet -of_objects $vio] "VIO clock net" 1]
    # UG908 debug constraints: select the free-running SoC clock before
    # implementation inserts the hub, rather than auto-selecting DDR 75 MHz.
    set connected [get_nets -quiet -of_objects [get_pins -quiet dbg_hub/clk]]
    if {[llength $connected]} { disconnect_debug_port dbg_hub/clk }
    set_property C_CLK_INPUT_FREQ_HZ 50000000 $core
    set_property C_ENABLE_CLK_DIVIDER false $core
    connect_debug_port dbg_hub/clk $net
    puts "CDC: debug hub and VIO share $clock (50 MHz)"
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

# Bound the actual asynchronous output ports, not arbitrary hierarchy pins.
# Clock endpoints avoid path segmentation; -through preserves checks all the
# way to receiving FFs, including the unbuffered reset-phase decode/CE paths.
proc ara_cdc::handshake {src dst stages width} {
    set src_clock [clock_at $src/clk_i]
    set dst_clock [clock_at $dst/clk_i]
    if {$src_clock eq $dst_clock} { error "CDC: same clock on DMI handshake $src -> $dst" }
    set bound [expr {min([get_property PERIOD $src_clock], [get_property PERIOD $dst_clock])}]
    set req [require [get_pins -quiet $src/async_req_o] "$src request output" 1]
    set ack [require [get_pins -quiet $dst/async_ack_o] "$dst acknowledge output" 1]
    set data [require [get_pins -quiet $src/async_data_o*] "$src data output bits" $width]
    foreach half [list $src $dst] {
        set regs [require [get_cells -quiet -hierarchical -filter \
            "NAME =~ $half/i_sync/reg_q_reg* && REF_NAME =~ FD*"] \
            "DMI synchronizer in $half" $stages]
        # Check each stage as well as the total count; do not mark data/state FFs.
        for {set stage 0} {$stage < $stages} {incr stage} {
            set expected [format {%s/i_sync/reg_q_reg[%d]} $half $stage]
            set found {}
            foreach reg $regs {
                if {[get_property NAME $reg] eq $expected} { lappend found $reg }
            }
            require $found "DMI stage $expected" 1
        }
        set_property ASYNC_REG TRUE $regs
    }
    set_max_delay -datapath_only $bound -from $src_clock -through $req -to $dst_clock
    set_max_delay -datapath_only $bound -from $dst_clock -through $ack -to $src_clock
    set_max_delay -datapath_only $bound -from $src_clock -through $data -to $dst_clock
    puts "CDC: DMI $src -> $dst; data=$width, stages=$stages, max=${bound}ns"
}

proc ara_cdc::dmi_legacy {} {
    set root i_cheshire_soc/i_dbg_dmi_jtag/i_dmi_cdc
    # dm_pkg::dmi_req_t and dmi_resp_t; a changed ABI/hierarchy must be reviewed.
    foreach channel {req resp} width {41 34} {
        set cdc $root/i_cdc_$channel
        handshake $cdc/i_src $cdc/i_dst 3 $width
        set reset $cdc/i_cdc_reset_ctrlr
        foreach side {a b} other {b a} {
            handshake $reset/i_cdc_reset_ctrlr_half_$side/i_state_transition_cdc_src \
                $reset/i_cdc_reset_ctrlr_half_$other/i_state_transition_cdc_dst 2 2
        }
    }
}

proc ara_cdc::jtag {} {
    set root i_cheshire_soc/i_dbg_dmi_jtag
    set regs [get_cells -quiet -hierarchical -filter \
        "NAME =~ $root/fpga_tck_sync_q_reg* && REF_NAME =~ FD*"]
    if {![llength $regs] && [info exists ::ara_cdc_inspect_legacy] &&
        $::ara_cdc_inspect_legacy} {
        puts "WARNING: CDC: inspecting legacy TCK-clocked TAP; sampled-JTAG fix requires synthesis."
        create_clock -period 100.0 -name clk_jtag [get_ports jtag_tck_i]
        set_input_delay -min -clock clk_jtag 10.0 [get_ports {jtag_tdi_i jtag_tms_i}]
        set_input_delay -max -clock clk_jtag 20.0 [get_ports {jtag_tdi_i jtag_tms_i}]
        set_output_delay -min -clock clk_jtag 10.0 [get_ports jtag_tdo_o]
        set_output_delay -max -clock clk_jtag 20.0 [get_ports jtag_tdo_o]
        dmi_legacy
        return
    }
    require $regs "three sampled-TCK registers; re-synthesize the FPGA snapshot" 3
    set clock [clock_at $root/clk_i]
    if {[get_property PERIOD $clock] > 20.0} {
        error "CDC: sampled JTAG requires a SoC clock of at least 50 MHz"
    }
    foreach signal {tck tms tdi} {
        set regs [require [get_cells -quiet -hierarchical -filter \
            "NAME =~ $root/fpga_${signal}_sync_q_reg* && REF_NAME =~ FD*"] \
            "three sampled-$signal registers" 3]
        set first {}
        for {set stage 0} {$stage < 3} {incr stage} {
            set expected [format {%s/fpga_%s_sync_q_reg[%d]} $root $signal $stage]
            set found {}
            foreach reg $regs {
                if {[get_property NAME $reg] eq $expected} { lappend found $reg }
            }
            require $found "JTAG stage $expected" 1
            if {$stage == 0} { set first $found }
        }
        set_property ASYNC_REG TRUE $regs
        set pad [require [get_ports -quiet jtag_${signal}_i] "JTAG $signal pad" 1]
        set pin [require [get_pins -quiet -of_objects $first -filter {REF_PIN_NAME == D}] \
            "JTAG $signal first-stage D" 1]
        async_input $pad $pin 20.0
    }
    set_max_delay -datapath_only 20.0 -from $clock \
        -to [require [get_ports -quiet jtag_tdo_o] "JTAG TDO pad" 1]
    puts "CDC: sampled JTAG on $clock; TCK <=1 MHz, phases >=400ns, IO budgets=20ns"
}

proc ara_cdc::uart {} {
    set root i_cheshire_soc/gen_uart.i_uart/i_apb_uart/UART_IS_SIN
    set regs [require [get_cells -quiet -hierarchical -filter \
        "NAME =~ $root/iD_reg* && REF_NAME =~ FD*"] "UART RX synchronizer" 2]
    set first {}
    foreach reg $regs {
        if {[get_property NAME $reg] eq "$root/iD_reg\[0\]"} { lappend first $reg }
    }
    require $first "UART RX first stage" 1
    set_property ASYNC_REG TRUE $regs
    set input [require [get_ports -quiet uart_rx_i] "UART RX port" 1]
    set capture [require [get_pins -quiet -of_objects $first -filter {REF_PIN_NAME == D}] \
        "UART RX first-stage D pin" 1]
    async_input $input $capture 70.0
    puts "CDC: UART RX pad -> first-stage D, max=70ns; second stage normally timed"
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
        set_bus_skew 3.0 -from $src_clock -to $forward
        set_bus_skew 3.0 -from $dst_clock -to $reverse
        puts "CDC: $channel $src_clock -> $dst_clock; data=[llength $data], pointers=6+6, max=3ns"
    }
    # POR assertion is asynchronous; each rstgen synchronizes deassertion.
    foreach pin {i_rstgen/rst_ni i_dram_wrapper/i_ui_rstgen/rst_ni} {
        set_false_path -through [require [get_pins -quiet $pin] "reset input $pin" 1]
    }
    foreach pin {i_board_por/rst_ni i_dram_wrapper/i_ui_por/rst_ni} {
        set pins [get_pins -quiet $pin]
        if {![llength $pins] && [info exists ::ara_cdc_inspect_legacy] &&
            $::ara_cdc_inspect_legacy} {
            puts "WARNING: CDC: legacy reset netlist lacks $pin; re-synthesis required."
        } else {
            set_false_path -through [require $pins "registered reset POR input $pin" 1]
        }
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
    jtag
    uart
    ddr_reset
    debug_clock
}

ara_cdc::apply
