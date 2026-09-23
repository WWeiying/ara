# Extend the existing query-backed collection mocks without changing baseline tests.
source [file join [file dirname [info script]] test_cdc.tcl]
rename get_ports baseline_get_ports
proc get_ports {args} {
    if {[lindex $args end] eq "c1_ddr4_reset_n"} {
        if {$::ddr_case eq "missing_pad"} { return {} }
        return c1_ddr4_reset_n
    }
    return [baseline_get_ports {*}$args]
}
proc get_filesets {args} { return sources_1 }
rename get_property baseline_get_property
proc get_property {key object} {
    if {$key eq "verilog_define"} { return $::ddr_defines }
    return [baseline_get_property $key $object]
}
rename set_max_delay baseline_set_max_delay
proc set_max_delay {args} {
    set from [option $args -from]; set to [option $args -to]
    if {$to eq "c1_ddr4_reset_n"} {
        assert {$from eq "ui2" && [lrange $args 0 1] eq "-datapath_only 3.333"} "C2 reset uses its own UI clock"
        lappend ::max_delays $args
    } elseif {[string match gen_ddr2.i_dram_wrapper_c2/* [lindex $to 0]]} {
        assert {[lrange $args 0 1] eq "-datapath_only 3.0"} "C2 bound unchanged"
        assert {$from in {soc ui2} && [llength $to]} "C2 uses correct source clock"
        foreach pin $to {
            set cell [string range $pin 0 end-2]
            assert {[dict get $::cells $cell] ne $from} "C2 destination is opposite domain"
            assert {![regexp {reg_q_reg\[1\]} $cell]} "C2 second stage normally timed"
        }
        lappend ::max_delays $args
    } else { baseline_set_max_delay {*}$args }
}
rename set_false_path baseline_set_false_path
proc set_false_path {args} {
    if {[lindex $args 0] eq "-through" &&
        [string match gen_ddr2.i_dram_wrapper_c2/* [lindex $args 1]]} {
        assert {[lindex $args 1] in {gen_ddr2.i_dram_wrapper_c2/i_ui_rstgen/rst_ni gen_ddr2.i_dram_wrapper_c2/i_ui_por/rst_ni}} "only C2 reset assertions excepted"
        lappend ::false_paths $args
    } else { baseline_set_false_path {*}$args }
}
foreach ddr_case {dual single missing_channel unexpected_channel missing_pad missing_c1_coupled_reset missing_c2_coupled_reset missing_second_stage missing_ui_clock missing_por} {
    setup healthy
    set ddr_defines [expr {$ddr_case in {single unexpected_channel} ? {} : {ARA_FPGA_DDR2}}]
    if {$ddr_case ni {single missing_channel}} {
        dict set ::pins i_dram_wrapper/fabric_reset_ni reset
        dict for {name clock} $::pins {
            if {[string match i_dram_wrapper/* $name]} {
                set new [string map {i_dram_wrapper gen_ddr2.i_dram_wrapper_c2} $name]
                dict set ::pins $new [expr {$clock eq "ui" ? "ui2" : $clock}]
            }
        }
        dict for {name clock} $::cells {
            if {[string match i_dram_wrapper/* $name]} {
                set new [string map {i_dram_wrapper gen_ddr2.i_dram_wrapper_c2} $name]
                dict set ::cells $new [expr {$clock eq "ui" ? "ui2" : $clock}]
            }
        }
        dict set ::pins gen_ddr2.i_dram_wrapper_c2/soc_clk_i soc
        if {$ddr_case eq "missing_c1_coupled_reset"} {
            dict unset ::pins i_dram_wrapper/fabric_reset_ni
        }
        if {$ddr_case eq "missing_c2_coupled_reset"} {
            dict unset ::pins gen_ddr2.i_dram_wrapper_c2/fabric_reset_ni
        }
        set cdc gen_ddr2.i_dram_wrapper_c2/gen_cdc.i_axi_cdc_mig
        if {$ddr_case eq "missing_second_stage"} {
            dict unset ::cells $cdc/i_axi_cdc_dst/i_cdc_fifo_gray_dst_aw/gen_sync\[0\].i_sync/reg_q_reg\[1\]
        }
        if {$ddr_case eq "missing_ui_clock"} {
            dict unset ::pins $cdc/i_axi_cdc_dst/i_cdc_fifo_gray_dst_aw/dst_clk_i
        }
        if {$ddr_case eq "missing_por"} {
            dict unset ::pins gen_ddr2.i_dram_wrapper_c2/i_ui_por/rst_ni
        }
    }
    set failed [catch {source $root/constraints/cdc.xdc} message]
    assert {$failed == ($ddr_case ni {dual single})} "$ddr_case: $message"
    if {$failed} {
        assert {[string match CDC:* $message]} "intentional fail-closed error"
    } else {
        set dual [expr {$ddr_case eq "dual"}]
        assert {[llength $max_delays] == 21 + 16*$dual} "every DDR datapath/reset bound applied"
        assert {[llength $bus_skews] == 10 + 10*$dual} "every DDR Gray skew bound applied"
        assert {[llength $false_paths] == 5 + 2*$dual} "only documented reset/status exceptions"
    }
    puts "PASS DDR2 CDC $ddr_case"
}
