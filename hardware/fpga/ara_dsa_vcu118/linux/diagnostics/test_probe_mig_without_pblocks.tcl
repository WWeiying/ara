set script [file join [file dirname [info script]] probe_mig_without_pblocks.tcl]
proc set_param {args} {}
proc get_param {args} {return {}}
proc open_checkpoint {args} {}
proc get_pblocks {args} {
    if {$::scenario eq "missing"} {return {ara_c1_fifo}}
    return {ara_c1_fifo ara_loader_control ara_c1_fast ara_c2_fifo}
}
proc get_property {prop objects} {return $objects}
proc delete_pblocks {args} {lappend ::calls delete}
proc place_design {} {lappend ::calls place}
rename exit real_exit
proc exit {code} {return -code error -errorcode [list TEST_EXIT $code] "exit $code"}
set argv {candidate.dcp package out}
foreach scenario {healthy missing} {
    set calls {}
    catch {source $script} message options
    set expected [expr {$scenario eq "missing"}]
    if {[dict get $options -errorcode] ne [list TEST_EXIT $expected]} {error "Unexpected test result"}
    if {!$expected && $calls ne {delete place}} {error "Unexpected ablation operations"}
    if {$expected && [llength $calls]} {error "Modified unexpected checkpoint"}
    puts "PASS $scenario"
}
