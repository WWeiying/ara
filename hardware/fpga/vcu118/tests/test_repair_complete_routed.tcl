set ::complete_repair_test_mode true
source [file join [file dirname [info script]] .. ethernet repair_complete_routed.tcl]
set fifo i_dram_wrapper/gen_cdc.i_axi_cdc_mig/word_q_reg
set shared i_dram_wrapper/gen_ethernet.i_eth_shared_ddr/i_mux/data_q_reg
set fabric i_dram_wrapper/gen_ethernet.i_eth_loader/i_loader/loader_bd_i/ddr_fabric/reg
set mig i_dram_wrapper/gen_channel_c1.i_dram/inst/u_ddr4_mem_intfc/u_ddr_cal_top/u_ddr_cal/u_ddr_cal_addr_decode/reg
foreach {path expected} [list $fifo/CE c1_fifo $fifo/D c1_fifo $shared/CE ethernet_shared_ddr \
    $shared/D ethernet_shared_ddr $fabric/CE ethernet_fabric $fabric/D ethernet_fabric $mig/D mig_calibration] {
    if {[complete_repair::family $path] ne $expected} {error "Incorrect classification: $path"}
}
foreach bad [list $fifo/C $fifo/R other/reg/D gen_ddr2.i_dram_wrapper_c2/reg/D] {
    if {![catch {complete_repair::family $bad}]} {error "Unreviewed path accepted: $bad"}
}
complete_repair::same_endpoints {a b} {b a} reorder
foreach actual {{a} {a b c} {a a} {a c}} {
    if {![catch {complete_repair::same_endpoints {a b} $actual mismatch}]} {error "Inventory mismatch accepted"}
}
if {![catch {complete_repair::same_endpoints {} {} empty}]} {error "Empty review accepted"}
set ::paths [list $fifo/CE $fifo/D $shared/CE $shared/D $fabric/CE $fabric/D $mig/D]
proc get_clocks {args} {return mmcm_clkout0_1}
proc get_timing_paths {args} {
    if {$::wrong_clock && [lsearch -exact $args -from] >= 0} {return [lrange $::paths 1 end]}
    return $::paths
}
proc get_property {property objects} {
    switch -- $property {
        ENDPOINT_PIN {return $objects}
        STARTPOINT_PIN {return source/C}
        SLACK {return -0.056}
        default {error "Unexpected property $property"}
    }
}
set dir [file join [pwd] complete_repair_test_[pid]]
file mkdir $dir
set code [catch {
    set f [open [file join $dir endpoints.txt] w]
    puts $f [join $::paths \n]
    close $f
    set ::wrong_clock 0
    complete_repair::review [file join $dir endpoints.txt] $dir
    set ::wrong_clock 1
    if {![catch {complete_repair::review [file join $dir endpoints.txt] $dir}]} {error "Other-clock path accepted"}
    rename complete_repair::async_signature complete_repair::real_async_signature
    rename complete_repair::clock_signature complete_repair::real_clock_signature
    proc complete_repair::async_signature {} {return $::sync}
    proc complete_repair::clock_signature {} {return $::clock}
    proc phys_opt_design {args} {
        if {$args ne {-directive AggressiveExplore}} {error "Unexpected optimization command"}
        if {$::change eq "sync"} {set ::sync changed}
        if {$::change eq "clock"} {set ::clock changed}
    }
    set ::sync original; set ::clock original; set ::change none
    complete_repair::optimize
    foreach change {sync clock} {
        set ::sync original; set ::clock original; set ::change $change
        if {![catch {complete_repair::optimize}]} {error "Changed $change accepted"}
    }
    proc report_route_status {args} {return $::route([lindex $args end])}
    array set ::route {ROUTED_FULLY 1 ERRORS_IN_ROUTES 0}
    complete_repair::route_integrity
    set ::route(ERRORS_IN_ROUTES) 1
    if {![catch {complete_repair::route_integrity}]} {error "Illegal routes accepted"}
} message options]
file delete -force $dir
if {$code} {return -options $options $message}
puts "PASS: complete endpoint review, clock scope, optimizer invariants and route gates"
