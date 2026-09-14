# Synthetic netlist query tests, not a substitute for Vivado timing/CDC.
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
    return {}
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
        PERIOD { return [expr {$object eq "soc" ? 20 : $::scenario eq "fast_clock" ? 2.5 : 3.333}] }
        default { error "Unexpected property $key" }
    }
}
proc set_property {key value objects} {
    assert {$key eq "ASYNC_REG" && $value eq "TRUE"} "only synchronizer attributes"
    foreach cell $objects { dict set ::attributes $cell $value }
}
proc set_max_delay {args} {
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
foreach scenario {healthy missing_first missing_second missing_data missing_clock multiple_clocks fast_clock same_clock missing_reset legacy missing_status missing_status_second} {
    setup $scenario
    set failed [catch {source $root/constraints/cdc.xdc} message]
    assert {$failed == ($scenario ni {healthy legacy})} "$scenario: $message"
    if {!$failed} {
        set legacy [expr {$scenario eq "legacy"}]
        assert {[llength $max_delays] == 15 && [llength $false_paths] == ($legacy ? 2 : 3)} "all channels/status bits covered"
        assert {[dict size $attributes] == ($legacy ? 120 : 128)} "pointer/status synchronizers marked"
    } else {
        assert {[string match CDC:* $message]} "expected an intentional validation failure: $message"
    }
    puts "PASS CDC $scenario"
}
