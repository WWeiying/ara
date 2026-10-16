# Read-only extraction from the checkpoint that produced the failing bitstream.
if {[llength $argv] ni {2 3}} { error "Expected checkpoint output-directory ?kind-list?" }
lassign $argv checkpoint output kinds
if {[llength $argv] == 2} { set kinds {valu ara_sequencer lane_sequencer} }
foreach kind $kinds {
    if {$kind ni {valu ara_sequencer lane_sequencer vldu vstu addrgen}} {
        error "Unsupported extraction kind: $kind"
    }
}
if {[file exists $output]} { error "Output already exists: $output" }
file mkdir $output
open_checkpoint $checkpoint
set report [open [file join $output inventory.tsv] w]
puts $report "kind\tcell\tref\tfile"
foreach kind $kinds {
    set cells [get_cells -hierarchical -filter "ORIG_REF_NAME == $kind || REF_NAME == $kind"]
    if {![llength $cells]} { error "No $kind cells found" }
    set index 0
    foreach cell $cells {
        set path [file join $output ${kind}_${index}.v]
        puts $report "$kind\t$cell\t[get_property REF_NAME $cell]\t$path"
        flush $report
        write_verilog -cell $cell -mode funcsim -include_xilinx_libs $path
        incr index
    }
}
close $report
close_design
