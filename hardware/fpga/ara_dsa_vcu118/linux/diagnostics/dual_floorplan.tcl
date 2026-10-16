# Physical-only plan derived from the 2026-10-06 whole-design census.
# Keep fast logic near each MIG, without removing CDC or IP protection.
namespace eval dual_floor {}
proc dual_floor::plan {} {
    set c1 i_dram_wrapper
    set c2 gen_ddr2.i_dram_wrapper_c2
    set ld $c1/gen_ethernet.i_eth_loader/i_loader/loader_bd_i
    return [list \
        [list ara_c1_mig CLOCKREGION_X4Y12:CLOCKREGION_X4Y14 [list $c1/gen_channel_c1.i_dram]] \
        [list ara_c2_mig CLOCKREGION_X2Y1:CLOCKREGION_X2Y3 [list $c2/gen_channel_c2.i_dram]] \
        [list ara_c1_fifo CLOCKREGION_X1Y12:CLOCKREGION_X3Y13 [list \
            $c1/gen_cdc.i_axi_cdc_mig $c1/i_ddr_r_cut $c1/i_ui_rstgen $c1/i_ui_por]] \
        [list ara_c1_fast CLOCKREGION_X2Y12:CLOCKREGION_X3Y13 [list \
            $c1/gen_ethernet.i_eth_shared_ddr $ld/ddr_fabric $ld/dma $ld/cdma \
            $ld/mb_axi_periph $ld/mac/inst/eth_buf $ld/rst_ddr_300M]] \
        [list ara_c2_fifo CLOCKREGION_X0Y1:CLOCKREGION_X1Y3 [list \
            $c2/gen_cdc.i_axi_cdc_mig $c2/i_ddr_r_cut $c2/i_ui_rstgen $c2/i_ui_por]] \
        [list ara_loader_control CLOCKREGION_X2Y6:CLOCKREGION_X5Y9 [list \
            $ld/mb $ld/mb_local_memory $ld/mdm_1 $ld/mb_axi_intc $ld/timer]]]
}
proc dual_floor::validate_regions {} {
    # Keep user regions west of the measured C1/C2 MIG footprints. Actual
    # automatic macro legality still needs validation by the placer.
    foreach item [plan] {
        lassign $item name range members
        if {[string match ara_c?_mig $name]} {
            set expected [dict create ara_c1_mig CLOCKREGION_X4Y12:CLOCKREGION_X4Y14 \
                ara_c2_mig CLOCKREGION_X2Y1:CLOCKREGION_X2Y3]
            if {![dict exists $expected $name] || $range ne [dict get $expected $name]} {
                error "MIG region differs from measured footprint: $name"
            }
            continue
        }
        if {![regexp {^CLOCKREGION_X([0-9]+)Y([0-9]+):CLOCKREGION_X([0-9]+)Y([0-9]+)$} $range -> x0 y0 x1 y1]} {
            error "Unrecognized floorplan range: $range"
        }
        foreach footprint {{4 12 4 14} {2 1 2 3}} {
            lassign $footprint a b c d
            if {$x0 <= $c && $a <= $x1 && $y0 <= $d && $b <= $y1} {
                error "User region intersects audited MIG footprint: $name"
            }
        }
    }
}
proc dual_floor::buffer_name {} {
    return i_dram_wrapper/gen_ethernet.i_eth_loader/i_loader/loader_bd_i/mdm_1/U0/No_Dbg_Reg_Access.BUFG_DRCK/Using_FPGA.Native
}
proc dual_floor::index {} {
    set objects [get_cells -quiet -hier -filter {!IS_PRIMITIVE}]
    set indexed [dict create]
    foreach obj $objects name [get_property NAME $objects] {dict set indexed $name $obj}
    return $indexed
}
proc dual_floor::apply {out} {
    validate_regions
    set indexed [index]
    set resolved {}
    foreach item [plan] {
        lassign $item name range paths
        if {[llength [get_pblocks -quiet $name]]} {error "Candidate Pblock already exists: $name"}
        set objects {}
        foreach path $paths {
            if {![dict exists $indexed $path]} {error "Missing reviewed hierarchy: $path"}
            lappend objects [dict get $indexed $path]
        }
        lappend resolved [list $name $range $objects]
    }
    set buffer [get_cells -quiet -hier -filter "NAME == [buffer_name]"]
    if {[llength $buffer]!=1 || [get_property REF_NAME $buffer] ne "BUFGCE"} {error "MDM clock buffer changed"}
    if {[get_property IS_LOC_FIXED $buffer] in {1 true TRUE}} {error "Do not override a fixed clock buffer"}
    file mkdir $out
    set f [open [file join $out plan.tsv] w]
    puts $f "pblock\trange\thierarchy"
    foreach item $resolved {
        lassign $item name range objects
        set pb [create_pblock $name]
        resize_pblock $pb -add $range
        add_cells_to_pblock $pb $objects
        # Explicit MIG regions use the vendor's default soft-Pblock policy;
        # hard PHY/BEL/IO constraints remain intact. User logic stays bounded.
        set_property IS_SOFT [expr {[string match ara_c?_mig $name] ? "true" : "false"}] $pb
        # Do not reserve empty fabric or contain routes: other logic may pack
        # into unused sites, and CDC connections may route across boundaries.
        set_property EXCLUDE_PLACEMENT false $pb
        set_property CONTAIN_ROUTING false $pb
        foreach obj $objects {puts $f "$name\t$range\t$obj"}
        report_utilization -pblocks $pb -file [file join $out ${name}_capacity.rpt]
    }
    close $f
    # BSCAN is at X5Y6 in SLR1. The old BUFG was at X2Y11 in SLR2,
    # despite a vendor soft SLR1 assignment. Constrain a region, not a BEL.
    set_property CLOCK_REGION X4Y6 $buffer
    if {[get_property CLOCK_REGION $buffer] ne "X4Y6"} {error "MDM clock region not applied"}
    return $resolved
}
