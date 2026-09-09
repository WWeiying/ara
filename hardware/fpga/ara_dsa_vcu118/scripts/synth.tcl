source [file join [file dirname [info script]] common.tcl]
open_package_project
set pending_ips [list]
foreach name {clkwiz_synth_1 vio_synth_1 ddr4_synth_1} {
    if {![llength [get_runs -quiet $name]]} { error "Missing IP run $name; check IP generation." }
    if {![string match {*synth_design Complete*} [get_property STATUS [get_runs $name]]]} {
        lappend pending_ips $name
    }
}
if {[llength $pending_ips]} { launch_runs $pending_ips -jobs $run_jobs }
foreach name $pending_ips {
    wait_on_run $name
    check_run $name {*synth_design Complete*}
}
launch_runs synth_1 -jobs $run_jobs
wait_on_run synth_1
check_run synth_1 {*synth_design Complete*}
open_run synth_1
write_reports synth
puts "Synthesis complete; inspect reports/synth before implementation."
