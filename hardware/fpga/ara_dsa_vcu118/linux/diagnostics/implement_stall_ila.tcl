# Build observations from the frozen synthesis checkpoint, not current RTL.
namespace eval stall_implementation {}
proc stall_implementation::stage {out name} {
    set f [open [file join $out stage.txt] w]
    puts $f $name
    close $f
    puts "STALL_IMPLEMENTATION_STAGE $name"
    flush stdout
}
proc stall_implementation::run {prepared reference package out width} {
    if {![string is integer -strict $width] || $width < 1 || $width > 1024} {
        error "Invalid expected probe width"
    }
    foreach input [list $prepared $reference] {
        if {![file isfile $input]} { error "Missing checkpoint: $input" }
    }
    if {[file exists $out]} { error "Output already exists: $out" }
    file mkdir $out
    set ::env(ARA_FPGA_PROFILE) host_ethernet
    foreach script {common.tcl run_support.tcl} {
        uplevel #0 [list source [file join $package scripts $script]]
    }
    global board_part fpga_part
    set_param board.repoPaths [linsert [get_param board.repoPaths] 0 [file join $package board_files]]
    if {[llength [get_board_parts -quiet $board_part]] != 1} {
        error "Frozen board definition is unavailable: $board_part"
    }
    # opt_design regenerates debug cores and reapplies board-derived IP XDC.
    # Missing catalog data must stop before a partially constrained design is used.
    set_msg_config -id {Board 49-67} -new_severity ERROR
    set_msg_config -id {Constraints 18-638} -new_severity ERROR
    set_param general.maxThreads 8
    stage $out opening_prepared_observation
    open_checkpoint $prepared
    if {[get_property BOARD_PART [current_project]] ne $board_part ||
        [get_property PART [current_project]] ne $fpga_part} {
        error "Checkpoint board/part does not match the frozen package"
    }
    set cores [get_debug_cores -quiet i_stall_ila]
    if {[llength $cores] != 1} { error "Missing observation core" }
    set probes [get_debug_ports -quiet i_stall_ila/probe0]
    if {[llength $probes] != 1 || [get_property PORT_WIDTH $probes] != $width} {
        error "Observation width mismatch"
    }
    if {[get_property C_DATA_DEPTH $cores] != 1024 ||
        [get_property C_INPUT_PIPE_STAGES $cores] != 1} {
        error "Unexpected observation sampling configuration"
    }
    if {![get_property C_ADV_TRIGGER $cores] ||
        [get_property ALL_PROBE_SAME_MU_CNT $cores] ni {1 2}} {
        error "Unexpected observation trigger configuration"
    }
    # The original prepared DCP used one MU with advanced triggering. Vivado
    # 2020.1 rejects that combination during IP generation (IP_Flow 19-3458).
    # Correct the debug core only; do not reopen or resynthesize functional RTL.
    set_property ALL_PROBE_SAME_MU_CNT 2 $cores
    puts "OBSERVATION_TRIGGER_CONFIG advanced=true match_units=2"
    stage $out optimizing_observation_netlist
    opt_design
    set blackboxes [get_cells -quiet -hierarchical -filter {IS_BLACKBOX == 1}]
    if {[llength $blackboxes]} { error "Unresolved blackboxes after opt_design: $blackboxes" }
    write_checkpoint [file join $out optimized.dcp]
    stage $out incremental_matching
    read_checkpoint -incremental $reference
    report_incremental_reuse -file [file join $out reuse_before.rpt]
    stage $out incremental_placement
    place_design
    write_checkpoint [file join $out placed.dcp]
    stage $out incremental_routing
    route_design
    write_checkpoint [file join $out routed.dcp]
    stage $out routed_reports
    set reports [file join $out reports]
    file mkdir $reports
    report_incremental_reuse -file [file join $out reuse_after.rpt]
    report_route_status -file [file join $reports route_status.rpt]
    foreach check {ROUTED_FULLY ERRORS_IN_ROUTES} expected {1 0} {
        set value [report_route_status -boolean_check $check]
        if {![string is boolean -strict $value] || [expr {!!$value}] != $expected} {
            error "Route integrity failed: $check=$value"
        }
    }
    require_no_multiple_drivers $reports
    write_reports $reports true
    fpga_run::require_timing $reports
    # CDC review and release approval precede bitgen and board access separately.
    stage $out timing_passed_requires_full_audit
    close_design
}
if {![info exists ::stall_implementation_test]} {
    if {[catch {
        if {[llength $argv] != 5} { error "Expected prepared reference package output width" }
        stall_implementation::run {*}$argv
    } message]} {
        puts stderr $::errorInfo
        exit 1
    }
    exit 0
}
