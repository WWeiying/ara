# Read-only feasibility gate for the Vivado 2020.1 Ethernet downloader.
# Creates an isolated project but does not synthesize or connect to hardware.
if {[llength $argv] != 2} {
    error "Usage: loader_preflight.tcl OUTPUT BOARD_REPO"
}
lassign $argv output board_repo
if {[version -short] ne "2020.1"} {
    error "Expected Vivado 2020.1, got [version -short]"
}
if {[file exists $output]} {
    error "Output already exists: $output"
}
file mkdir $output
set_param board.repoPaths [list [file normalize $board_repo]]
create_project eth_loader_preflight [file join $output project] -part xcvu9p-flga2104-2L-e
set_property board_part xilinx.com:vcu118:part0:2.4 [current_project]

set report [open [file join $output ip_preflight.tsv] w]
puts $report "vivado\t[version -short]"
puts $report "part\t[get_property PART [current_project]]"
puts $report "board\t[get_property BOARD_PART [current_project]]"
foreach name {axi_ethernet axi_dma microblaze smartconnect ddr4} {
    set definitions [get_ipdefs -all -quiet "xilinx.com:ip:$name:*"]
    puts $report "$name\t[join $definitions ,]"
    if {![llength $definitions]} {
        close $report
        error "Missing required IP: $name"
    }
}
close $report

create_ip -vlnv xilinx.com:ip:axi_ethernet:7.2 -module_name eth_loader_mac
set mac [get_ips eth_loader_mac]
set mac_desired [dict create \
    CONFIG.PHY_TYPE SGMII \
    CONFIG.ENABLE_LVDS true \
    CONFIG.speed_1_2p5 1G \
    CONFIG.SupportLevel 1 \
    CONFIG.processor_mode true \
    CONFIG.ENABLE_AVB false \
    CONFIG.Enable_1588 false \
    CONFIG.USE_BOARD_FLOW true \
    CONFIG.PHYADDR 1 \
    CONFIG.EnableAsyncSGMII false \
    CONFIG.axiliteclkrate 100 \
    CONFIG.ETHERNET_BOARD_INTERFACE sgmii_lvds \
    CONFIG.MDIO_BOARD_INTERFACE mdio_mdc \
    CONFIG.PHYRST_BOARD_INTERFACE Custom \
    CONFIG.DIFFCLK_BOARD_INTERFACE sgmii_phyclk \
    CONFIG.lvdsclkrate 625 \
    CONFIG.tx_in_upper_nibble false \
    CONFIG.rxnibblebitslice0used false \
    CONFIG.txlane0_placement DIFF_PAIR_2 \
    CONFIG.rxlane0_placement DIFF_PAIR_0]
set_property -dict $mac_desired $mac
set report [open [file join $output mac_config.tsv] w]
dict for {name value} $mac_desired {
    set actual [get_property $name $mac]
    puts $report "$name\t$actual"
    if {![string equal -nocase $actual $value]} {
        close $report
        error "MAC configuration changed: $name expected=$value actual=$actual"
    }
}
close $report

create_ip -vlnv xilinx.com:ip:axi_dma:7.1 -module_name eth_loader_dma
set dma [get_ips eth_loader_dma]
set desired [dict create \
    CONFIG.c_include_sg 1 \
    CONFIG.c_s_axis_s2mm_tdata_width 32 \
    CONFIG.c_m_axis_mm2s_tdata_width 32 \
    CONFIG.c_m_axi_s2mm_data_width 64 \
    CONFIG.c_addr_width 32]
set_property -dict $desired $dma
set report [open [file join $output dma_config.tsv] w]
dict for {name value} $desired {
    set actual [get_property $name $dma]
    puts $report "$name\t$actual"
    if {$actual ne $value} {
        close $report
        error "DMA configuration changed: $name expected=$value actual=$actual"
    }
}
close $report
generate_target all [get_ips {eth_loader_mac eth_loader_dma}]
report_ip_status -license_status -file [file join $output ip_status.rpt]
close_project
puts "LOADER_IP_PREFLIGHT_PASS $output"
