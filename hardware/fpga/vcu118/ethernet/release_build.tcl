# Current frozen RTL is authoritative; reference DCP supplies physical reuse only.
if {[catch {
    if {[llength $argv] != 6} {error "Expected mode package output token reference tools"}
    lassign $argv mode package out token reference tools
    set ::env(ARA_FPGA_PROFILE) dual_ddr_ethernet
    set ::rebuild_test_mode true
    source [file join $package ethernet rebuild_mainrtl.tcl]
    set ::rebuild_opt_preflight [file join $tools dual_cdc_preflight.tcl]
    rebuild_run $mode $package $out $token synth_$token $reference
} message]} {
    puts stderr $::errorInfo
    exit 1
}
exit 0
