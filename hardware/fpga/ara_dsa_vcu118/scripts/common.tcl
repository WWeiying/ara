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
}

proc check_run {name expected} {
    set status [get_property STATUS [get_runs $name]]
    if {![string match $expected $status]} {
        error "$name did not complete successfully: $status. Read the run log."
    }
}

proc write_reports {stage} {
    global package_root
    set dir [file join $package_root reports $stage]
    file mkdir $dir
    report_utilization -hierarchical -file [file join $dir utilization.rpt]
    report_timing_summary -report_unconstrained -file [file join $dir timing_summary.rpt]
    check_timing -verbose -file [file join $dir check_timing.rpt]
    report_cdc -details -file [file join $dir cdc.rpt]
    report_clock_interaction -file [file join $dir clock_interaction.rpt]
    report_drc -file [file join $dir drc.rpt]
}
