# Observation-only preparation from the frozen synthesized run. No board access.
proc stall_one {objects label} {
    if {[llength $objects] != 1} { error "$label: expected one object, got [llength $objects]" }
    return [lindex $objects 0]
}
proc stall_clock {pin expected} {
    set clock [stall_one [get_clocks -quiet -of_objects $pin] "clock at $pin"]
    if {$clock ne $expected || abs([get_property PERIOD $clock] - 20.0) > 0.001} {
        error "Unexpected capture domain at $pin: $clock"
    }
}
proc stall_prepare {package run connections out} {
    if {[file exists $out]} { error "Output exists: $out" }
    file mkdir $out
    set ::env(ARA_FPGA_PROFILE) host_ethernet
    uplevel #0 [list source [file join $package scripts common.tcl]]
    global xpr_path project_name design_top
    set_param board.repoPaths [linsert [get_param board.repoPaths] 0 [file join $package board_files]]
    open_project -read_only $xpr_path
    if {[get_property NAME [current_project]] ne $project_name} { error "Wrong project" }
    require_project_profile
    if {[get_property STATUS [get_runs $run]] ne "synth_design Complete!"} { error "Synthesis not complete" }
    set expected_dir [file normalize [file join $package .. runs $run]]
    if {[file normalize [get_property DIRECTORY [get_runs $run]]] ne $expected_dir} {
        error "Synthesized run is not the pinned frozen run directory"
    }
    # Both CDC debug-clock wiring and ILA insertion require an editable project.
    # Retain run results in a separate project; never make the frozen XPR writable.
    set original_dcp [file join $expected_dir $design_top.dcp]
    set original_hash [exec certutil -hashfile $original_dcp SHA256]
    set project_copy [file join $out project_copy]
    save_project_as stall_observation $project_copy
    if {[get_property IS_READONLY [current_project]]} { error "Project copy is read-only" }
    if {[file normalize [get_property DIRECTORY [current_project]]] ne [file normalize $project_copy]} {
        error "Observation project is not isolated"
    }
    set copied_dcp [file join [get_property DIRECTORY [get_runs $run]] $design_top.dcp]
    set copied_hash [exec certutil -hashfile $copied_dcp SHA256]
    # certutil's first line contains the path; compare its SHA256 line only.
    if {![regexp -line {^[0-9a-fA-F]{64}\r?$} $original_hash original_digest] ||
        ![regexp -line {^[0-9a-fA-F]{64}\r?$} $copied_hash copied_digest] ||
        [string trim $original_digest] ne [string trim $copied_digest]} {
        error "Copied synthesis checkpoint does not match the frozen source"
    }
    open_run $run
    foreach cell [get_cells -quiet -hierarchical -filter {IS_BLACKBOX == 1}] {
        if {$cell ne "dbg_hub"} { error "Unlinked IP: $cell" }
    }
    set f [open $connections r]
    set header [gets $f]
    if {$header ne "source\tkind\tname\tcell\tnet\trole\tprobe_bit\tregister_ref"} {
        close $f
        error "Invalid connection table"
    }
    set clock_net ""
    set capture_clock ""
    set rows {}
    while {[gets $f line] >= 0} {
        if {$line eq ""} { continue }
        set fields [split $line \t]
        if {[llength $fields] != 8} { error "Malformed connection record" }
        lappend rows $fields
        lassign $fields source kind name cell expected role bit ref
        if {$role eq "clock"} {
            set pin [stall_one [get_pins -quiet [list $cell/$name]] "capture clock pin"]
            set clock_net [stall_one [get_nets -quiet -of_objects $pin] "capture clock net"]
            set capture_clock [stall_one [get_clocks -quiet -of_objects $pin] "capture clock"]
            if {$clock_net ne $expected} { error "Clock net changed" }
            stall_clock $pin $capture_clock
        }
    }
    close $f
    if {$clock_net eq ""} { error "Missing capture clock" }
    set checked_cells [dict create]
    set bits [dict create]
    set report [open [file join $out validated.tsv] w]
    puts $report $header
    foreach fields $rows {
        lassign $fields source kind name cell expected role bit ref
        if {![dict exists $checked_cells $cell]} {
            set pin [stall_one [get_pins -quiet [list $cell/clk_i]] "module clock"]
            stall_clock $pin $capture_clock
            dict set checked_cells $cell 1
        }
        switch -- $source {
            pin {
                set obj [stall_one [get_pins -quiet [list $cell/$name]] "source pin $name"]
                set net [stall_one [get_nets -quiet -of_objects $obj] "source net $name"]
            }
            net { set net [stall_one [get_nets -quiet [list $expected]] "source net $name"] }
            register {
                set reg [stall_one [get_cells -quiet [list $cell/$name]] "state register $name"]
                if {[get_property REF_NAME $reg] ne $ref} { error "Register primitive changed: $name" }
                set q [stall_one [get_pins -quiet -of_objects $reg -filter {REF_PIN_NAME == Q}] "register Q"]
                set c [stall_one [get_pins -quiet -of_objects $reg -filter {REF_PIN_NAME == C}] "register C"]
                stall_clock $c $capture_clock
                set net [stall_one [get_nets -quiet -of_objects $q] "register Q net"]
            }
            default { error "Unknown source type: $source" }
        }
        if {$net ne $expected} { error "Source binding changed for $cell/$name: $net != $expected" }
        if {$role eq "data"} {
            if {![string is integer -strict $bit] || $bit < 0} { error "Invalid bit index" }
            if {[dict exists $bits $bit] && [dict get $bits $bit] ne $net} { error "Probe-bit alias conflict" }
            dict set bits $bit $net
        } elseif {$role ne "clock"} { error "Invalid role: $role" }
        puts $report [join $fields \t]
    }
    close $report
    set probe_nets {}
    for {set i 0} {$i < [dict size $bits]} {incr i} {
        if {![dict exists $bits $i]} { error "Noncontiguous probe bit indices" }
        lappend probe_nets [dict get $bits $i]
    }
    if {[llength $probe_nets] == 0 || [llength $probe_nets] > 1024} { error "Invalid observation width" }
    if {[llength [get_debug_cores -quiet i_stall_ila]]} { error "ILA already exists" }
    create_debug_core i_stall_ila ila
    set core [get_debug_cores i_stall_ila]
    set_property C_DATA_DEPTH 1024 $core
    set_property C_INPUT_PIPE_STAGES 1 $core
    set_property C_ADV_TRIGGER true $core
    set_property C_EN_STRG_QUAL true $core
    set_property C_TRIGIN_EN false $core
    set_property C_TRIGOUT_EN false $core
    set_property ALL_PROBE_SAME_MU true $core
    set_property ALL_PROBE_SAME_MU_CNT 2 $core
    set_property port_width [llength $probe_nets] [get_debug_ports i_stall_ila/probe0]
    connect_debug_port i_stall_ila/clk $clock_net
    connect_debug_port i_stall_ila/probe0 $probe_nets
    write_checkpoint [file join $out observation_synth.dcp]
    report_clocks -file [file join $out clocks.rpt]
    set f [open [file join $out prepared.txt] w]
    puts $f "observation_only_prepared_not_implemented"
    puts $f "probe_width=[llength $probe_nets] clock=$capture_clock"
    close $f
    close_project
}
if {![info exists ::stall_ila_test]} {
    if {[catch {
        if {[llength $argv] != 4} { error "Expected package synth-run connections output-directory" }
        stall_prepare {*}$argv
    } message]} {
        puts stderr $::errorInfo
        exit 1
    }
    exit 0
}
