# Tcl command mocks test orchestration and rejection, not vendor IP synthesis.
if {[llength [info commands try]]} { rename try {} }
set scripts [file normalize [file join [file dirname [info script]] .. scripts]]
set scratch [file normalize [lindex $argv 0]]
if {[llength $argv] != 1 || [file exists $scratch]} { error "Pass one new scratch directory" }
file mkdir $scratch
set checks 0
proc assert {condition message} {
    if {![uplevel 1 [list expr $condition]]} { error "ASSERT: $message" }
    incr ::checks
}
proc put {path data} {
    file mkdir [file dirname $path]
    set f [open $path w]; puts $f $data; close $f
}
proc option {args key} { return [lindex $args [expr {[lsearch -exact $args $key]+1}]] }
proc get_ips {args} { return [lindex $args end] }
proc create_ip {args} {
    set name [option $args -module_name]
    assert {$name ni $::created} "IP must only be created once"
    lappend ::created $name
    dict set ::ip_kinds $name [option $args -name]
    dict set ::ip_versions $name [option $args -version]
}
proc set_property {args} {
    assert {[lindex $args 0] eq "-dict"} "IP configuration must be explicit"
    dict set ::properties [lindex $args end] [lindex $args 1]
}
proc generate_target {target ips} { set ::generated $ips }
proc create_ip_run {ip} { lappend ::ooc $ip }

foreach profile {baseline host dual_ddr} {
    set ::env(ARA_FPGA_PROFILE) $profile
    source $scripts/common.tcl
    set expected ara_dsa_vcu118
    if {$profile ne "baseline"} { append expected _$profile }
    assert {$project_name eq $expected} "isolated project name"
    assert {[file tail $build_dir] eq $expected} "isolated project directory"
    assert {[file tail $xpr_path] eq "$expected.xpr"} "isolated project path"
    assert {$design_top eq "ara_dsa_vcu118"} "DCP name follows unchanged RTL top"
    set expected_defines {}
    if {$profile ne "baseline"} { lappend expected_defines ARA_FPGA_HOST }
    if {$profile eq "dual_ddr"} { lappend expected_defines ARA_FPGA_DDR2 }
    assert {$profile_defines eq $expected_defines} "exact profile defines"
    set created {}; set properties {}; set ip_kinds {}; set ip_versions {}; set ooc {}
    source $scripts/create_ip.tcl
    assert {[lsort $created] eq [lsort $profile_ips]} "only selected IPs instantiated"
    assert {$generated eq $profile_ips && $ooc eq $profile_ips} "generate/OOC every required IP"
    assert {[dict get $properties ddr4 CONFIG.C0_DDR4_BOARD_INTERFACE] eq "ddr4_sdram_c1_062"} "C1 unchanged"
    set narrow [dict get $properties ddr4 CONFIG.C0.DDR4_AxiNarrowBurst]
    assert {$narrow eq [expr {$profile eq "baseline" ? "false" : "true"}]} "DDR narrow burst profile"
    if {$profile ne "baseline"} {
        foreach name {jtag_mem jtag_debug} {
            assert {[dict get $ip_kinds $name] eq "jtag_axi"} "real JTAG AXI IP"
            assert {[dict get $ip_versions $name] eq "1.2"} "explicit vendor IP version"
        }
        foreach {key value} {
            CONFIG.PROTOCOL 0 CONFIG.M_AXI_DATA_WIDTH 64 CONFIG.M_AXI_ADDR_WIDTH 64
            CONFIG.M_AXI_ID_WIDTH 2 CONFIG.WR_TXN_QUEUE_LENGTH 16 CONFIG.RD_TXN_QUEUE_LENGTH 16
        } { assert {[dict get $properties jtag_mem $key] == $value} "memory bridge $key" }
        foreach {key value} {CONFIG.PROTOCOL 2 CONFIG.M_AXI_DATA_WIDTH 32 CONFIG.M_AXI_ADDR_WIDTH 32} {
            assert {[dict get $properties jtag_debug $key] == $value} "debug bridge $key"
        }
    }
    if {$profile eq "dual_ddr"} {
        set c1 [dict get $properties ddr4]; set c2 [dict get $properties ddr4_c2]
        assert {[dict get $c2 CONFIG.C0_DDR4_BOARD_INTERFACE] eq "ddr4_sdram_c2_062"} "C2 interface"
        dict unset c1 CONFIG.C0_DDR4_BOARD_INTERFACE
        dict unset c2 CONFIG.C0_DDR4_BOARD_INTERFACE
        assert {$c1 eq $c2} "C2 identical geometry/timing to C1"
    }
    set n [expr {$profile eq "dual_ddr" ? 2 : 1}]
    assert {[llength [fpga_checks::gray_groups]] == 10*$n} "every channel has ten Gray groups"
    assert {[llength [fpga_checks::cdc_failures {}]] == 65*$n+1} "empty CDC fails closed"
    assert {[llength [fpga_checks::skew_failures {} true]] == 10*$n} "empty skew fails closed"
}
set ::env(ARA_FPGA_PROFILE) invalid
assert {[catch {source $scripts/config.tcl} message]} "invalid profile rejected"
unset ::env(ARA_FPGA_PROFILE)
source $scripts/common.tcl
assert {$fpga_profile eq "baseline"} "environment absent defaults to baseline"

