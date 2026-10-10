# Observe a real compute stage; drive only the external testbench reset pin.
proc ext_path {path} {
    if {![regexp {^ara_tb(\.[A-Za-z_][A-Za-z0-9_]*(\[[0-9]+\])*)+$} $path]} {
        error "Invalid HDL observation path"
    }
    return $path
}
proc ext_read {path} {
    set raw [string trim [get [ext_path $path] -radix decimal]]
    if {![regexp {^([0-9]+)$} $raw -> number] &&
        ![regexp {^[0-9]*'[dD]([0-9]+)$} $raw -> number]} {
        error "Unknown HDL observation: $path"
    }
    scan $number %d value
    return $value
}
proc ext_reset_execute {} {
    source external-reset-selection.tcl
    foreach name {ext_target ext_value ext_guard ext_dump_objects} {
        if {![info exists $name]} {error "Missing configuration: $name"}
    }
    ext_path $ext_target
    if {![regexp {^ara_tb\.dut\.i_ara_soc\.i_system\.i_ara\..*\.(div_cur_state|entry_state_q\[[0-9]+\])$} $ext_target] ||
        ![regexp {^[0-9]+$} $ext_value] || $ext_value > 15} {
        error "Invalid compute-stage selection"
    }
    if {$ext_guard ne ""} {
        ext_path $ext_guard
        if {![string match ara_tb.dut.i_ara_soc.i_system.i_ara.* $ext_guard]} {
            error "Guard outside Ara"
        }
    }
    set ara ara_tb.dut.i_ara_soc.i_system.i_ara
    foreach required [list ara_tb.clk ara_tb.rst_n ${ara}.axi_req_o ${ara}.axi_resp_i $ext_target] {
        if {[lsearch -exact $ext_dump_objects $required] < 0} {error "Missing focused object"}
    }
    if {$ext_guard ne "" && [lsearch -exact $ext_dump_objects $ext_guard] < 0} {
        error "Missing guard observation"
    }
    set seen {}
    foreach path $ext_dump_objects {
        ext_path $path
        if {[lsearch -exact $seen $path] >= 0} {error "Duplicate focused object"}
        lappend seen $path
    }
    set fid [dump -file external-reset.vpd -type VPD]
    foreach path $ext_dump_objects {
        show -type $path
        set added [dump -add $path -fid $fid -depth 0 -aggregates]
        if {![string is integer -strict $added] || $added <= 0} {error "Dump object unavailable"}
    }
    set condition "($ext_target == $ext_value) && (ara_tb.rst_n == 1)"
    if {$ext_guard ne ""} {append condition " && ($ext_guard == 1)"}
    set ::ext_hit 0
    stop -once -negedge ara_tb.clk -condition $condition -command {set ::ext_hit 1}
    puts "EXT_RESET_READY $ext_target $ext_value"
    run
    if {!$::ext_hit || [ext_read $ext_target] != $ext_value || [ext_read ara_tb.rst_n] != 1} {
        error "Compute stage not reached"
    }
    if {$ext_guard ne "" && [ext_read $ext_guard] != 1} {error "Guard not valid"}
    puts "EXT_RESET_TARGET $ext_target $ext_value"
    force ara_tb.rst_n 0 -deposit
    puts "EXT_RESET_ASSERT"
    for {set edge 0} {$edge < 4} {incr edge} {
        run -negedge ara_tb.clk
        if {[ext_read ara_tb.rst_n] != 0} {error "Reset hold violated"}
        puts "EXT_RESET_LOW_EDGE [expr {$edge + 1}]"
    }
    force ara_tb.rst_n 1 -deposit
    puts "EXT_RESET_RELEASE"
    puts "EXT_RESET_DONE"
    run
}
if {[catch {ext_reset_execute} failure]} {
    puts "EXT_RESET_ERROR $failure"
    exit 1
}
