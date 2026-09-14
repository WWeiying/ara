set package_root [file normalize [file join [file dirname [info script]] ..]]
source [file join $package_root scripts config.tcl]
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
    report_clocks -file [file join $dir clocks.rpt]
    set loops [write_loop_details $dir]
    if {$reject_loops && $loops} {
        error "Combinational loops remain; inspect $dir/loop_cells.rpt. No bitstream was generated."
    }
}

# LUT names alone cannot distinguish RTL feedback from a mapping problem.
proc write_loop_details {dir} {
    report_drc -checks {LUTLP-1} -name ara_loops -force -file [file join $dir loops.rpt]
    set violations [get_drc_violations -quiet -name ara_loops LUTLP*]
    set out [open [file join $dir loop_cells.rpt] w]
    set seeds {}
    puts $out "LUTLP violations: [llength $violations]"
    try {
        foreach violation $violations {
            puts $out "VIOLATION $violation"
            foreach cell [get_cells -quiet -of_objects $violation] {
                lappend seeds $cell
                write_cell_details $out $cell
            }
        }
    } finally { close $out }
    write_loop_fanin $dir $seeds
    return [llength $violations]
}

proc write_cell_details {out cell} {
    puts $out "CELL $cell REF_NAME=[get_property REF_NAME $cell]"
    foreach key {INIT ORIG_REF_NAME ORIG_CELL_NAME FILE_NAME LINE_NUMBER} {
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
proc write_loop_fanin {dir seeds {limit 2048}} {
    if {$limit < 1} { error "Invalid fanin report limit" }
    set queue [lsort -unique $seeds]
    set seen {}
    foreach cell $queue { dict set seen $cell 1 }
    set out [open [file join $dir loop_fanin.rpt] w]
    puts $out "Loop fanin, maximum $limit cells; sequential cells are boundaries"
    try {
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
    } finally { close $out }
}

proc require_no_combinational_loops {dir} {
    file mkdir $dir
    if {[write_loop_details $dir]} {
        error "Combinational loops remain; inspect $dir/loop_cells.rpt. Implementation/bitstream blocked."
    }
}
