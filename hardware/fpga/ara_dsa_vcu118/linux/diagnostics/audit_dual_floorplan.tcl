# Read-only physical census. No placement, netlist edits, or board access.
proc floor_stage {name} {
    set f [open [file join $::out stage.txt] w]; puts $f $name; close $f
    puts "FLOOR_AUDIT $name"; flush stdout
}
proc floor_properties {object names} {
    set supported [list_property $object]
    set row {}
    foreach name $names {
        if {$name in $supported} {lappend row [get_property $name $object]} else {lappend row {}}
    }
    return $row
}
if {[catch {
    if {[llength $argv]!=3} {error "Expected checkpoint package output"}
    lassign $argv checkpoint package ::out
    set_param general.maxThreads 8
    set_param board.repoPaths [linsert [get_param board.repoPaths] 0 [file join $package board_files]]
    floor_stage open_checkpoint
    open_checkpoint $checkpoint
    floor_stage clocks_and_region_utilization
    report_clock_utilization -file [file join $::out clock_utilization.rpt]
    report_clocks -file [file join $::out clocks.rpt]
    report_utilization -slr -file [file join $::out slr_utilization.rpt]
    report_utilization -hierarchical -hierarchical_depth 7 -file [file join $::out hierarchy_utilization.rpt]
    floor_stage site_region_index
    set regions [dict create]
    set f [open [file join $::out region_capacity.tsv] w]
    puts $f "region\tslr\tsite_type\tsites"
    foreach cr [get_clock_regions] {
        set slr [get_slrs -of_objects $cr]
        set sites [get_sites -of_objects $cr]
        set counts [dict create]
        foreach site $sites type [get_property SITE_TYPE $sites] {
            dict set regions $site [list $cr $slr]
            dict incr counts $type
        }
        dict for {type count} $counts {puts $f "$cr\t$slr\t$type\t$count"}
    }
    close $f
    floor_stage bulk_primitive_census
    set f [open [file join $::out cells.tsv] w]
    puts $f "name\tref\tloc\tregion\tslr"
    set cells [get_cells -quiet -hier -filter {IS_PRIMITIVE}]
    # Batch properties; never scan the entire hierarchy for each endpoint.
    for {set i 0} {$i<[llength $cells]} {incr i 4096} {
        set batch [lrange $cells $i [expr {$i+4095}]]
        set names [get_property NAME $batch]
        set refs [get_property REF_NAME $batch]
        set locs [get_property LOC $batch]
        foreach values [list $names $refs $locs] {
            if {[llength $values]!=[llength $batch]} {error "Bulk property length mismatch"}
        }
        foreach name $names ref $refs loc $locs {
            set cr {}; set slr {}
            if {[dict exists $regions $loc]} {lassign [dict get $regions $loc] cr slr}
            puts $f "$name\t$ref\t$loc\t$cr\t$slr"
        }
        if {$i%65536==0} {puts "CENSUS $i/[llength $cells]"; flush stdout; flush $f}
    }
    close $f
    unset cells regions
    floor_stage clock_buffer_properties
    set f [open [file join $::out clock_buffers.tsv] w]
    puts $f "cell\tref\tloc\tclock_region\tout_net\tclock_root\tuser_clock_root\tclock_delay_group"
    foreach cell [get_cells -quiet -hier -filter {IS_PRIMITIVE && REF_NAME =~ BUFG*}] {
        set output [get_pins -of_objects $cell -filter {DIRECTION == OUT}]
        set nets [get_nets -of_objects $output]
        foreach net $nets {
            puts $f [join [concat [floor_properties $cell {NAME REF_NAME LOC CLOCK_REGION}] \
                [floor_properties $net {NAME CLOCK_ROOT USER_CLOCK_ROOT CLOCK_DELAY_GROUP}]] "\t"]
        }
    }
    close $f
    floor_stage existing_floorplan_constraints
    set f [open [file join $::out slr_constraints.tsv] w]
    puts $f "cell\tassignment"
    foreach cell [get_cells -quiet -hier -filter {USER_SLR_ASSIGNMENT != ""}] {
        puts $f "$cell\t[get_property USER_SLR_ASSIGNMENT $cell]"
    }
    close $f
    set f [open [file join $::out pblocks.rpt] w]
    foreach pb [get_pblocks -quiet] {
        puts $f [report_property -return_string $pb]
        puts $f "CELLS [get_cells -of_objects $pb]"
    }
    close $f
    floor_stage full_path_inventory
    foreach kind {max min} label {setup hold} {
        set paths [get_timing_paths -quiet -delay_type $kind -slack_lesser_than 0 -max_paths 30000 -nworst 1]
        if {[llength $paths]>=30000} {error "Truncated $label inventory"}
        set f [open [file join $::out ${label}_paths.tsv] w]
        set fields {SLACK STARTPOINT_PIN ENDPOINT_PIN STARTPOINT_CLOCK ENDPOINT_CLOCK LOGIC_LEVELS DATAPATH_DELAY REQUIREMENT}
        puts $f [join $fields "\t"]
        if {[llength $paths]} {
            set supported [list_property [lindex $paths 0]]
            foreach path $paths {
                set row {}
                foreach field $fields {
                    if {$field in $supported} {lappend row [get_property $field $path]} else {lappend row {}}
                }
                puts $f [join $row "\t"]
            }
        }
        close $f
        report_timing -delay_type $kind -max_paths 50 -nworst 1 -path_type full_clock_expanded \
            -input_pins -file [file join $::out ${label}_expanded.rpt]
    }
    floor_stage congestion_analysis
    report_design_analysis -congestion -file [file join $::out congestion.rpt]
    floor_stage complete_read_only_not_signoff
    close_design
} message]} {puts stderr $::errorInfo; floor_stage failed; exit 1}
exit 0
