# Standalone Ethernet loader block design. No synthesis or board programming.
namespace eval loader_bd {
    proc require_interface {name} {
        set pin [get_bd_intf_pins -quiet $name]
        if {[llength $pin] != 1 || ![llength [get_bd_intf_nets -quiet -of_objects $pin]]} {
            error "Unconnected interface: $name"
        }
    }

    proc require_pin {name} {
        set pin [get_bd_pins -quiet $name]
        if {[llength $pin] != 1 || ![llength [get_bd_nets -quiet -of_objects $pin]]} {
            error "Unconnected pin: $name"
        }
    }

    proc require_pair {left right} {
        set left_net [get_bd_intf_nets -quiet -of_objects [get_bd_intf_pins $left]]
        set right_net [get_bd_intf_nets -quiet -of_objects [get_bd_intf_pins $right]]
        if {[llength $left_net] != 1 || $left_net ne $right_net} {
            error "Stream mismatch: $left ($left_net) and $right ($right_net)"
        }
    }

    proc require_pin_pair {left right} {
        set left_net [get_bd_nets -quiet -of_objects [get_bd_pins $left]]
        set right_net [get_bd_nets -quiet -of_objects [get_bd_pins $right]]
        if {[llength $left_net] != 1 || $left_net ne $right_net} {
            error "Pin mismatch: $left ($left_net) and $right ($right_net)"
        }
    }

    proc require_ddr_map {channel space} {
        set found 0
        foreach segment [get_bd_addr_segs -quiet -of_objects [get_bd_addr_spaces $space]] {
            if {![string match *ddr* $segment]} { continue }
            set offset [get_property OFFSET $segment]
            set range [get_property RANGE $segment]
            if {$offset ne "0x80000000" || $range ne "0x80000000"} {
                error "DDR map mismatch: $space offset=$offset range=$range"
            }
            puts $channel "DDR_MAP $space OFFSET=$offset RANGE=$range"
            incr found
        }
        if {$found != 1} { error "Expected one DDR mapping for $space, got $found" }
    }

