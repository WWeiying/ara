# Reuse proven UCLI timing, dump and external-pin deposition; exact VMFPU profile.
set f [open {/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/external_reset_driver.tcl} r]
set body [read $f]; close $f
set tail {if {[catch {ext_reset_execute} failure]} {
    puts "EXT_RESET_ERROR $failure"
    exit 1
}}
set pos [string first $tail $body]
if {$pos < 0} {error "Frozen reset driver entry changed"}
set body [string range $body 0 [expr {$pos-1}]]
set old {.*\.(div_cur_state|entry_state_q\[[0-9]+\])$}
set new {gen_lanes\[0\]\.i_lane\.i_vfus\.i_vmfpu\.mfpu_state_q$}
if {[string first $old $body] < 0} {error "Frozen selector guard changed"}
set body [string map [list $old $new {$ext_value > 15} {$ext_value != 1}] $body]
set old {set condition "($ext_target == $ext_value) && (ara_tb.rst_n == 1)"}
if {[string first $old $body] < 0} {error "Frozen stop condition changed"}
set body [string map [list $old {set condition [ured_condition $ext_states]}] $body]
set old {puts "EXT_RESET_TARGET $ext_target $ext_value"}
if {[string first $old $body] < 0} {error "Frozen target confirmation changed"}
set body [string map [list $old {foreach state $ext_states {
        if {[ext_read $state] != 1} {error "Not all four lanes in INTRA"}
    }
    puts "EXT_RESET_TARGET $ext_target $ext_value"}] $body]
proc ured_condition {states} {
    set base ara_tb.dut.i_ara_soc.i_system.i_ara
    set expected {}
    for {set lane 0} {$lane < 4} {incr lane} {
        lappend expected ${base}.gen_lanes\[$lane\].i_lane.i_vfus.i_vmfpu.mfpu_state_q
    }
    if {$states ne $expected} {error "Exact four frozen VMFPU states required"}
    set condition {(ara_tb.rst_n == 1)}
    foreach state $states {append condition " && ($state == 1)"}
    return $condition
}
uplevel #0 $body
if {![info exists ::ured_test_only]} {
    if {[catch {ext_reset_execute} failure]} {
        puts "EXT_RESET_ERROR $failure"
        exit 1
    }
}
