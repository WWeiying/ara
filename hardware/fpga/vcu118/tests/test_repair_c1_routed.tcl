set ::c1_repair_test_mode true
source [file join [file dirname [info script]] .. ethernet repair_c1_routed.tcl]
set local i_dram_wrapper/gen_cdc.i_axi_cdc_mig/local_decode
foreach {name type async protected expected} [list \
    $local LUT6 0 0 1 $local MUXF7 {} {} 1 \
    $local FDCE 0 0 0 $local LUT6 1 0 0 $local LUT6 0 true 0 \
    other/LUT LUT6 0 0 0] {
    if {[c1_repair::safe_driver $name $type $async $protected] != $expected} {
        error "Unsafe/incorrect driver selection: $name $type $async $protected"
    }
}
puts "PASS: six driver safety cases; synchronizers, registers and protected/out-of-scope logic rejected"
# Execute the entire target classifier. Unknown properties must fail the test.
proc get_clocks {args} {return mmcm_clkout0_1}
proc get_timing_paths {args} {
    if {$::wrong_clock && [lsearch -exact $args -from] >= 0} {return {}}
    return [lrepeat 205 path]
}
proc get_property {property objects} {
    switch -- $property {
        ENDPOINT_PIN {
            set result {}
            foreach object $objects {lappend result {i_dram_wrapper/gen_cdc.i_axi_cdc_mig/word_q_reg[31]/CE}}
            if {[llength $objects] == 1} {return [lindex $result 0]}
            return $result
        }
        NAME {return $objects}
        REF_NAME {return $::driver_type}
        DONT_TOUCH - ASYNC_REG {return 0}
        STARTPOINT_PIN {return sync/C}
        SLACK {return -0.056}
        default {error "Unsupported real-tool property used: $property"}
    }
}
proc get_pins {args} {
    if {[lsearch -exact $args -of_objects] >= 0} {return driver_pin}
    if {[lindex $args end] ne {i_dram_wrapper/gen_cdc.i_axi_cdc_mig/word_q_reg\[31\]/CE}} {error "Unescaped indexed endpoint"}
    return endpoint_pin
}
proc get_nets {args} {return measured_net}
proc get_cells {args} {return i_dram_wrapper/gen_cdc.i_axi_cdc_mig/local_decode}
set temp [file join [pwd] c1_classifier_test_[pid]]
file mkdir $temp
set code [catch {
    set ::wrong_clock 0
    set ::driver_type LUT6
    if {[c1_repair::targets $temp] ne "measured_net"} {error "Incorrect targets"}
    set ::wrong_clock 1
    if {![catch {c1_repair::targets $temp}]} {error "Other-clock failures accepted"}
    set ::wrong_clock 0
    set ::driver_type FDCE
    if {![catch {c1_repair::targets $temp}]} {error "Synchronizer/register replication accepted"}
} message options]
file delete -force $temp
if {$code} {return -options $options $message}
puts "PASS: full 205-path classifier, cross-clock rejection, indexed-pin lookup, register rejection"