    proc run {output board_repo {mode baseline}} {
        if {[version -short] ne "2020.1"} { error "Expected Vivado 2020.1" }
        if {$mode ni {baseline cdma}} { error "Expected baseline or cdma mode" }
        if {[file exists $output]} { error "Output already exists: $output" }
        file mkdir $output
        set_param board.repoPaths [list [file normalize $board_repo]]
        create_project eth_loader_bd [file join $output project] -part xcvu9p-flga2104-2L-e
        set_property board_part xilinx.com:vcu118:part0:2.4 [current_project]
        create_bd_design loader_bd

        set mac [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_ethernet:7.2 mac]
        set_property -dict [dict create \
            CONFIG.PHY_TYPE SGMII CONFIG.ENABLE_LVDS true CONFIG.speed_1_2p5 1G \
            CONFIG.SupportLevel 1 CONFIG.processor_mode true CONFIG.ENABLE_AVB false \
            CONFIG.Enable_1588 false CONFIG.USE_BOARD_FLOW true CONFIG.PHYADDR 1 \
            CONFIG.EnableAsyncSGMII false CONFIG.axiliteclkrate 100 \
            CONFIG.ETHERNET_BOARD_INTERFACE sgmii_lvds \
            CONFIG.MDIO_BOARD_INTERFACE mdio_mdc \
            CONFIG.PHYRST_BOARD_INTERFACE Custom \
            CONFIG.DIFFCLK_BOARD_INTERFACE sgmii_phyclk CONFIG.lvdsclkrate 625 \
            CONFIG.tx_in_upper_nibble false CONFIG.rxnibblebitslice0used false \
            CONFIG.txlane0_placement DIFF_PAIR_2 CONFIG.rxlane0_placement DIFF_PAIR_0] $mac

        set dma [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_dma:7.1 dma]
        set_property -dict [dict create CONFIG.c_include_sg 1 \
            CONFIG.c_s_axis_s2mm_tdata_width 32 CONFIG.c_m_axis_mm2s_tdata_width 32 \
            CONFIG.c_m_axi_s2mm_data_width 64 CONFIG.c_addr_width 32] $dma
        if {$mode eq "cdma"} {
            set cdma [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_cdma:4.1 cdma]
            set_property -dict [dict create CONFIG.C_INCLUDE_SG 0 \
                CONFIG.C_INCLUDE_DRE 1 CONFIG.C_M_AXI_DATA_WIDTH 64 \
                CONFIG.C_M_AXI_MAX_BURST_LEN 32] $cdma
            if {[get_property CONFIG.C_INCLUDE_DRE $cdma] != 1} {
                error "CDMA DRE is required for unaligned frame payloads"
            }
        }
        set mb [create_bd_cell -type ip -vlnv xilinx.com:ip:microblaze:11.0 mb]
        set ddr [create_bd_cell -type ip -vlnv xilinx.com:ip:ddr4:2.2 ddr]
        set_property -dict [list \
            CONFIG.System_Clock {No_Buffer} CONFIG.Reference_Clock {No_Buffer} \
            CONFIG.C0_DDR4_BOARD_INTERFACE {ddr4_sdram_c1_062} \
            CONFIG.C0.DDR4_InputClockPeriod {4000} CONFIG.C0.DDR4_CLKOUT0_DIVIDE {5} \
            CONFIG.C0.DDR4_MemoryPart {MT40A256M16LY-062E} \
            CONFIG.C0.DDR4_TimePeriod {833} CONFIG.C0.DDR4_DataWidth {64} \
            CONFIG.C0.DDR4_DataMask {DM_NO_DBI} CONFIG.C0.DDR4_MCS_ECC {false} \
            CONFIG.C0.DDR4_CasWriteLatency {12} CONFIG.C0.DDR4_CasLatency {18} \
            CONFIG.C0.DDR4_AxiDataWidth {512} CONFIG.C0.DDR4_AxiAddressWidth {31} \
            CONFIG.C0.DDR4_AxiNarrowBurst {true} CONFIG.C0.DDR4_AxiIDWidth {8} \
            CONFIG.C0.BANK_GROUP_WIDTH {1} CONFIG.C0.DDR4_AxiSelection {true}] $ddr

        set clock [create_bd_cell -type ip -vlnv xilinx.com:ip:clk_wiz:6.0 clock]
        set_property -dict [list CONFIG.PRIM_IN_FREQ {250.000} \
            CONFIG.PRIM_SOURCE {No_buffer} CONFIG.NUM_OUT_CLKS {1} \
            CONFIG.CLKOUT1_USED {true} \
            CONFIG.CLKOUT1_REQUESTED_OUT_FREQ {100.000}] $clock
        set temporary_clock [create_bd_port -dir I -type clk -freq_hz 250000000 clock_in]
        connect_bd_net $temporary_clock [get_bd_pins clock/clk_in1]
        apply_bd_automation -rule xilinx.com:bd_rule:microblaze -config [dict create \
            local_mem 128KB ecc None cache None debug_module {Debug Only} \
            axi_periph Enabled axi_intc 1 clk {/clock/clk_out1 (100 MHz)}] $mb

        # The MicroBlaze automation caps local_mem at 128KB, while the linked
        # standalone lwIP image requires more. Extend the generated dual-port
        # BRAM and both CPU address mappings together before validation.
        set local_bram [get_bd_cells mb_local_memory/lmb_bram]
        set_property CONFIG.Write_Depth_A 131072 $local_bram
        foreach {space segment} {
            mb/Data mb_local_memory/dlmb_bram_if_cntlr/SLMB/Mem
            mb/Instruction mb_local_memory/ilmb_bram_if_cntlr/SLMB/Mem
        } {
            assign_bd_address -target_address_space [get_bd_addr_spaces $space] \
                -offset 0x00000000 -range 512K [get_bd_addr_segs $segment]
        }

        set timer [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_timer:2.0 timer]
        set_property CONFIG.NUM_PORTS 4 [get_bd_cells mb_xlconcat]
        set_property -dict [list CONFIG.C_DISABLE_SYNCHRONIZERS {0} \
            CONFIG.C_NUM_SYNC_FF {2} CONFIG.C_ASYNC_INTR {0xE}] \
            [get_bd_cells mb_axi_intc]

        apply_bd_automation -rule xilinx.com:bd_rule:axi_ethernet \
            -config {FIFO_DMA DMA} $mac
        set control_slaves {mac/s_axi dma/S_AXI_LITE timer/S_AXI}
        if {$mode eq "cdma"} { lappend control_slaves cdma/S_AXI_LITE }
        foreach slave $control_slaves {
            apply_bd_automation -rule xilinx.com:bd_rule:axi4 -config [list \
                Master {/mb (Periph)} Clk_master Auto Clk_slave Auto Clk_xbar Auto] \
                [get_bd_intf_pins $slave]
        }
        foreach {source sink} {
            timer/interrupt mb_xlconcat/In0
            mac/mac_irq mb_xlconcat/In1
            dma/mm2s_introut mb_xlconcat/In2
            dma/s2mm_introut mb_xlconcat/In3
        } { connect_bd_net [get_bd_pins $source] [get_bd_pins $sink] }
        foreach master {{/mb (Periph)} /dma/M_AXI_SG /dma/M_AXI_MM2S /dma/M_AXI_S2MM} {
            apply_bd_automation -rule xilinx.com:bd_rule:axi4 -config [list \
                Master $master Clk_master Auto Clk_slave Auto Clk_xbar Auto] \
                [get_bd_intf_pins ddr/C0_DDR4_S_AXI]
        }

        # Vivado 2020.1 leaves the three DMA-side interconnect outputs dangling.
        # Join them and the CPU's DDR path before assigning DMA address segments.
        set ddr_net [get_bd_intf_nets -of_objects [get_bd_intf_pins ddr/C0_DDR4_S_AXI]]
        set cpu_ddr_master {}
        foreach pin [get_bd_intf_pins -of_objects $ddr_net] {
            if {[get_property MODE $pin] eq "Master"} { lappend cpu_ddr_master $pin }
        }
        if {[llength $cpu_ddr_master] != 1} {
            error "Expected one CPU DDR master, got $cpu_ddr_master"
        }
        delete_bd_objs $ddr_net
        set fabric [create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect:1.0 ddr_fabric]
        set input_count [expr {$mode eq "cdma" ? 5 : 4}]
        set_property -dict [list CONFIG.NUM_SI $input_count CONFIG.NUM_MI {1} \
            CONFIG.NUM_CLKS {2}] $fabric
        connect_bd_intf_net [get_bd_intf_pins ddr_fabric/M00_AXI] \
            [get_bd_intf_pins ddr/C0_DDR4_S_AXI]
        connect_bd_intf_net $cpu_ddr_master [get_bd_intf_pins ddr_fabric/S00_AXI]
        foreach {source target} {
            axi_mem_intercon/M00_AXI ddr_fabric/S01_AXI
            axi_mem_intercon_1/M00_AXI ddr_fabric/S02_AXI
            axi_mem_intercon_2/M00_AXI ddr_fabric/S03_AXI
        } { connect_bd_intf_net [get_bd_intf_pins $source] [get_bd_intf_pins $target] }
        if {$mode eq "cdma"} {
            connect_bd_intf_net [get_bd_intf_pins cdma/M_AXI] \
                [get_bd_intf_pins ddr_fabric/S04_AXI]
            connect_bd_net [get_bd_pins clock/clk_out1] [get_bd_pins cdma/m_axi_aclk]
        }
        connect_bd_net [get_bd_pins ddr/c0_ddr4_ui_clk] [get_bd_pins ddr_fabric/aclk]
        connect_bd_net [get_bd_pins clock/clk_out1] [get_bd_pins ddr_fabric/aclk1]
        connect_bd_net [get_bd_pins rst_ddr_300M/peripheral_aresetn] \
            [get_bd_pins ddr_fabric/aresetn]
        set segment [get_bd_addr_segs ddr/C0_DDR4_MEMORY_MAP/C0_DDR4_ADDRESS_BLOCK]
        foreach space {dma/Data_SG dma/Data_MM2S dma/Data_S2MM} {
            assign_bd_address -target_address_space [get_bd_addr_spaces $space] \
                -offset 0x80000000 -range 2G $segment
        }
        if {$mode eq "cdma"} {
            assign_bd_address -target_address_space [get_bd_addr_spaces cdma/Data] \
                -offset 0x80000000 -range 2G $segment
        }

        set definitions [get_ipdefs -all -quiet xilinx.com:ip:util_ds_buf:*]
        if {[llength $definitions] != 1} { error "Expected one util_ds_buf IP" }
        delete_bd_objs [get_bd_nets -of_objects [get_bd_pins clock/clk_in1]]
        delete_bd_objs [get_bd_ports clock_in]
        set buffer [create_bd_cell -type ip -vlnv [lindex $definitions 0] sys_clk_250_buffer]
        set_property -dict [list CONFIG.C_BUF_TYPE {IBUFDS}] $buffer
        set port [create_bd_intf_port -mode Slave \
            -vlnv xilinx.com:interface:diff_clock_rtl:1.0 sys_clk_250]
        set_property CONFIG.FREQ_HZ 250000000 $port
        connect_bd_intf_net $port [get_bd_intf_pins sys_clk_250_buffer/CLK_IN_D]
        connect_bd_net [get_bd_pins sys_clk_250_buffer/IBUF_OUT] \
            [get_bd_pins clock/clk_in1] [get_bd_pins ddr/c0_sys_clk_i]
        set ref [create_bd_intf_port -mode Slave \
            -vlnv xilinx.com:interface:diff_clock_rtl:1.0 sgmii_phyclk]
        set_property CONFIG.FREQ_HZ 625000000 $ref
        connect_bd_intf_net $ref [get_bd_intf_pins mac/lvds_clk]
        set memory [create_bd_intf_port -mode Master \
            -vlnv xilinx.com:interface:ddr4_rtl:1.0 ddr4_sdram_c1_062]
        connect_bd_intf_net $memory [get_bd_intf_pins ddr/C0_DDR4]
        set reset [create_bd_port -dir I -type rst sys_reset]
        set_property CONFIG.POLARITY ACTIVE_HIGH $reset
        foreach sink {clock/reset ddr/sys_rst rst_clock_100M/ext_reset_in} {
            connect_bd_net $reset [get_bd_pins $sink]
        }

        validate_bd_design
        set report [open [file join $output bd_report.txt] w]
        puts $report "BD_VALIDATED [version -short]"
        puts $report "MODE $mode"
        foreach pin {
            mac/m_axis_rxd mac/m_axis_rxs mac/s_axis_txc mac/s_axis_txd
            mac/s_axi dma/S_AXI_LITE dma/M_AXI_SG dma/M_AXI_MM2S
            dma/M_AXI_S2MM timer/S_AXI ddr/C0_DDR4_S_AXI ddr/C0_DDR4
        } {
            require_interface $pin
            puts $report "CONNECTED $pin"
        }
        if {$mode eq "cdma"} {
            foreach pin {cdma/S_AXI_LITE cdma/M_AXI} {
                require_interface $pin
                puts $report "CONNECTED $pin"
            }
            puts $report "CDMA_DRE [get_property CONFIG.C_INCLUDE_DRE $cdma]"
        }
        foreach {left right} {
            mac/m_axis_rxd dma/S_AXIS_S2MM
            mac/m_axis_rxs dma/S_AXIS_STS
            mac/s_axis_txc dma/M_AXIS_CNTRL
            mac/s_axis_txd dma/M_AXIS_MM2S
        } {
            require_pair $left $right
            puts $report "STREAM_PAIR $left $right"
        }
        foreach {source sink} {
            timer/interrupt mb_xlconcat/In0
            mac/mac_irq mb_xlconcat/In1
            dma/mm2s_introut mb_xlconcat/In2
            dma/s2mm_introut mb_xlconcat/In3
        } {
            require_pin_pair $source $sink
            puts $report "IRQ_PAIR $source $sink"
        }
        foreach pin {
            clock/clk_in1 ddr/c0_sys_clk_i mac/axis_clk mac/s_axi_lite_clk
            dma/m_axi_sg_aclk ddr_fabric/aclk ddr_fabric/aclk1
        } {
            require_pin $pin
            puts $report "CLOCK_CONNECTED $pin"
        }
        if {$mode eq "cdma"} {
            require_pin cdma/m_axi_aclk
            puts $report "CLOCK_CONNECTED cdma/m_axi_aclk"
        }
        require_pin_pair sys_clk_250_buffer/IBUF_OUT clock/clk_in1
        require_pin_pair sys_clk_250_buffer/IBUF_OUT ddr/c0_sys_clk_i
        puts $report "SHARED_250MHZ_REFERENCE clock/clk_in1 ddr/c0_sys_clk_i"
        set ddr_spaces {mb/Data dma/Data_SG dma/Data_MM2S dma/Data_S2MM}
        if {$mode eq "cdma"} { lappend ddr_spaces cdma/Data }
        foreach space $ddr_spaces {
            require_ddr_map $report $space
        }
        if {[get_property CONFIG.Write_Depth_A $local_bram] != 131072} {
            error "Local BRAM depth did not remain at 512KB"
        }
        foreach {space segment} {
            mb/Data dlmb_bram_if_cntlr
            mb/Instruction ilmb_bram_if_cntlr
        } {
            set found 0
            foreach mapped [get_bd_addr_segs -quiet -of_objects [get_bd_addr_spaces $space]] {
                if {![string match *$segment* $mapped]} { continue }
                set range [get_property RANGE $mapped]
                if {$range ne "0x00080000"} {
                    error "Local BRAM map mismatch: $space range=$range"
                }
                incr found
            }
            if {$found != 1} { error "Expected one 512KB local-memory mapping for $space" }
            puts $report "LOCAL_BRAM $space RANGE=512K"
        }
        puts $report "NOT_READY no_XDC_no_firmware_no_BIT_no_board_test"
        close $report
        save_bd_design
        close_project
        puts "LOADER_BD_VALIDATED $output"
    }
}

if {![info exists ::loader_bd_library_only]} {
    if {[llength $argv] < 2 || [llength $argv] > 3} {
        error "Usage: loader_bd_build.tcl OUTPUT BOARD_REPO ?baseline|cdma?"
    }
    if {[catch {loader_bd::run {*}$argv} message options]} {
        puts stderr [dict get $options -errorinfo]
        exit 1
    }
    exit 0
}
