# Reproduce only the known initialization failure and retain its physical state.
proc mig_dump {label} {
    set dir [file join $::out $label]
    file mkdir $dir
    write_xdc -force [file join $dir effective.xdc]
    set f [open [file join $dir properties.rpt] w]
    foreach pb [get_pblocks -quiet] {
        puts $f "PBLOCK $pb"
        puts $f [report_property -return_string $pb]
        puts $f "MEMBERS [get_cells -quiet -of_objects $pb]"
    }
    foreach cell [get_cells -quiet -hier -filter {NAME =~ *gen_channel*.i_dram || NAME =~ *gen_channel*.i_dram/inst}] {
        puts $f "MIG $cell"
        puts $f [report_property -return_string $cell]
    }
    close $f
    set f [open [file join $dir fixed_cells.tsv] w]
    puts $f "cell\tref\tloc\tpblock"
    set cells [get_cells -quiet -hier -filter {IS_PRIMITIVE && IS_LOC_FIXED}]
    foreach c $cells ref [get_property REF_NAME $cells] loc [get_property LOC $cells] {
        puts $f "$c\t$ref\t$loc\t[get_pblocks -quiet -of_objects $c]"
    }
    close $f
    report_drc -file [file join $dir drc.rpt]
}
lassign $argv checkpoint package ::out
file mkdir $::out
set_param general.maxThreads 8
set_param board.repoPaths [linsert [get_param board.repoPaths] 0 [file join $package board_files]]
if {[catch {
    open_checkpoint $checkpoint
    mig_dump before
    set failed [catch {place_design -verbose} message options]
    set f [open [file join $::out placement_result.txt] w]
    puts $f "FAILED=$failed\n$message\n$options"
    close $f
    mig_dump after
    if {!$failed} {write_checkpoint [file join $::out unexpectedly_placed.dcp]}
    close_design
} message]} {puts stderr $::errorInfo; exit 1}
exit 0
