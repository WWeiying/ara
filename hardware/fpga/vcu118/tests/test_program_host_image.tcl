# Mock the hardware-manager API to verify board VIO selection before board use.
set script [file normalize [file join [file dirname [info script]] .. .. ara_dsa_vcu118 scripts program_host_image.tcl]]
set root [file join /tmp ara_test_program_host_image_[pid]]
file mkdir $root
foreach name {image.bit image.ltx} {
    set out [open [file join $root $name] w]
    puts $out fixture
    close $out
}

rename exit tcl_exit
proc exit {code} { set ::exit_code $code }
proc open_hw_manager {} {}
proc connect_hw_server {args} {}
proc get_hw_targets {} { return {target0} }
proc open_hw_target {target} {}
proc get_hw_devices {args} { return {xcvu9p_0} }
proc current_hw_device {device} {}
proc set_property {name value object} {
    if {$name eq "OUTPUT_VALUE" && $object eq "board:reset"} {
        lappend ::reset_values $value
    }
}
proc program_hw_devices {device} { incr ::program_count }
proc refresh_hw_device {device} {}
proc get_hw_vios {args} { return $::vios }
proc get_hw_probes {args} {
    set vio [lindex $args end]
    if {$vio eq "board"} {
        return {board:reset board:mode board:select board:status}
    }
    return {eth:status eth:enable}
}
proc get_property {name object} {
    if {$name eq "PART"} { return xcvu9p }
    if {$name eq "INPUT_VALUE"} { return e }
    set fields [dict create \
        board:reset {vio_reset vio_output 0} \
        board:mode {vio_boot_mode vio_output 1} \
        board:select {vio_boot_select vio_output 2} \
        board:status {status vio_input 0} \
        eth:status {status vio_input 0} \
        eth:enable {enable vio_output 0}]
    set index [dict create NAME 0 TYPE 1 PROBE_PORT 2]
    return [lindex [dict get $fields $object] [dict get $index $name]]
}
proc commit_hw_vio {vio} { lappend ::committed $vio }
proc refresh_hw_vio {vio} {}
proc close_hw_target {target} {}
proc disconnect_hw_server {} {}
proc close_hw_manager {} {}

foreach vios {{board} {eth board} {board eth}} {
    set ::vios $vios
    set ::program_count 0
    set ::reset_values {}
    set ::committed {}
    set ::exit_code -1
    set argv [list [file join $root image.bit] [file join $root image.ltx]]
    source $script
    if {$::exit_code != 0 || $::program_count != 1 ||
        $::reset_values ne {1 0} || $::committed ne {board board}} {
        error "Failed VIO selection for $vios"
    }
}
set ::vios {board eth}
set ::program_count 0
set ::reset_values {}
set ::committed {}
set ::exit_code -1
set argv [list [file join $root image.bit] [file join $root image.ltx] --cold-no-reset]
source $script
if {$::exit_code != 0 || $::program_count != 1 ||
    $::reset_values ne {0} || $::committed ne {board}} {
    error "Cold programming unexpectedly pulsed board reset"
}
set ::vios {eth}
if {![catch {board_vio xcvu9p_0}]} { error "Ethernet VIO was accepted as board VIO" }
set ::vios {board board}
if {![catch {board_vio xcvu9p_0}]} { error "Ambiguous board VIO was accepted" }
puts "PASS: board VIO selected with one or two VIO cores"
rename exit {}
rename tcl_exit exit
