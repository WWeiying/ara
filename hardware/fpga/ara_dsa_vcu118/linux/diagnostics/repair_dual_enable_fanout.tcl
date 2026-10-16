# Test the measured terminal-enable fanout bottleneck without changing RTL latency.
proc enable_stage {value} {
    set f [open [file join $::out stage.txt] w]; puts $f $value; close $f
    puts "ENABLE_REPAIR $value"; flush stdout
}
proc enable_eligible {name ref async protected loads failing} {
    if {$async in {1 true TRUE} || $protected in {1 true TRUE}} {return 0}
    if {![regexp {^LUT[1-6]$} $ref] || $loads < 64 || $failing < 32} {return 0}
    return [regexp {^(i_dram_wrapper|gen_ddr2\.i_dram_wrapper_c2)/(gen_ethernet\.(i_eth_shared_ddr|i_eth_loader)/|gen_cdc\.i_axi_cdc_mig/|i_ddr_r_cut/)} $name]
}
proc enable_inventory {dir} {
    file mkdir $dir
    report_timing_summary -report_unconstrained -file [file join $dir timing.rpt]
    report_timing -delay_type max -path_type full_clock_expanded -max_paths 100 -nworst 1 -file [file join $dir setup.rpt]
    report_timing -delay_type min -path_type full_clock_expanded -max_paths 50 -nworst 1 -file [file join $dir hold.rpt]
    set paths [get_timing_paths -quiet -delay_type max -slack_lesser_than 0 -max_paths 30000 -nworst 1]
    if {[llength $paths]>=30000} {error "Failing endpoint inventory truncated"}
    set f [open [file join $dir failing_setup.tsv] w]
    puts $f "slack\tstartpoint\tendpoint"
    foreach p $paths {puts $f "[get_property SLACK $p]\t[get_property STARTPOINT_PIN $p]\t[get_property ENDPOINT_PIN $p]"}
    close $f
    return $paths
}
proc enable_targets {paths} {
    set wanted [dict create]
    foreach p $paths {
        set end [get_property ENDPOINT_PIN $p]
        if {[string match */CE $end]} {dict set wanted $end 1}
    }
    # One design scan, then exact dictionary lookup. Per-endpoint -hier queries
    # made this stage quadratic in endpoint count and full design size.
    set ce_pins [get_pins -quiet -hier -filter {IS_LEAF && REF_PIN_NAME == CE}]
    set pins [dict create]
    foreach pin $ce_pins name [get_property NAME $ce_pins] {
        if {[dict exists $wanted $name]} {dict set pins $name $pin}
    }
    if {[dict size $pins]!=[dict size $wanted]} {error "Missing CE endpoints in bulk index"}
    puts "ENABLE_INDEX wanted=[dict size $wanted] indexed=[dict size $pins]"; flush stdout
    set groups [dict create]
    set objects [dict create]
    dict for {end pin} $pins {
        set net [get_nets -of_objects $pin]
        if {[llength $net]!=1} {error "CE endpoint net missing: $end"}
        set name [get_property NAME $net]
        dict lappend groups $name $end
        dict set objects $name [list $net $pin]
    }
    puts "ENABLE_GROUPS count=[dict size $groups]"; flush stdout
    set targets {}
    set f [open [file join $::out enable_candidates.tsv] w]
    puts $f "net\tdriver\tref\tloads\tfailing_endpoints\tselected"
    dict for {name ends} $groups {
        lassign [dict get $objects $name] net pin
        set count [llength $ends]
        if {$count<32} {continue}
        set segments [get_nets -segments -of_objects $pin]
        set drivers [get_pins -of_objects $segments -filter {IS_LEAF && DIRECTION == OUT}]
        if {[llength $drivers]!=1} {continue}
        set cell [get_cells -of_objects $drivers]
        if {[llength $cell]!=1} {continue}
        set loads [llength [get_pins -of_objects $segments -filter {IS_LEAF && DIRECTION == IN}]]
        set protected [get_property DONT_TOUCH $cell]
        foreach segment $segments {
            if {[get_property DONT_TOUCH $segment] in {1 true TRUE}} {set protected true}
        }
        set ref [get_property REF_NAME $cell]
        set selected [enable_eligible [get_property NAME $cell] $ref [get_property ASYNC_REG $cell] $protected $loads $count]
        puts $f "$name\t[get_property NAME $cell]\t$ref\t$loads\t$count\t$selected"
        flush $f
        puts "ENABLE_CANDIDATE failing=$count loads=$loads selected=$selected net=$name"; flush stdout
        if {$selected} {lappend targets $net}
    }
    close $f
    if {![llength $targets] || [llength $targets]>32} {error "Unexpected eligible enable net count: [llength $targets]; review inventory"}
    return $targets
}
if {![info exists ::enable_library_only]} {
    if {[catch {
        if {[llength $argv]!=4} {error "Expected checkpoint tools package output"}
        lassign $argv checkpoint tools package ::out
        set_param general.maxThreads 8
        set_param board.repoPaths [linsert [get_param board.repoPaths] 0 [file join $package board_files]]
        enable_stage open_preserved_checkpoint
        open_checkpoint $checkpoint
        set ::dual_cdc_preflight_library_only true
        source [file join $tools dual_cdc_preflight.tcl]
        dual_cdc_preflight [file join $::out constraints_before] false
        enable_stage inventory_terminal_enable_paths
        set paths [enable_inventory [file join $::out before]]
        set targets [enable_targets $paths]
        enable_stage replicate_measured_terminal_enables
        phys_opt_design -force_replication_on_nets $targets
        write_checkpoint [file join $::out enables_replicated.dcp]
        enable_inventory [file join $::out replicated]
        enable_stage replace_terminal_enable_cones
        phys_opt_design -placement_opt
        write_checkpoint [file join $::out enables_placed.dcp]
        enable_inventory [file join $::out after]
        dual_cdc_preflight [file join $::out constraints_after] false
        report_bus_skew -file [file join $::out after bus_skew.rpt]
        report_drc -file [file join $::out after drc.rpt]
        enable_stage completed_requires_comparison_no_route
        close_design
    } message]} {puts stderr $::errorInfo; enable_stage failed; exit 1}
    exit 0
}
