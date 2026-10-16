set ::enable_library_only true
source [file join [file dirname [info script]] repair_dual_enable_fanout.tcl]
set prefix i_dram_wrapper/gen_ethernet.i_eth_shared_ddr/i_mux/enable
foreach {label name ref async protected loads failing expected} [list \
    valid $prefix LUT6 {} {} 577 432 1 \
    sync $prefix LUT6 true {} 577 432 0 \
    protected $prefix LUT6 {} 1 577 432 0 \
    register $prefix FDCE {} {} 577 432 0 \
    low_fanout $prefix LUT6 {} {} 63 40 0 \
    low_failures $prefix LUT6 {} {} 577 31 0 \
    mig i_dram_wrapper/gen_channel_c1.i_dram/enable LUT6 {} {} 577 432 0 \
    debug dbg_hub/enable LUT6 {} {} 577 432 0 \
    c2 gen_ddr2.i_dram_wrapper_c2/i_ddr_r_cut/enable LUT4 {} {} 100 40 1] {
    if {[enable_eligible $name $ref $async $protected $loads $failing] != $expected} {error "Failed $label"}
    puts "PASS $label"
}

# Exercise grouping with literal array indexes, duplicate timing paths, and
# non-CE endpoints. Any per-endpoint hierarchical query fails this test.
set ::out [file normalize [file join /tmp enable_index_test_[pid]]]
file mkdir $::out
set ::mock_pins {}
for {set i 0} {$i<40} {incr i} {lappend ::mock_pins "top/data_reg\[$i\]/CE"}
proc get_property {key objects} {
    switch $key {
        ENDPOINT_PIN {return $objects}
        NAME {return $objects}
        REF_NAME {return LUT6}
        ASYNC_REG {return {}}
        DONT_TOUCH {return [expr {$::scenario eq "protected_net" && $objects eq "net"}]}
        default {error "Unexpected property: $key"}
    }
}
proc get_pins {args} {
    if {[lsearch -exact $args -hier]>=0} {
        incr ::scans
        if {[lindex $args end] ne {IS_LEAF && REF_PIN_NAME == CE}} {error "Per-endpoint hierarchy scan"}
        if {$::scenario eq "missing"} {return [lrange $::mock_pins 1 end]}
        return $::mock_pins
    }
    if {[lindex $args end] eq {IS_LEAF && DIRECTION == OUT}} {return driver/O}
    return [lrepeat 100 load]
}
proc get_nets {args} {
    if {[lsearch -exact $args -hier]>=0} {error "Unnecessary net hierarchy scan"}
    return net
}
proc get_cells {args} {return i_dram_wrapper/gen_ethernet.i_eth_shared_ddr/i_mux/enable}
try {
    foreach scenario {healthy missing protected_net} {
        set scans 0
        set paths [concat $::mock_pins [list [lindex $::mock_pins 0] top/data_reg/D]]
        set failed [catch {enable_targets $paths} result]
        if {$scans!=1} {error "Expected exactly one design scan, got $scans"}
        if {$scenario eq "healthy"} {
            if {$failed || $result ne "net"} {error "Bad candidate selection: $result"}
            set f [open [file join $::out enable_candidates.tsv]]
            set report [read $f]; close $f
            if {![string match "*\t100\t40\t1*" $report]} {error "Duplicate endpoint counted twice"}
        } elseif {!$failed} {error "Expected refusal: $scenario"}
        puts "PASS bulk_index_$scenario scans=$scans"
    }
} finally {file delete -force $::out}
