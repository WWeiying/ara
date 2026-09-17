set package_root [file normalize [file join [file dirname [info script]] ..]]
source [file join $package_root scripts config.tcl]
source [file join $package_root scripts constraint_checks.tcl]
set build_dir [file join $package_root build $project_name]
set xpr_path [file join $build_dir ${project_name}.xpr]

proc require_vivado {} {
    if {![llength [info commands create_project]]} {
        error "Run this script inside Vivado, not a standalone Tcl interpreter."
    }
}

proc open_package_project {} {
    global xpr_path project_name
    require_vivado
    if {![file exists $xpr_path]} { error "First source scripts/create_project.tcl" }
    if {[current_project -quiet] eq ""} {
        open_project $xpr_path
    } elseif {[file normalize [get_property DIRECTORY [current_project]]] ne
              [file normalize [file dirname $xpr_path]]} {
        error "A different project is open; close it first."
    }
    configure_package_constraints
}

proc configure_package_constraints {} {
    global package_root
    set cdc [get_files -quiet [file join $package_root constraints cdc.xdc]]
    if {[llength $cdc] != 1} { error "Missing package CDC constraint file in project" }
    # Existing XPRs cache FILE_TYPE. Vivado 2020.1 rejects control flow in XDC.
    set_property FILE_TYPE TCL $cdc
    set_property USED_IN_SYNTHESIS false $cdc
    set_property USED_IN_IMPLEMENTATION true $cdc
    set_property PROCESSING_ORDER LATE $cdc
}

proc check_run {name expected} {
    set status [get_property STATUS [get_runs $name]]
    if {![string match $expected $status]} {
        error "$name did not complete successfully: $status. Read the run log."
    }
}

proc require_no_multiple_drivers {dir} {
    file mkdir $dir
    report_drc -checks MDRV-1 -name ara_drivers -force -file [file join $dir multiple_drivers.rpt]
    if {[llength [get_drc_violations -name ara_drivers MDRV*]]} {
        error "Multiple drivers remain; inspect $dir/multiple_drivers.rpt. Run was not accepted."
    }
}

proc write_reports {stage {reject_loops false}} {
    global package_root
    set dir [file join $package_root reports $stage]
    file mkdir $dir
    report_utilization -hierarchical -file [file join $dir utilization.rpt]
    report_timing_summary -report_unconstrained -file [file join $dir timing_summary.rpt]
    check_timing -verbose -file [file join $dir check_timing.rpt]
    report_cdc -details -file [file join $dir cdc.rpt]
    report_clock_interaction -file [file join $dir clock_interaction.rpt]
    report_drc -file [file join $dir drc.rpt]
    report_timing -delay_type max -max_paths 50 -nworst 1 -slack_lesser_than 0 \
        -file [file join $dir setup_paths.rpt]
    report_exceptions -ignored -file [file join $dir ignored_exceptions.rpt]
    # -ignored omits partially overridden exceptions. Coverage exposes those
    # as well as empty paths; needed for the bundled-data DMI constraints.
    report_exceptions -coverage -file [file join $dir exception_coverage.rpt]
    report_clocks -file [file join $dir clocks.rpt]
    report_bus_skew -delay_type min_max -warn_on_violation -file [file join $dir bus_skew.rpt]
    report_methodology -file [file join $dir methodology.rpt]
    report_io -file [file join $dir io.rpt]
    report_exceptions -file [file join $dir exceptions.rpt]
    report_timing -delay_type min -max_paths 50 -nworst 1 -slack_lesser_than 0 \
        -file [file join $dir hold_paths.rpt]
    write_clock_io_details $dir
    # Collect the fixed fault cone in the same run, even if no loop remains.
    set fault_cells [get_cells -quiet -hierarchical -filter {NAME =~ */i_fpga_compute_fault}]
    write_loop_fanin $dir $fault_cells 64 fault_decode.rpt
    set loops [write_loop_details $dir]
    if {$reject_loops && $loops} {
        error "Combinational loops remain; inspect $dir/loop_cells.rpt. No bitstream was generated."
    }
    # Historical-netlist inspection cannot validate the new physical structure.
    if {![string match inspect* $stage]} { write_boundary_checks $dir $reject_loops }
}

