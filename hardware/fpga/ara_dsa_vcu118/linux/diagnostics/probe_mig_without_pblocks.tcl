# Discriminating initialization test: remove only the four user Pblocks.
lassign $argv checkpoint package out
set_param general.maxThreads 8
set_param board.repoPaths [linsert [get_param board.repoPaths] 0 [file join $package board_files]]
if {[catch {
    open_checkpoint $checkpoint
    set pblocks [get_pblocks -quiet ara_*]
    if {[lsort [get_property NAME $pblocks]] ne {ara_c1_fast ara_c1_fifo ara_c2_fifo ara_loader_control}} {
        error "Unexpected Pblock inventory"
    }
    delete_pblocks $pblocks
    puts "MIG_PROBE removed_only_user_pblocks; MDM clock region and all timing constraints retained"
    flush stdout
    place_design
} message]} {puts stderr $::errorInfo; exit 1}
exit 0
