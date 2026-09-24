# Isolated Vivado 2020.1 check of the host DDR IP narrow-burst setting.
if {[llength $argv] != 3} { error "Expected output board_repo scripts_dir" }
lassign $argv output board_repo scripts_dir
set output [file normalize $output]
set board_repo [file normalize $board_repo]
set scripts_dir [file normalize $scripts_dir]
if {[file exists $output]} { error "Output already exists: $output" }
if {![file isfile [file join $scripts_dir create_ip.tcl]]} {
    error "Missing create_ip.tcl"
}
file mkdir $output
if {[version -short] ne "2020.1"} { error "Expected Vivado 2020.1" }
set_param board.repoPaths [list $board_repo]
create_project narrow_probe [file join $output project] -part xcvu9p-flga2104-2L-e
set boards [get_board_parts -quiet xilinx.com:vcu118:part0:2.4]
if {[llength $boards] != 1} { error "Bundled VCU118 board part unavailable" }
set_property board_part [lindex $boards 0] [current_project]
set ::env(ARA_FPGA_PROFILE) host
source [file join $scripts_dir config.tcl]
source [file join $scripts_dir create_ip.tcl]
set actual [get_property CONFIG.C0.DDR4_AxiNarrowBurst [get_ips ddr4]]
puts "DDR4_NARROW_BURST=$actual"
if {![string is boolean -strict $actual] || ![string is true -strict $actual]} {
    error "Host DDR4 IP did not enable narrow bursts"
}
puts "DDR4_DATA_WIDTH=[get_property CONFIG.C0.DDR4_AxiDataWidth [get_ips ddr4]]"
puts "STATE ip_config_generated_no_synthesis_or_board_access"
close_project