# Check actual reset connectivity, not the name of an automatically inserted
# global buffer. BUFGCTRL/test muxes and buffers on the short POR paths remain
# forbidden; only ungated buffers driven by the final SoC/UI reset FF qualify.
proc reset_buffer_failures {out} {
    set failures {}
    set buffers [get_cells -quiet -hierarchical -filter \
        {NAME =~ */i_rstgen_bypass/* && REF_NAME =~ BUFG*}]
    puts $out "RESET_BUFG_COUNT=[llength $buffers] CELLS=$buffers"
    foreach buffer $buffers {
        set type [get_property REF_NAME $buffer]
        set owner [file dirname [get_property NAME $buffer]]
        if {$type ni {BUFG BUFGCE} || $owner ni \
                {i_rstgen/i_rstgen_bypass i_dram_wrapper/i_ui_rstgen/i_rstgen_bypass}} {
            lappend failures "reset clock mux or POR buffer remains: $buffer ($type)"
            continue
        }
        set input [get_pins -quiet -of_objects $buffer -filter {REF_PIN_NAME == I}]
        if {[llength $input] != 1} {
            lappend failures "reset buffer must have one I pin: $buffer (pins=$input)"
            continue
        }
        set net [get_nets -quiet -segments -of_objects $input]
        set drivers {}
        if {[llength $net]} {
            set drivers [get_pins -quiet -leaf -of_objects $net -filter {DIRECTION == OUT}]
        }
        set expected [format {%s/synch_regs_q_reg[3]/Q} $owner]
        puts $out "RESET_BUFFER $buffer TYPE=$type DRIVERS=$drivers"
        if {[llength $drivers] != 1 ||
            [get_property NAME $drivers] ne $expected} {
            lappend failures "reset buffer is not driven by the final reset FF: $buffer"
        }
        set inputs [list I $input]
        if {$type eq "BUFGCE"} {
            set ce [get_pins -quiet -of_objects $buffer -filter {REF_PIN_NAME == CE}]
            if {[llength $ce] != 1} {
                lappend failures "reset BUFGCE must have one CE pin: $buffer (pins=$ce)"
                continue
            }
            set ce_net [get_nets -quiet -segments -of_objects $ce]
            set ce_driver {}
            if {[llength $ce_net]} {
                set ce_driver [get_pins -quiet -leaf -of_objects $ce_net -filter {DIRECTION == OUT}]
            }
            set ce_cell {}
            if {[llength $ce_driver] == 1} { set ce_cell [get_cells -quiet -of_objects $ce_driver] }
            puts $out "RESET_BUFFER_CE $buffer DRIVERS=$ce_driver CELLS=$ce_cell"
            if {[llength $ce_driver] != 1 || [llength $ce_cell] != 1 ||
                [get_property REF_NAME $ce_cell] ne "VCC"} {
                lappend failures "reset BUFGCE must be always enabled by one VCC driver: $buffer"
            }
            lappend inputs CE $ce
        }
        # UG912 (2020.1): inversion is a netlist PIN property. Optional cell
        # attributes can be empty after BUFG -> BUFGCE unisim transformation.
        foreach {name pin} $inputs {
            set code [catch {get_property IS_INVERTED $pin} inverted]
            puts $out "RESET_BUFFER_PIN $buffer/$name QUERY_ERROR=$code IS_INVERTED=[list $inverted]"
            if {$code || ![string is boolean -strict $inverted]} {
                lappend failures "reset buffer pin inversion unavailable: $buffer/$name ([list $inverted])"
            } elseif {$inverted} {
                lappend failures "reset buffer pin must be non-inverting: $buffer/$name"
            }
        }
    }
    return $failures
}

# Fail closed on missing/overridden budgets after saving the diagnostics. Missing
# CDC constraints fail even before routing; estimated negative slack does not.
proc write_boundary_checks {dir routed} {
    set out [open [file join $dir boundary_checks.rpt] w]
    set failures {}
    set code [catch {
        set failures [reset_buffer_failures $out]
        set root i_dram_wrapper/gen_cdc.i_axi_cdc_mig
        foreach channel {w r} width {579 525} source {src dst} dest {dst src} {
            foreach half {src dst} side [list $source $dest] gen {write read} {
                set fifo $root/i_axi_cdc_$side/i_cdc_fifo_gray_${half}_$channel
                set regs [get_cells -quiet -hierarchical -filter \
                    "NAME =~ $fifo/*gen_fpga_${gen}*select_q_reg* && REF_NAME =~ FD*"]
                set expected [expr {32 * (($width+63)/64)}]
                puts $out "SELECTOR $channel $half COUNT=[llength $regs] EXPECTED=$expected"
                if {[llength $regs] != $expected} { lappend failures "$channel $half selector replicas missing" }
            }
        }
        foreach port {jtag_tck_i jtag_tms_i jtag_tdi_i uart_rx_i jtag_tdo_o uart_tx_o c0_ddr4_reset_n} \
                budget {20.0 20.0 20.0 70.0 20.0 70.0 ui} \
                direction {in in in in out out out} {
            set pad [get_ports -quiet $port]
            if {$budget eq "ui"} {
                set clocks [get_clocks -quiet -of_objects [get_pins -quiet \
                    $root/i_axi_cdc_dst/i_cdc_fifo_gray_src_r/src_clk_i]]
                if {[llength $clocks] != 1} {
                    lappend failures "DDR UI clock missing"; continue
                }
                set budget [get_property PERIOD $clocks]
            }
            set args [list -delay_type max -max_paths 1]
            if {$direction eq "in"} { lappend args -from $pad } else { lappend args -to $pad }
            set paths {}
            if {[llength $pad] == 1} { set paths [get_timing_paths -quiet {*}$args] }
            if {[llength $paths] != 1} {
                puts $out "PAD $port MISSING_TIMED_PATH"
                lappend failures "$port has no timed path"; continue
            }
            set slack [get_property SLACK $paths]
            set requirement [get_property REQUIREMENT $paths]
            puts $out "PAD $port BUDGET=$budget REQUIREMENT=$requirement SLACK=$slack"
            # inf is a valid Tcl double, but is not a constrained timing path.
            set finite {^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$}
            if {![regexp $finite $slack] || ![regexp $finite $requirement]} {
                lappend failures "$port is unconstrained"
            } elseif {abs($requirement - $budget) > 0.001 || $slack < 0} {
                lappend failures "$port physical budget missing or violated"
            }
            report_timing {*}$args -file [file join $dir pad_$port.rpt]
        }
        set reset [get_ports -quiet c0_ddr4_reset_n]
        set standard [get_property IOSTANDARD $reset]
        puts $out "DDR_RESET_IOSTANDARD=$standard"
        if {$standard ne "LVCMOS12"} { lappend failures "DDR reset must use LVCMOS12" }
        set hub [get_clocks -quiet -of_objects [get_pins -quiet dbg_hub/clk]]
        set vio [get_clocks -quiet -of_objects [get_pins -quiet i_vio/clk]]
        puts $out "DEBUG_HUB_CLOCK=$hub VIO_CLOCK=$vio"
        if {[llength $hub] != 1 || $hub ne $vio} {
            lappend failures "debug hub and VIO clocks differ"
        }
        set constraint_failures [write_constraint_checks $dir $routed]
        set failures [concat $failures $constraint_failures]
        puts $out "FAILURES=[llength $failures]: $failures"
    } result options]
    set close_code [catch {close $out} close_result close_options]
    if {$code} { return -options $options $result }
    if {$close_code} { return -options $close_options $close_result }
    if {[llength $constraint_failures] || ($routed && [llength $failures])} {
        error "Physical boundary checks failed: $failures. Inspect $dir/boundary_checks.rpt."
    }
}

# Capture actual drivers/clock coverage as well as the bounded pad paths.
# Do not create guessed generated clocks on debug-hub outputs.
proc write_clock_io_details {dir} {
    set out [open [file join $dir clock_io.rpt] w]
    set code [catch {
        foreach cell [get_cells -quiet dbg_hub] {
            puts $out "CELL $cell"
            foreach key {REF_NAME IS_BLACKBOX} {
                if {$key in [list_property $cell]} {
                    puts $out "  $key=[get_property $key $cell]"
                }
            }
        }
        foreach kind {port pin} patterns {
            {jtag_tck_i uart_rx_i c0_ddr4_reset_n}
            {dbg_hub/clk {dbg_hub/sl_iport0_o[1]} {dbg_hub/sl_iport1_o[1]}}
        } {
            foreach pattern $patterns {
                if {$kind eq "port"} { set objects [get_ports -quiet $pattern] } \
                else { set objects [get_pins -quiet $pattern] }
                if {![llength $objects]} { puts $out "MISSING $kind $pattern" }
                foreach object $objects {
                    puts $out "OBJECT $object CLOCKS=[get_clocks -quiet -of_objects $object]"
                    set nets [get_nets -quiet -segments -of_objects $object]
                    if {![llength $nets]} { puts $out "  NO NET"; continue }
                    set drivers [get_pins -quiet -leaf -of_objects $nets -filter {DIRECTION == OUT}]
                    puts $out "  NETS=$nets DRIVERS=$drivers"
                    if {[llength $drivers]} {
                        foreach cell [get_cells -quiet -of_objects $drivers] {
                            puts $out "  DRIVER_CELL=$cell REF_NAME=[get_property REF_NAME $cell]"
                        }
                    }
                }
            }
        }
    } result options]
    set close_code [catch {close $out} close_result close_options]
    if {$code} { return -options $options $result }
    if {$close_code} { return -options $close_options $close_result }
}

# LUT names alone cannot distinguish RTL feedback from a mapping problem.
proc write_loop_details {dir} {
    report_drc -checks {LUTLP-1} -name ara_loops -force -file [file join $dir loops.rpt]
    set violations [get_drc_violations -quiet -name ara_loops LUTLP*]
    set out [open [file join $dir loop_cells.rpt] w]
    set seeds {}
    # Preserve diagnostics and release the file even on an extraction failure.
    # catch is supported by the older Tcl embedded in Windows Vivado 2020.1.
    set code [catch {
        puts $out "LUTLP violations: [llength $violations]"
        foreach violation $violations {
            puts $out "VIOLATION $violation"
            foreach cell [get_cells -quiet -of_objects $violation] {
                lappend seeds $cell
                write_cell_details $out $cell
            }
        }
    } result options]
    set close_code [catch {close $out} close_result close_options]
    if {$code} { return -options $options $result }
    if {$close_code} { return -options $close_options $close_result }
    write_loop_fanin $dir $seeds
    return [llength $violations]
}

proc write_cell_details {out cell} {
    puts $out "CELL $cell REF_NAME=[get_property REF_NAME $cell]"
    foreach key {INIT DONT_TOUCH ORIG_REF_NAME ORIG_CELL_NAME FILE_NAME LINE_NUMBER} {
        if {$key in [list_property $cell]} { puts $out "  $key=[get_property $key $cell]" }
    }
    if {[get_property IS_SEQUENTIAL $cell]} {
        puts $out "  BOUNDARY sequential"
        return {}
    }
    set fanin {}
    foreach pin [get_pins -quiet -of_objects $cell] {
        set direction [get_property DIRECTION $pin]
        set nets [get_nets -quiet -segments -of_objects $pin]
        puts $out "  PIN $pin $direction NETS=$nets"
        if {[llength $nets]} {
            set drivers [get_pins -quiet -leaf -of_objects $nets -filter {DIRECTION == OUT}]
            puts $out "    DRIVERS=$drivers"
            puts $out "    PORTS=[get_ports -quiet -of_objects $nets]"
            if {$direction eq "IN" && [llength $drivers]} {
                foreach source [get_cells -quiet -of_objects $drivers] { lappend fanin $source }
            }
        }
    }
    return [lsort -unique $fanin]
}

# Include side inputs of the loop, stopping at registers instead of exporting
# the whole QBS netlist. A hard node bound keeps this diagnostic uploadable.
proc write_loop_fanin {dir seeds {limit 2048} {filename loop_fanin.rpt}} {
    if {$limit < 1} { error "Invalid fanin report limit" }
    set queue [lsort -unique $seeds]
    set seen {}
    foreach cell $queue { dict set seen $cell 1 }
    set out [open [file join $dir $filename] w]
    set code [catch {
        puts $out "Cell fanin, maximum $limit cells; sequential cells are boundaries"
        for {set n 0} {$n < [llength $queue] && $n < $limit} {incr n} {
            foreach source [write_cell_details $out [lindex $queue $n]] {
                if {![dict exists $seen $source]} {
                    dict set seen $source 1
                    lappend queue $source
                }
            }
        }
        set pending [expr {[llength $queue] - $n}]
        puts $out "Visited $n cells; pending $pending"
        if {$pending} { puts $out "TRUNCATED: remaining cells [lrange $queue $n end]" }
    } result options]
    set close_code [catch {close $out} close_result close_options]
    if {$code} { return -options $options $result }
    if {$close_code} { return -options $close_options $close_result }
}

proc require_no_combinational_loops {dir} {
    file mkdir $dir
    if {[write_loop_details $dir]} {
        error "Combinational loops remain; inspect $dir/loop_cells.rpt. Implementation/bitstream blocked."
    }
}
