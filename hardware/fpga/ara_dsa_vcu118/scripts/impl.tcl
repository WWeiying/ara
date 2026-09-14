source [file join [file dirname [info script]] common.tcl]
open_package_project
check_run synth_1 {*synth_design Complete*}
open_run synth_1
require_no_combinational_loops [file join $package_root reports impl_preflight]
close_design
launch_runs impl_1 -to_step route_design -jobs $run_jobs
wait_on_run impl_1
check_run impl_1 {*route_design Complete*}
open_run impl_1
write_reports impl true
set setup_path [get_timing_paths -quiet -delay_type max -max_paths 1]
set hold_path [get_timing_paths -quiet -delay_type min -max_paths 1]
if {![llength $setup_path] || ![llength $hold_path]} { error "No timing paths; inspect constraints." }
if {[get_property SLACK $setup_path] < 0 || [get_property SLACK $hold_path] < 0} {
    error "Timing not met. Reports saved; bitstream generation was not launched."
}
# Route reports must also be reviewed for unconstrained clocks and CDC findings.
set out [file join $package_root output]
file mkdir $out
write_debug_probes -force [file join $out ${project_name}.ltx]
write_bitstream -force [file join $out ${project_name}.bit]
puts "Bitstream written to $out. Read DRC/CDC reports before programming."
