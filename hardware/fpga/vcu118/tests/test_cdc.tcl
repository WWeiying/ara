# Synthetic netlist query tests, not a substitute for Vivado timing/CDC.
if {[llength [info commands try]]} { rename try {} }
set root [file normalize [lindex $argv 0]]
proc assert {condition message} {
    if {![uplevel 1 [list expr $condition]]} { error "ASSERT: $message" }
}
proc option {args key} { return [lindex $args [expr {[lsearch -exact $args $key]+1}]] }
proc setup {scenario} {
    set ::scenario $scenario
    set ::cells {}; set ::pins {}; set ::max_delays {}; set ::false_paths {}; set ::attributes {}
    set base i_dram_wrapper/gen_cdc.i_axi_cdc_mig
    foreach channel {aw w ar b r} {
        foreach side {src dst} {
            set half [expr {($channel in {aw w ar}) == ($side eq "src") ? "src" : "dst"}]
            set fifo $base/i_axi_cdc_$half/i_cdc_fifo_gray_${side}_$channel
            set clock [expr {$half eq "src" ? "soc" : "ui"}]
            dict set ::pins $fifo/${side}_clk_i $clock
            for {set bit 0} {$bit < 6} {incr bit} {
                for {set stage 0} {$stage < 2} {incr stage} {
                    set cell [format {%s/gen_sync[%d].i_sync/reg_q_reg[%d]} $fifo $bit $stage]
                    if {$channel eq "aw" && $side eq "dst" && $bit == 0 &&
                        (($scenario eq "missing_first" && $stage == 0) ||
                         ($scenario eq "missing_second" && $stage == 1))} { continue }
                    dict set ::cells $cell $clock
                }
            }
            if {$side eq "dst" && !($scenario eq "missing_data" && $channel eq "r")} {
                foreach name {{a_data_q_reg[0]} {b_data_q_reg[0]} a_full_q_reg} {
                    dict set ::cells $fifo/i_spill_register/spill_register_flushable_i/gen_spill_reg.$name $clock
                }
            }
        }
    }
    dict set ::pins i_rstgen/rst_ni reset
    if {$scenario ne "missing_reset"} { dict set ::pins i_dram_wrapper/i_ui_rstgen/rst_ni reset }
    unset -nocomplain ::ara_cdc_inspect_legacy
    if {$scenario eq "legacy"} { set ::ara_cdc_inspect_legacy true }
    if {$scenario ni {legacy missing_status}} {
        for {set bit 0} {$bit < 4} {incr bit} {
            for {set stage 0} {$stage < 2} {incr stage} {
                if {$scenario eq "missing_status_second" && $stage == 1 && $bit == 0} { continue }
                dict set ::cells [format {gen_status_sync[%d].i_sync/reg_q_reg[%d]} $bit $stage] soc
            }
        }
    }
    set ::through_clocks {}
    set dmi i_cheshire_soc/i_dbg_dmi_jtag/i_dmi_cdc
    foreach channel {req resp} width {41 34} {
        set cdc $dmi/i_cdc_$channel
        set source [expr {$channel eq "req" ? "jtag" : "soc"}]
        set dest [expr {$source eq "soc" ? "jtag" : "soc"}]
        mock_handshake $cdc/i_src $cdc/i_dst $source $dest 3 $width
        set reset $cdc/i_cdc_reset_ctrlr
        mock_handshake $reset/i_cdc_reset_ctrlr_half_a/i_state_transition_cdc_src \
            $reset/i_cdc_reset_ctrlr_half_b/i_state_transition_cdc_dst $source $dest 2 2
        mock_handshake $reset/i_cdc_reset_ctrlr_half_b/i_state_transition_cdc_src \
            $reset/i_cdc_reset_ctrlr_half_a/i_state_transition_cdc_dst $dest $source 2 2
    }
    set uart i_cheshire_soc/gen_uart.i_uart/i_apb_uart/UART_IS_SIN
    dict set ::cells $uart/iD_reg\[0\] soc
    dict set ::cells $uart/iD_reg\[1\] soc
    switch $scenario {
        missing_dmi_req { dict unset ::pins $dmi/i_cdc_req/i_src/async_req_o }
        missing_dmi_ack { dict unset ::pins $dmi/i_cdc_resp/i_dst/async_ack_o }
        missing_dmi_bit { dict unset ::pins $dmi/i_cdc_req/i_src/async_data_o\[40\] }
        missing_dmi_stage { dict unset ::cells $dmi/i_cdc_req/i_src/i_sync/reg_q_reg\[2\] }
        wrong_dmi_stage {
            dict unset ::cells $dmi/i_cdc_req/i_src/i_sync/reg_q_reg\[2\]
            dict set ::cells $dmi/i_cdc_req/i_src/i_sync/reg_q_reg\[3\] jtag
        }
        missing_reset_phase { dict unset ::pins $reset/i_cdc_reset_ctrlr_half_b/i_state_transition_cdc_src/async_data_o\[1\] }
        missing_uart_stage { dict unset ::cells $uart/iD_reg\[0\] }
    }
}
proc mock_handshake {src dst source dest stages width} {
    foreach half [list $src $dst] clock [list $source $dest] {
        dict set ::pins $half/clk_i $clock
        for {set stage 0} {$stage < $stages} {incr stage} {
            dict set ::cells [format {%s/i_sync/reg_q_reg[%d]} $half $stage] $clock
        }
    }
    dict set ::pins $src/async_req_o $source
    dict set ::pins $dst/async_ack_o $dest
    dict set ::through_clocks $src/async_req_o [list $source $dest]
    dict set ::through_clocks $dst/async_ack_o [list $dest $source]
    for {set bit 0} {$bit < $width} {incr bit} {
        set name [format {%s/async_data_o[%d]} $src $bit]
        dict set ::pins $name $source
        dict set ::through_clocks $name [list $source $dest]
    }
}
proc get_cells {args} {
    set filter [option $args -filter]
    assert {[regexp {^NAME =~ (\S+) && REF_NAME =~ FD\*$} $filter -> pattern]} "bounded FF query"
    set result {}
    dict for {cell clock} $::cells { if {[string match $pattern $cell]} { lappend result $cell } }
    return $result
}
proc get_pins {args} {
    if {[lsearch -exact $args -of_objects] >= 0} {
        assert {[option $args -filter] eq "REF_PIN_NAME == D"} "only D pins, not clock/reset/CE"
        set result {}
        foreach cell [option $args -of_objects] {
            assert {[dict exists $::cells $cell]} "unknown register"
            lappend result $cell/D
        }
        return $result
    }
    set name [lindex $args end]
    if {[dict exists $::pins $name]} { return $name }
    if {[string match */async_data_o* $name]} {
        set result {}
        dict for {pin clock} $::pins {
            if {[string match $name $pin]} { lappend result $pin }
        }
        return $result
    }
    return {}
}
proc get_ports {args} {
    assert {[lindex $args end] eq "uart_rx_i"} "UART input only"
    return [expr {$::scenario eq "missing_uart_port" ? "" : "uart_rx_i"}]
}
proc get_clocks {args} {
    set pin [option $args -of_objects]
    if {$::scenario eq "missing_clock"} { return {} }
    if {$::scenario eq "multiple_clocks"} { return {soc ui} }
    if {$::scenario eq "same_clock"} { return soc }
    return [dict get $::pins $pin]
}
proc get_property {key object} {
    switch $key {
        NAME { return $object }
        PERIOD {
            if {$object eq "jtag"} { return [expr {$::scenario eq "fast_jtag" ? 10.0 : 100.0}] }
            return [expr {$object eq "soc" ? 20.0 : $::scenario eq "fast_clock" ? 2.5 : 3.333}]
        }
        default { error "Unexpected property $key" }
    }
}
proc set_property {key value objects} {
    assert {$key eq "ASYNC_REG" && $value eq "TRUE"} "only synchronizer attributes"
    foreach cell $objects { dict set ::attributes $cell $value }
}
proc set_max_delay {args} {
    set from [option $args -from]; set to [option $args -to]
    if {[lsearch -exact $args -through] >= 0} {
        set pins [option $args -through]
        set delay [expr {$::scenario eq "fast_jtag" ? 10.0 : 20.0}]
        assert {[lrange $args 0 1] eq "-datapath_only $delay"} "minimum actual period, not a hardcoded JTAG period"
        assert {$from in {soc jtag} && $to in {soc jtag} && $from ne $to} "opposite clock endpoints"
        assert {[llength $pins] >= 1 && [llength $pins] <= 41} "bounded DMI ports"
        foreach pin $pins {
            assert {[dict get $::through_clocks $pin] eq [list $from $to]} "physical source/destination direction"
        }
        lappend ::max_delays $args
        return
    }
    if {$from eq "uart_rx_i"} {
        assert {[lrange $args 0 1] eq "-datapath_only 70.0"} "UART physical bound"
        assert {[llength $to] == 1 && [lindex $to 0] eq {i_cheshire_soc/gen_uart.i_uart/i_apb_uart/UART_IS_SIN/iD_reg[0]/D}} "UART first stage only"
        lappend ::max_delays $args
        return
    }
    assert {[lrange $args 0 1] eq "-datapath_only 3.0"} "3 ns datapath-only bound"
    assert {[lsearch -exact $args -through] < 0} "no huge through collection"
    set from [option $args -from]; set to [option $args -to]
    assert {$from in {soc ui} && [llength $to]} "explicit source clock and destinations"
    foreach pin $to {
        set cell [string range $pin 0 end-2]
        assert {[dict get $::cells $cell] ne $from} "never except same-domain paths"
        assert {![regexp {reg_q_reg\[1\]} $cell]} "second synchronizer stage remains timed"
    }
    lappend ::max_delays $args
}
proc set_false_path {args} {
    assert {[llength $args] == 2} "one bounded pin set only"
    if {[lindex $args 0] eq "-through"} {
        assert {[lindex $args 1] in {i_rstgen/rst_ni i_dram_wrapper/i_ui_rstgen/rst_ni}} "reset pins only"
    } else {
        assert {[lindex $args 0] eq "-to" && [llength [lindex $args 1]] == 4} "four status inputs only"
        foreach pin [lindex $args 1] {
            assert {[regexp {^gen_status_sync\[[0-3]\]\.i_sync/reg_q_reg\[0\]/D$} $pin]} "only first-stage status D pins"
        }
    }
    lappend ::false_paths $args
}
foreach scenario {healthy missing_first missing_second missing_data missing_clock multiple_clocks fast_clock same_clock missing_reset legacy missing_status missing_status_second missing_dmi_req missing_dmi_ack missing_dmi_bit missing_dmi_stage wrong_dmi_stage missing_reset_phase fast_jtag missing_uart_stage missing_uart_port} {
    setup $scenario
    set failed [catch {source $root/constraints/cdc.xdc} message]
    assert {$failed == ($scenario ni {healthy legacy fast_jtag})} "$scenario: $message"
    if {!$failed} {
        set legacy [expr {$scenario eq "legacy"}]
        assert {[llength $max_delays] == 34 && [llength $false_paths] == ($legacy ? 2 : 3)} "all FIFO/DMI/UART channels covered"
        assert {[dict size $attributes] == ($legacy ? 150 : 158)} "only pointer/status/handshake/UART synchronizers marked"
    } else {
        assert {[string match CDC:* $message]} "expected an intentional validation failure: $message"
    }
    puts "PASS CDC $scenario"
}
