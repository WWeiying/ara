# Inventory AXI CDMA 4.1 in the same Vivado/VCU118 environment as the loader.
if {[version -short] ne "2020.1"} { error "Expected Vivado 2020.1" }
create_project -in_memory -part xcvu9p-flga2104-2L-e
create_bd_design cdma_inventory
set cdma [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_cdma:4.1 cdma]
set_property -dict [dict create CONFIG.C_INCLUDE_SG 0 \
    CONFIG.C_M_AXI_DATA_WIDTH 64 CONFIG.C_M_AXI_MAX_BURST_LEN 32] $cdma
foreach property {
    CONFIG.C_INCLUDE_SG CONFIG.C_M_AXI_DATA_WIDTH
    CONFIG.C_M_AXI_MAX_BURST_LEN CONFIG.C_ADDR_WIDTH CONFIG.C_INCLUDE_DRE
} {
    if {[catch {get_property $property $cdma} value]} {
        puts "$property UNAVAILABLE"
    } else {
        puts "$property $value"
    }
}
foreach interface [get_bd_intf_pins -of_objects $cdma] {
    puts "INTERFACE $interface [get_property MODE $interface]"
}
foreach pin [get_bd_pins -of_objects $cdma] {
    puts "PIN $pin [get_property DIR $pin]"
}
close_project
