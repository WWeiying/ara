# Linked-netlist checks and pad routing budgets, not an external PHY timing model.
namespace eval ara_eth_timing {
    proc one {objects what} {
        if {[llength $objects] != 1} { error "Ethernet: expected one $what: $objects" }
        return $objects
    }
    proc apply {} {
        set root i_dram_wrapper/gen_ethernet.i_eth_loader/i_loader/loader_bd_i
        set mb [one [get_pins -quiet $root/mb/Clk] "MicroBlaze clock pin"]
        set management [one [get_clocks -quiet -of_objects $mb] "management clock"]
        set ui [one [get_clocks -quiet -of_objects [one \
            [get_pins -quiet i_dram_wrapper/gen_ethernet.i_eth_loader/i_control/clk] "UI clock pin"]] "UI clock"]
        foreach clock [list $management $ui] period {10.0 3.333} {
            set actual [get_property PERIOD $clock]
            if {![string is double -strict $actual] || abs($actual - $period) > 0.01} {
                error "Ethernet: unexpected clock period $clock=$actual (expected $period)"
            }
        }
        # Keep vendor SmartConnect/DMA/PCS clock and CDC constraints. No blanket
        # asynchronous clock groups: the management and UI clocks share a source.
        foreach name {eth_mdio eth_mdc eth_phy_reset_n} {
            set port [one [get_ports -quiet $name] "$name port"]
            set_max_delay 20.0 -datapath_only -from $management -to $port
        }
        set mdio [one [get_ports -quiet eth_mdio] "MDIO input"]
        set endpoints [all_fanout -flat -endpoints_only $mdio]
        if {![llength $endpoints]} { error "Ethernet: missing MDIO capture endpoints" }
        set_max_delay 20.0 -datapath_only -from $mdio -to $endpoints
        puts "ETH_TIMING management=$management ui=$ui mdio_capture=$endpoints"
        # MDIO's slow enabled transfers and multicycle constraints are provided by
        # TEMAC. These additional 20-ns budgets match the reviewed diagnostic pad
        # budgets; report their coverage/overrides and review actual routed paths.
    }
}
if {![info exists ::ara_eth_timing_library_only]} { ara_eth_timing::apply }
