# Tcl syntax/path regression, NOT a Vivado or IP implementation model.
set root [file normalize [lindex $argv 0]]
set mock_project ""
set mock_dir ""
set mock_sources {}
set mock_ip_names {}
set mock_generated_ips {}
set mock_ip_runs {}
array set params {board.repoPaths {}}
proc create_project {name dir args} { set ::mock_project $name; set ::mock_dir $dir }
proc current_project {args} { return $::mock_project }
proc get_param {name} { return $::params($name) }
proc set_param {name value} { set ::params($name) $value }
proc get_parts {args} { return [lindex $args end] }
proc get_board_parts {args} { return [lindex $args end] }
proc set_property {args} {}
proc get_property {name args} {
    switch $name {
        PERIOD { return 3.333 }
        DIRECTORY { return $::mock_dir }
        default { error "Unexpected mocked property $name" }
    }
}
proc current_fileset {} { return sources_1 }
proc add_files {args} {
    set path [lindex $args end]
    if {![file exists $path]} { error "Tcl references missing file $path" }
    lappend ::mock_sources $path
}
proc get_runs {args} { return $args }
proc create_ip {args} { lappend ::mock_ip_names [lindex $args end] }
proc get_ips {patterns} {
    set objects {}
    foreach pattern $patterns {
        foreach name $::mock_ip_names {
            if {[string match $pattern $name] && [lsearch -exact $objects $name] < 0} {
                lappend objects $name
            }
        }
    }
    return $objects
}
proc generate_target {target objects} {
    if {$target ne "all" || ![llength $objects]} { error "Unexpected IP generation request" }
    foreach name $objects {
        if {[lsearch -exact $::mock_ip_names $name] < 0} { error "Unknown IP $name" }
        lappend ::mock_generated_ips $name
    }
}
proc create_ip_run {objects} {
    # UG835 limits this command to one IP, unlike generate_target.
    if {[llength $objects] != 1} { error "create_ip_run requires exactly one sub-design" }
    set name [lindex $objects 0]
    if {[lsearch -exact $::mock_generated_ips $name] < 0} { error "IP targets missing: $name" }
    if {[lsearch -exact $::mock_ip_runs $name] >= 0} { error "Duplicate IP run: $name" }
    lappend ::mock_ip_runs $name
}
proc get_files {args} { return $args }
proc report_ip_status {args} {}
proc get_ports {args} { return [lindex $args end] }
proc get_nets {args} { return mock_net }
proc get_pins {args} { return mock_pin }
proc get_clocks {args} { return mock_clock }
proc current_design {} { return mock_design }
proc create_clock {args} {}
proc set_input_jitter {args} {}
proc set_clock_groups {args} {}
proc set_input_delay {args} {}
proc set_output_delay {args} {}
proc set_max_delay {args} {}
proc set_false_path {args} {}

foreach path [concat [glob $root/scripts/*.tcl] [glob $root/constraints/*.xdc]] {
    set fd [open $path r]
    set text [read $fd]
    close $fd
    if {![info complete $text]} { error "Incomplete Tcl syntax: $path" }
}
source $root/scripts/create_project.tcl
if {$mock_ip_names ne "clkwiz vio ddr4"} { error "Unexpected IP list $mock_ip_names" }
if {$mock_generated_ips ne $mock_ip_names} { error "Missing IP output products" }
if {$mock_ip_runs ne $mock_ip_names} { error "Missing or duplicate IP synthesis runs" }
if {![catch {create_ip_run [get_ips {clkwiz vio ddr4}]} reason] ||
    $reason ne "create_ip_run requires exactly one sub-design"} {
    error "Mock must reject multi-IP create_ip_run"
}
if {[llength $mock_sources] != [expr {[llength $rtl_files] + 3}]} { error "Source count mismatch" }
if {[llength [lsort -unique $rtl_files]] != [llength $rtl_files]} { error "Duplicate file" }
if {[lsearch -exact $rtl_defines ARA_QBS_ENABLE=1] < 0} { error "QBS disabled" }
if {[lsearch -exact $rtl_defines ARA_AKV_V2_ENABLE=1] < 0} { error "AKV-v2 disabled" }
foreach path [glob $root/constraints/*.xdc] { source $path }
puts "PASS: Tcl syntax, create-project command path, source list, per-IP synthesis run creation"
