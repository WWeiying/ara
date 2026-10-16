# Preserve actual repaired synthesis logic for independent functional review.
if {[catch {
    if {[llength $argv] != 3} {error "Expected package checkpoint output"}
    lassign $argv package checkpoint out
    if {[file exists $out]} {error "Existing output"}
    file mkdir $out
    set_param board.repoPaths [linsert [get_param board.repoPaths] 0 [file join $package board_files]]
    set_param general.maxThreads 8
    open_checkpoint $checkpoint
    set mmu [get_cells -quiet -hierarchical -filter {REF_NAME =~ cva6_mmu*}]
    if {[llength $mmu] != 1} {error "Missing/ambiguous MMU"}
    write_verilog -cell $mmu -mode funcsim [file join $out mmu.v]
    set f [open [file join $out ppn_fanin.rpt] w]
    set count 0
    foreach pin [get_pins -quiet -of_objects $mmu -filter {DIRECTION == OUT}] {
        if {![string match {*lsu_dtlb_ppn_o*} $pin]} {continue}
        incr count
        puts $f "PPN $pin"
        puts $f [all_fanin -flat -startpoints_only -to $pin]
    }
    close $f
    if {$count != 44} {error "Unexpected PPN output width: $count"}
    close_design
} message]} {
    puts stderr $::errorInfo
    exit 1
}
exit 0
