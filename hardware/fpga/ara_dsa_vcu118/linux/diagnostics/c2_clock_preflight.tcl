# Existing MIG IP, isolated top. No hardware manager or source-package writes.
if {[catch {
    if {[llength $argv] != 3} { error "Expected xci package output" }
    lassign $argv xci package out
    if {[file exists $out]} { error "Preflight output exists" }
    file mkdir $out
    cd $out
    set_param board.repoPaths [linsert [get_param board.repoPaths] 0 [file join $package board_files]]
    create_project -in_memory -part xcvu9p-flga2104-2L-e
    set_property board_part xilinx.com:vcu118:part0:2.4 [current_project]
    set_param general.maxThreads 4
    read_ip $xci
    set ip [get_ips ddr4_c2]
    foreach {property expected} {
        CONFIG.C0_DDR4_BOARD_INTERFACE ddr4_sdram_c2_062
        CONFIG.C0.DDR4_InputClockPeriod 4000
        CONFIG.System_Clock No_Buffer
    } {
        if {[get_property $property $ip] ne $expected} {error "Unexpected $property"}
    }
    read_verilog -sv [file join [file dirname [info script]] c2_clock_preflight.sv]
    read_xdc [file join $package constraints ddr2_clock.xdc]
    synth_design -top c2_clock_preflight -part xcvu9p-flga2104-2L-e
    set_property PACKAGE_PIN L19 [get_ports sys_reset]
    set_property IOSTANDARD LVCMOS12 [get_ports sys_reset]
    set_property IOSTANDARD LVCMOS18 [get_ports calibrated]
    foreach cell [get_cells -hier -filter {IS_BLACKBOX == 1}] {
        if {$cell ne "dbg_hub" || [llength [get_debug_cores -quiet dbg_hub]] != 1} {
            error "Unresolved preflight IP: $cell"
        }
    }
    foreach {port pin bank} {c2_sys_clk_p AW26 41 c2_sys_clk_n AW27 41} {
        if {[get_property PACKAGE_PIN [get_ports $port]] ne $pin} {error "Clock pin mismatch"}
        if {[get_property BANK [get_package_pins $pin]] != $bank} {error "Clock bank mismatch"}
    }
    set pads [get_ports c0_ddr4_*]
    if {[llength $pads] < 90} {error "Missing C2 physical ports"}
    foreach pad $pads {
        set pin [get_property PACKAGE_PIN $pad]
        if {$pin eq "" || [get_property BANK [get_package_pins $pin]] ni {40 41 42}} {
            error "C2 pad outside expected banks: $pad $pin"
        }
    }
    # The same MIG generation stage rejected the previous cross-SLR reference.
    opt_design
    set blackboxes [get_cells -hier -filter {IS_BLACKBOX == 1}]
    if {[llength $blackboxes]} {error "Unresolved post-opt IP: $blackboxes"}
    write_checkpoint [file join $out c2_optimized.dcp]
    report_drc -file [file join $out drc.rpt]
    set f [open [file join $out completed.txt] {WRONLY CREAT EXCL}]
    puts $f "C2_MIG_OPT_PASS clock=AW26/AW27 bank=41; not routed or hardware validated"
    close $f
} message]} {
    puts stderr $::errorInfo
    exit 1
}
exit 0
