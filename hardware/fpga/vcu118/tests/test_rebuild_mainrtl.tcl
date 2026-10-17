set rebuild_test_mode 1
source [file join [file dirname [info script]] .. ethernet rebuild_mainrtl.tcl]
set root [lindex $argv 0]
if {$root eq "" || [file exists $root]} {error "Supply a new test directory"}
file mkdir $root
set ref [file join $root reference.dcp]
set f [open $ref w]; puts $f test; close $f
rename source real_source
proc source {args} {}
set fpga_profile host_ethernet
set design_top ara_dsa_vcu118
set max_threads 8
namespace eval fpga_run {}
namespace eval fpga_checks {}
proc record {args} {lappend ::calls $args}
foreach name {open_package_project set_param set_property current_run check_run
              require_no_multiple_drivers require_no_combinational_loops
              report_incremental_reuse report_timing_summary close_project} {
    proc $name {args} {}
}
proc fpga_checks::finite {x} {return 1}
proc get_param {name} {return {}}
proc fpga_run::check_ips {} {}
proc fpga_run::reusable {args} {}
proc fpga_run::clone_run {base name parent} {record clone $name $parent; return $name}
proc fpga_run::wait_checked {args} {if {$::scenario eq "worker_fail"} {error worker}}
proc wait_on_run {args} {if {$::scenario eq "worker_fail"} {error worker}}
proc fpga_run::launch_error {args} {}
proc fpga_run::nonempty {p} {if {![file isfile $p] || ![file size $p]} {error "Missing checkpoint"}}
proc fpga_run::require_timing {args} {if {$::scenario eq "timing_fail"} {error timing}}
proc launch_runs {args} {
    record launch {*}$args
    if {[lindex $args end] eq "opt_design"} {
        set dir [file join [lindex $args [expr {[lsearch $args -dir]+1}]] [lindex $args 0]]
        file mkdir $dir
        foreach name {.opt_design.end.rst .vivado.end.rst ara_dsa_vcu118_opt.dcp} {
            set f [open [file join $dir $name] w]; puts $f data; close $f
        }
        set f [open [file join $dir runme.log] w]
        if {$::scenario eq "constraint_fail"} {
            puts $f {CRITICAL WARNING: [Common 17-1548] Command failed: CDC: profile mismatch}
        } else { puts $f {opt_design completed successfully} }
        close $f
    }
}
proc open_run {name} {record open $name}
proc open_checkpoint {path} {record open_checkpoint $path}
proc read_checkpoint {args} {record reuse {*}$args}
proc place_design {} {record place}
proc route_design {args} {record route {*}$args}
proc phys_opt_design {args} {record phys_opt {*}$args}
proc write_checkpoint {path} {record checkpoint $path}
proc report_route_status {args} {
    if {[lindex $args 1] eq "ERRORS_IN_ROUTES"} {return 0}
    return [expr {$::scenario ne "route_fail"}]
}
proc get_timing_paths {args} {return path}
proc get_runs {args} {return [lindex $args end]}
proc get_property {args} {
    if {[lindex $args 0] eq "PARENT"} {
        if {$::scenario eq "existing_wrong_parent"} {return synth_wrong}
        return synth_abcdef012345
    }
    if {[lindex $args 0] eq "STATUS" && [string match existing_* $::scenario] &&
        [lsearch -glob $::calls {launch *}] < 0} {
        if {$::scenario eq "existing_started"} {return "Running opt_design"}
        return "Not started"
    }
    if {[lindex $args 0] eq "STATUS"} {return "Not started place_design"}
    return [expr {$::scenario eq "setup_fail" ? -0.1 : 0.1}]
}
foreach scenario {pass worker_fail constraint_fail route_fail timing_fail} {
    set calls {}
    set out [file join $root $scenario]; file mkdir $out
    set code [catch {rebuild_run impl package $out abcdef012345 synth_abcdef012345 $ref} msg]
    if {$code != ($scenario ne "pass")} {error "Unexpected $scenario: $msg"}
    if {$scenario in {worker_fail constraint_fail}} {
        if {[lsearch -glob $calls {reuse *}] >= 0} {error "Continued failed worker"}
        if {[lsearch -exact $calls place] >= 0 || [lsearch -glob $calls {route *}] >= 0} {
            error "Implemented a netlist with failed constraints"
        }
        continue
    }
    if {[lsearch -glob $calls {open_checkpoint *}] < 0 ||
        [lsearch -glob $calls {open_checkpoint *}] >=
        [lsearch -exact $calls [list reuse -incremental $ref]]} {error "Reference replaced current netlist"}
    if {[lsearch -exact $calls [list checkpoint [file join $out ara_dsa_vcu118_routed.dcp]]] < 0} {
        error "Failed result not preserved"
    }
}
set scenario setup_fail
set out [file join $root synth]; file mkdir $out
if {![catch {rebuild_run synth package $out abcdef012345 - $ref} msg]} {error "Accepted negative setup"}
set scenario pass
set calls {}
set out [file join $root resume]; file mkdir $out
rebuild_run resume package $out abcdef012345 - $ref $ref
if {[lsearch -glob $calls {launch *}] >= 0 || [lsearch -glob $calls {clone *}] >= 0} {
    error "Resume rebuilt sources"
}
set dir [file join $root pass impl_abcdef012345]
file delete [file join $dir .opt_design.end.rst]
if {![catch {rebuild_opt_complete impl_abcdef012345 $dir}]} {error "Accepted missing opt marker"}
set f [open [file join $dir .opt_design.end.rst] w]; close $f
set f [open [file join $dir .opt_design.error.rst] w]; close $f
if {![catch {rebuild_opt_complete impl_abcdef012345 $dir}]} {error "Accepted failed opt marker"}
puts "PASS: rebuild scenarios include swallowed constraint error and checkpoint-only resume"
set fpga_profile dual_ddr_ethernet
set scenario pass
set calls {}
set out [file join $root dual]; file mkdir $out
rebuild_run resume package $out abcdef012345 - $ref $ref
if {[lsearch -exact $calls {phys_opt -directive Explore}] < 0} {
    error "Dual-channel build omitted post-route optimization"
}
set scenario timing_fail
set out [file join $root dual_fail]; file mkdir $out
if {![catch {rebuild_run resume package $out abcdef012345 - $ref $ref}]} {
    error "Dual-channel physical optimization bypassed strict timing"
}
puts "PASS: dual profile runs one physical pass and retains strict routed gate"
set rebuild_opt_preflight $ref
proc set_property {args} {record property {*}$args}
set scenario pass
set calls {}
set out [file join $root dual_hook]; file mkdir $out
rebuild_run impl package $out abcdef012345 synth_abcdef012345 $ref
set configured [lsearch -exact $calls [list property STEPS.OPT_DESIGN.TCL.PRE $ref impl_abcdef012345]]
set launched [lsearch -glob $calls {launch *}]
if {$configured < 0 || $configured >= $launched} {error "CDC preflight hook not installed before opt launch"}
puts "PASS: dual CDC hook is installed on the isolated run before implementation"
foreach scenario {existing_pass existing_started existing_wrong_parent} {
    set calls {}
    set out [file join $root $scenario]; file mkdir $out
    set code [catch {rebuild_run impl_existing package $out abcdef012345 synth_abcdef012345 $ref} msg]
    if {$code != ($scenario ne "existing_pass")} {error "Unexpected $scenario: $msg"}
    if {[lsearch -glob $calls {clone *}] >= 0} {error "Continuation cloned or rebuilt a run"}
    if {$scenario ne "existing_pass" && [lsearch -glob $calls {launch *}] >= 0} {error "Launched incompatible existing run"}
}
puts "PASS: continuation accepts only an unstarted implementation with the correct synthesis parent"
