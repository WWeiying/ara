# Current frozen RTL is authoritative; reference DCP supplies physical reuse only.
if {[catch {
    if {[llength $argv] != 6} {error "Expected mode package output token reference tools"}
    lassign $argv mode package out token reference tools
    set ::env(ARA_FPGA_PROFILE) dual_ddr_ethernet
    set ::rebuild_test_mode true
    set library [file join [file dirname [info script]] rebuild_mainrtl.tcl]
    if {![file isfile $library]} {set library [file join $package ethernet rebuild_mainrtl.tcl]}
    source $library
    set ::rebuild_opt_preflight [file join $tools dual_cdc_preflight.tcl]
    if {$mode in {impl impl_existing} &&
        (![file isfile $::rebuild_opt_preflight] || [file size $::rebuild_opt_preflight] == 0)} {
        error "Missing implementation preflight before opening/creating runs: $::rebuild_opt_preflight"
    }
    if {$mode eq "prepared"} {
        source [file join $package scripts common.tcl]
        source [file join $package scripts run_support.tcl]
        open_package_project
        fpga_run::check_ips
        close_project
        puts "PREPARED_PROJECT_VERIFIED"
    } else {
        rebuild_run $mode $package $out $token synth_$token $reference
    }
} message]} {
    puts stderr $::errorInfo
    exit 1
}
exit 0
