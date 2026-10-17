# Current RTL is authoritative. A reference DCP supplies physical reuse only.
proc rebuild_stage {out name} {
    set f [open [file join $out stage.txt] w]
    puts $f $name
    close $f
    puts "REBUILD_STAGE $name"
    flush stdout
}
proc rebuild_opt_complete {name dir} {
    # A -to_step opt_design run reports "Not started place_design" in 2020.1.
    # Wait for the worker, then require its completion markers and checkpoint.
    wait_on_run $name
    fpga_run::launch_error $dir
    foreach marker {.opt_design.end.rst .vivado.end.rst} {
        if {![file isfile [file join $dir $marker]]} {error "Missing completion marker: $marker"}
    }
    foreach marker {.opt_design.error.rst .vivado.error.rst} {
        if {[file exists [file join $dir $marker]]} {error "Failed optimized run: $marker"}
    }
    # Vivado 2020.1 can downgrade an unmanaged constraint Tcl error and still
    # finish opt_design. Never spend a placement/routing run on that netlist.
    set log [file join $dir runme.log]
    fpga_run::nonempty $log
    set f [open $log r]
    set contents [read $f]
    close $f
    if {[regexp {(CRITICAL WARNING|ERROR): \[Common 17-1548\]} $contents]} {
        error "Constraint Tcl command failed in $log; no placement or routing permitted"
    }
    set status [get_property STATUS [get_runs $name]]
    if {$status ne "Not started place_design" && ![string match {*opt_design Complete*} $status]} {
        error "Unexpected optimized run status: $status"
    }
    global design_top
    set checkpoint [file join $dir ${design_top}_opt.dcp]
    fpga_run::nonempty $checkpoint
    return $checkpoint
}
proc rebuild_run {mode package out token parent reference {optimized -}} {
    foreach script {common.tcl run_support.tcl} {
        uplevel #0 [list source [file join $package scripts $script]]
    }
    global design_top max_threads fpga_profile
    if {$fpga_profile ni {host_ethernet dual_ddr_ethernet} || ![regexp {^[0-9a-f]{12}$} $token]} {
        error "Invalid rebuild profile/token"
    }
    set_param general.maxThreads $max_threads
    if {$mode ne "resume"} {
        open_package_project
        fpga_run::check_ips
    }
    if {$mode eq "synth"} {
        set name synth_$token
        set run [fpga_run::clone_run synth_1 $name -]
        set_property STEPS.SYNTH_DESIGN.TCL.PRE [file join $package scripts synth_pre.tcl] $run
        current_run -synthesis $run
        rebuild_stage $out synthesis
        launch_runs $name -jobs 1 -dir $out
        fpga_run::wait_checked $name {*synth_design Complete*} [file join $out $name]
        check_run $name {*synth_design Complete*}
        open_run $name
        rebuild_stage $out synthesis_checks
        require_no_multiple_drivers [file join $out preflight]
        require_no_combinational_loops [file join $out preflight]
        report_timing_summary -report_unconstrained -file [file join $out synthesis_timing.rpt]
        foreach kind {max min} {
            set p [get_timing_paths -quiet -delay_type $kind -max_paths 1]
            if {[llength $p] != 1 || ![fpga_checks::finite [get_property SLACK $p]]} {
                error "Missing/invalid synthesis $kind timing path"
            }
            if {$kind eq "max" && [get_property SLACK $p] < 0} {
                error "Synthesis setup failed; no implementation launched"
            }
        }
        # Python separately inventories every failing clock group before impl.
        rebuild_stage $out synthesis_complete_requires_physical_gate
    } elseif {$mode in {impl resume}} {
      if {$mode eq "impl"} {
        if {$parent ne "synth_$token" || ![file isfile $reference]} {
            error "Missing current synthesized parent or physical reference"
        }
        fpga_run::reusable $parent {*synth_design Complete*} ${design_top}.dcp
        set name impl_$token
        set run [fpga_run::clone_run impl_1 $name $parent]
        if {[info exists ::rebuild_opt_preflight]} {
            fpga_run::nonempty $::rebuild_opt_preflight
            set_property STEPS.OPT_DESIGN.TCL.PRE $::rebuild_opt_preflight $run
        }
        current_run -implementation $run
        rebuild_stage $out optimize_current_netlist
        launch_runs $name -jobs 1 -dir $out -to_step opt_design
        set optimized [rebuild_opt_complete $name [file join $out $name]]
        close_project
      } else {
        fpga_run::nonempty $optimized
        fpga_run::nonempty $reference
      }
        rebuild_stage $out opening_current_optimized_checkpoint
        # Restore archived constraints; never apply working-tree XDC to a resume.
        set_param board.repoPaths [linsert [get_param board.repoPaths] 0 [file join $package board_files]]
        open_checkpoint $optimized
        require_no_multiple_drivers [file join $out preflight_opt]
        require_no_combinational_loops [file join $out preflight_opt]
        rebuild_stage $out incremental_matching
        read_checkpoint -incremental $reference
        report_incremental_reuse -file [file join $out reuse_before.rpt]
        rebuild_stage $out incremental_placement
        place_design
        write_checkpoint [file join $out placed.dcp]
        rebuild_stage $out incremental_routing
        route_design
        rebuild_stage $out route_finalize
        route_design -finalize
        if {$fpga_profile eq "dual_ddr_ethernet"} {
            # One physical-only pass before acceptance, as in the closed baseline.
            rebuild_stage $out post_route_physical_optimization
            phys_opt_design -directive Explore
            if {![report_route_status -boolean_check ROUTED_FULLY]} { route_design }
        }
        # Preserve diagnostics even if strict routed timing fails.
        write_checkpoint [file join $out ${design_top}_routed.dcp]
        report_incremental_reuse -file [file join $out reuse_after.rpt]
        rebuild_stage $out routed_timing_gate
        foreach check {ROUTED_FULLY ERRORS_IN_ROUTES} expected {1 0} {
            set value [report_route_status -boolean_check $check]
            if {![string is boolean -strict $value] || [expr {!!$value}] != $expected} {
                error "Route integrity failed: $check=$value"
            }
        }
        fpga_run::require_timing [file join $out routed_gate]
        rebuild_stage $out routed_ready_for_audit
    } else { error "Invalid mode" }
    close_project
}
if {![info exists ::rebuild_test_mode]} {
    if {[catch {
        if {[llength $argv] ni {6 7}} {error "Expected mode package out token parent reference ?optimized?"}
        rebuild_run {*}$argv
    } message]} {
        puts stderr $::errorInfo
        exit 1
    }
    exit 0
}