# Complete dual-channel fixture, then remove/corrupt only C2 evidence.
set fpga_profile dual_ddr
set cdc {}; set skew {}; set seq 0
foreach group [fpga_checks::gray_groups] {
    for {set bit 0} {$bit < 6} {incr bit} {
        append cdc [format {%d CDC-3 Safe  Max Delay Datapath Only  src %s/gen_sync[%d].i_sync/reg_q_reg[0]/D
} [incr seq] $group $bit]
    }
    if {[string match */i_cdc_fifo_gray_dst_* $group]} {
        append cdc "[incr seq] CDC-15 Safe  Max Delay Datapath Only  src $group/i_spill_register/data/D\n"
    }
    append skew [format {Slack (MET): 0.500ns
Endpoint Destination: %s/gen_sync[0].i_sync/reg_q_reg[0]/D
Requirement: 3.000ns
} $group]
}
append cdc {999 CDC-3 Safe  False Path  src gen_status_sync[2].i_sync/reg_q_reg[0]/D}
assert {![llength [fpga_checks::cdc_failures $cdc]]} "dual CDC complete"
assert {![llength [fpga_checks::skew_failures $skew true]]} "dual skew complete"
set missing [regsub -all -line {^.*gen_ddr2\.[^\n]*\n} $cdc {}]
assert {[llength [fpga_checks::cdc_failures $missing]] == 65} "missing C2 rejected"
set broken [regsub {Max Delay Datapath Only(  src gen_ddr2)} $cdc {False Path\1}]
assert {[llength [fpga_checks::cdc_failures $broken]] == 1} "no C2 pointer waiver"

proc current_project {args} { return $::project_name }
proc get_filesets {args} { return sources_1 }
proc get_property {key object} {
    switch $key {
        NAME { return $object }
        verilog_define { return $::defines }
        default { error "Unexpected property $key" }
    }
}
foreach profile {baseline host dual_ddr} {
    set ::env(ARA_FPGA_PROFILE) $profile
    source $scripts/config.tcl
    set build_dir [file join $scratch $project_name]
    set defines [concat FPGA $profile_defines]
    if {$profile ne "baseline"} {
        assert {[catch {require_project_profile}]} "nonbaseline project requires provenance marker"
        put $build_dir/profile.txt $profile
    }
    require_project_profile
    set defines [concat $defines ARA_FPGA_DDR2=1]
    assert {[catch {require_project_profile}]} "unexpected/duplicate define rejected"
    set defines $profile_defines
    put $build_dir/profile.txt wrong
    assert {[catch {require_project_profile}]} "wrong marker rejected"
    put $build_dir/profile.txt $profile
}
unset ::env(ARA_FPGA_PROFILE)
puts "PASS: $checks profile/IP/CDC/provenance checks (mocked, not Vivado validated)"
