# Create once, then prepare/check only this profile's OOC IP. Never reset runs.
source [file join [file dirname [info script]] common.tcl]
require_vivado
if {[current_project -quiet] ne ""} { error "Close the current project first." }
if {[file exists $xpr_path]} {
    open_package_project
} else {
    if {[file exists $build_dir]} {
        error "Incomplete/existing project directory: $build_dir. Inspect it; nothing was overwritten."
    }
    source [file join $package_root scripts create_project.tcl]
}
source [file join $package_root scripts run_support.tcl]
set_param general.maxThreads $max_threads
set pending {}
foreach name $profile_ips {
    set ip [get_ips -quiet $name]
    if {[llength $ip] != 1 || [get_property IS_LOCKED $ip]} {
        error "Missing/locked IP: $name. No upgrade or recreation was requested."
    }
    set run [get_runs -quiet ${name}_synth_1]
    if {[llength $run] != 1} { error "Missing OOC run for $name; inspect project creation log." }
    set status [get_property STATUS $run]
    if {[string match {*synth_design Complete*} $status]} {
        fpga_run::reusable ${name}_synth_1 {*synth_design Complete*} ${name}.dcp
    } elseif {$status eq "Not started"} {
        lappend pending $run
    } else {
        error "Refusing to restart $run ($status). Inspect its log; no run was reset."
    }
}
if {[llength $pending]} { launch_runs $pending -jobs $run_jobs }
foreach run $pending {
    wait_on_run $run
    check_run $run {*synth_design Complete*}
}
fpga_run::check_ips
close_project
puts "PROFILE READY: $fpga_profile; project=$xpr_path"
puts "IP synthesis/check only. Next: scripts/run.ps1 -Profile $fpga_profile -Stage all"
