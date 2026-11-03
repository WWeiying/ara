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
