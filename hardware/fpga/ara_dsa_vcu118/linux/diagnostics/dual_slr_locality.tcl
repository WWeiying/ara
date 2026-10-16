# Candidate placement-only correction for the preserved dual-DDR netlist.
# Not loaded by production builds until an isolated placement trial passes.
# USER_SLR_ASSIGNMENT is a soft hierarchical guideline, not signoff:
# https://docs.amd.com/r/en-US/ug912-vivado-properties/USER_SLR_ASSIGNMENT
namespace eval dual_locality {}

proc dual_locality::hierarchy {name} {
    set cell [get_cells -quiet -hierarchical -filter "NAME == $name"]
    if {[llength $cell]!=1 || [get_property IS_PRIMITIVE $cell]} {
        error "Expected retained hierarchy: $name"
    }
    return $cell
}

proc dual_locality::anchor_slr {pattern ref} {
    set cells [get_cells -quiet -hierarchical -filter "NAME =~ $pattern && REF_NAME == $ref"]
    if {![llength $cells]} {error "Missing physical anchor: $pattern / $ref"}
    set sites [get_sites -quiet -of_objects $cells]
    set slr [get_slrs -quiet -of_objects $sites]
    if {[llength $slr]!=1} {error "Anchor must occupy exactly one SLR: $pattern / $slr"}
    return [get_property NAME $slr]
}

proc dual_locality::plan {} {
    set plan {}
    set pcs i_dram_wrapper/gen_ethernet.i_eth_loader/i_loader/loader_bd_i/mac/inst/pcs_pma/inst/pcs_pma_block_i
    set phy_slr [anchor_slr $pcs/gen_io_logic/* RX_BITSLICE]
    lappend plan [list [get_property NAME [hierarchy $pcs]] $phy_slr]
    foreach wrapper {i_dram_wrapper gen_ddr2.i_dram_wrapper_c2} channel {c1 c2} {
        set mig $wrapper/gen_channel_$channel.i_dram/inst/u_ddr4_infrastructure
        set ui_slr [anchor_slr $mig/gen_mmcme4.u_mmcme_adv_inst MMCME4_ADV]
        # Keep both FIFO halves local: the entire bank, not only its read mux,
        # must meet the existing 3 ns asynchronous data-path bound.
        foreach block {i_ui_rstgen i_ui_por gen_cdc.i_axi_cdc_mig i_ddr_r_cut} {
            lappend plan [list [get_property NAME [hierarchy $wrapper/$block]] $ui_slr]
        }
        if {$channel eq "c1"} {
            lappend plan [list [get_property NAME [hierarchy $wrapper/gen_ethernet.i_eth_shared_ddr]] $ui_slr]
        }
    }
    return $plan
}

proc dual_locality::apply {out} {
    # Validate all anchors and hierarchies before changing any property.
    set plan [plan]
    return [apply_plan $plan $out]
}

proc dual_locality::apply_plan {plan out} {
    # A plan measured on placed cells can be replayed on the same opt netlist.
    set resolved {}
    foreach item $plan {
        lassign $item name slr
        set cell [hierarchy $name]
        if {![regexp {^SLR[0-9]+$} $slr]} {error "Invalid SLR: $slr"}
        lappend resolved [list $cell $slr]
    }
    set f [open $out w]
    puts $f "hierarchy\tuser_slr_assignment"
    foreach item $resolved {
        lassign $item cell slr
        set_property USER_SLR_ASSIGNMENT $slr $cell
        if {[get_property USER_SLR_ASSIGNMENT $cell] ne $slr} {
            close $f
            error "Placement guideline did not apply to $cell"
        }
        puts $f "$cell\t$slr"
    }
    close $f
    return $plan
}
