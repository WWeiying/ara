# Model create/open/IP OOC operations; no vendor tool or IP model is used.
set scripts [file normalize [file join [file dirname [info script]] .. scripts]]
set scratch [file normalize [lindex $argv 0]]
if {[llength $argv] != 1 || [file exists $scratch]} { error "Pass a new scratch directory" }
set checks 0
proc assert {condition message} {
    if {![uplevel 1 [list expr $condition]]} { error "ASSERT: $message" }
    incr ::checks
}
proc put {path data} {
    file mkdir [file dirname $path]
    set f [open $path w]; puts $f $data; close $f
}
proc opt {args name} { return [lindex $args [expr {[lsearch -exact $args $name]+1}]] }
proc current_project {args} { return $::active }
proc current_fileset {} { return sources_1 }
proc get_filesets {args} { return sources_1 }
proc get_parts {args} { return [lindex $args end] }
proc get_board_parts {args} { return [lindex $args end] }
proc get_param {args} { return {} }
proc set_param {args} {}
proc add_files {args} {}
proc get_files {args} { return [lindex $args end] }
proc get_ips {args} {
    set result {}
    foreach name [lindex $args end] { if {$name in $::ips} { lappend result $name } }
    return $result
}
proc get_runs {args} {
    set name [lindex $args end]
    if {$name in {synth_1 impl_1} || [dict exists $::statuses $name]} { return $name }
    return {}
}
proc set_property {args} {
    if {[lindex $args 0] eq "-dict"} {
        dict set ::props [lindex $args end] [lindex $args 1]
    } else { dict set ::props [lindex $args 2] [lindex $args 0] [lindex $args 1] }
}
proc get_property {key object} {
    switch $key {
        NAME { return $object }
        DIRECTORY {
            if {$object eq $::project_name} { return $::build_dir }
            return [file join $::build_dir runs $object]
        }
        IS_LOCKED { return [expr {$::fault eq "locked" && $object eq "jtag_debug"}] }
        NEEDS_REFRESH { return [expr {$::fault eq "stale" && $object eq "jtag_debug_synth_1"}] }
        STATUS { return [dict get $::statuses $object] }
        default { return [dict get $::props $object $key] }
    }
}
proc create_project {name dir args} {
    assert {![file exists $dir]} "never overwrite existing project directory"
    set ::active $name
    put [file join $dir $name.xpr] "mock project"
    incr ::creations
}
proc open_project {path} { set ::active $::project_name }
proc close_project {} { set ::active "" }
proc create_ip {args} {
    set name [opt $args -module_name]
    assert {$name ni $::ips} "no IP recreation"
    lappend ::ips $name
}
proc generate_target {args} {}
proc create_ip_run {name} { dict set ::statuses ${name}_synth_1 "Not started" }
proc report_ip_status {args} { put [opt $args -file] "mock report" }
proc launch_runs {runs args} {
    foreach run $runs {
        assert {[dict get $::statuses $run] eq "Not started"} "only pending OOC launch"
        lappend ::launches $run
        dict set ::statuses $run "synth_design Complete!"
        set name [string range $run 0 end-8]
        put [file join [get_property DIRECTORY $run] ${name}.dcp] "mock IP checkpoint"
    }
}
proc wait_on_run {args} {}
foreach forbidden {reset_runs delete_runs upgrade_ip write_bitstream} {
    proc $forbidden {args} { error "Forbidden destructive operation" }
}

foreach profile {baseline host dual_ddr} {
    set root [file join $scratch $profile]
    file mkdir $root/scripts
    foreach name {config.tcl common.tcl constraint_checks.tcl create_ip.tcl create_project.tcl prepare_profile.tcl run_support.tcl} {
        file copy $scripts/$name $root/scripts/$name
    }
    put $root/scripts/sources.tcl {set rtl_files {}; set rtl_include_dirs {}; set rtl_defines {FPGA}}
    set ::env(ARA_FPGA_PROFILE) $profile
    set active ""; set props {}; set ips {}; set statuses {}; set fault ""
    set creations 0; set launches {}
    source $root/scripts/prepare_profile.tcl
    assert {$creations == 1} "create separate selected project"
    assert {[lsort $launches] eq [lsort [dict keys $statuses]]} "prepare all selected OOC IPs"
    assert {[string trim [fpga_checks::read_report $build_dir/profile.txt]] eq $profile} "profile provenance"
    assert {$active eq ""} "close on success"
    set launches {}
    source $root/scripts/prepare_profile.tcl
    assert {$creations == 1 && ![llength $launches]} "repeat prepare checks only, no recreating or rerunning"
    set active wrong_project
    assert {[catch {source $root/scripts/prepare_profile.tcl} message]} "reject incompatible active project"
    assert {[string match *Close* $message]} "explain active project"
    set active ""
    if {$profile eq "baseline"} { continue }
    foreach fault {locked stale} {
        assert {[catch {source $root/scripts/prepare_profile.tcl}]} "reject $fault IP"
        assert {![llength $launches]} "no launch after failed preflight"
        set active ""
    }
    set fault ""
    dict set statuses jtag_debug_synth_1 "synth_design ERROR"
    assert {[catch {source $root/scripts/prepare_profile.tcl} message]} "failed IP is not silently reset"
    assert {[string match {*Refusing to restart*} $message]} "failed run diagnostic"
    assert {![llength $launches]} "all IP preflight before launch"
    set active ""
}
unset ::env(ARA_FPGA_PROFILE)
puts "PASS: $checks create/prepare profile checks (mocked, not Vivado validated)"
