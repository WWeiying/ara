# Initial board bring-up target, not a measured Fmax.
set design_top ara_dsa_vcu118
set fpga_profile baseline
if {[info exists ::env(ARA_FPGA_PROFILE)]} { set fpga_profile $::env(ARA_FPGA_PROFILE) }
if {$fpga_profile ni {baseline host dual_ddr}} {
    error "Invalid ARA_FPGA_PROFILE '$fpga_profile': use baseline, host or dual_ddr"
}
set project_name $design_top
set profile_defines {}
set profile_ips {clkwiz vio ddr4}
if {$fpga_profile ne "baseline"} {
    append project_name _$fpga_profile
    lappend profile_defines ARA_FPGA_HOST
    lappend profile_ips jtag_mem jtag_debug
}
if {$fpga_profile eq "dual_ddr"} {
    lappend profile_defines ARA_FPGA_DDR2
    lappend profile_ips ddr4_c2
}
set fpga_part xcvu9p-flga2104-2L-e
set board_part xilinx.com:vcu118:part0:2.4
set run_jobs 4
set max_threads 8
