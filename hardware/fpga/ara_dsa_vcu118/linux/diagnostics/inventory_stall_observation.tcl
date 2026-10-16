# Read-only checkpoint inventory; no board access or design modification.
if {[llength $argv] != 2} { error "Expected checkpoint output-directory" }
lassign $argv checkpoint out
if {[file exists $out]} { error "Output exists: $out" }
file mkdir $out
open_checkpoint $checkpoint
set f [open [file join $out inventory.tsv] w]
puts $f "kind\tcell\tref\tobject\tdirection\tnet"
set candidates [open [file join $out state_nets.tsv] w]
puts $candidates "kind\tcell\tnet"
set counts [open [file join $out counts.tsv] w]
puts $counts "kind\tcells\tpins\tstate_nets"
set registers [open [file join $out registers.tsv] w]
puts $registers "kind\tcell\tregister\tref\tnet\tclock\tinit"
foreach kind {acc_dispatcher ara_dispatcher ara_sequencer addrgen vldu load_store_unit lsu_bypass ara_fpga_debug vlsu} {
    set cells [get_cells -quiet -hierarchical -filter "ORIG_REF_NAME == $kind || REF_NAME == $kind"]
    if {[llength $cells] != 1} { error "Expected one $kind, found [llength $cells]" }
    set npins 0
    set nnets 0
    foreach cell $cells {
        set ref [get_property REF_NAME $cell]
        foreach pin [get_pins -quiet -of_objects $cell] {
            set nets [get_nets -quiet -of_objects $pin]
            puts $f "$kind\t$cell\t$ref\t$pin\t[get_property DIRECTION $pin]\t$nets"
            incr npins
        }
        # Only local nets: child hierarchy can contain large data memories.
        foreach net [get_nets -quiet ${cell}/*] {
            set name [get_property NAME $net]
            set leaf [string range $name [expr {[string length $cell]+1}] end]
            if {[string first / $leaf] >= 0} { continue }
            if {[regexp -nocase {state|running|retired|hazard|pending|valid|ready|ack|gnt|count|cnt|pointer|ptr|exception|complete|idle|trans_id|vstart|csr_vl|csr_vtype} $leaf]} {
                puts $candidates "$kind\t$cell\t$name"
                incr nnets
            }
        }
        # Record Q, not similarly named combinational D-input helper nets.
        foreach reg [get_cells -quiet ${cell}/* -filter {REF_NAME =~ FD*}] {
            set q [get_pins -quiet -of_objects $reg -filter {REF_PIN_NAME == Q}]
            set c [get_pins -quiet -of_objects $reg -filter {REF_PIN_NAME == C}]
            if {[llength $q] != 1 || [llength $c] != 1} { continue }
            puts $registers "$kind\t$cell\t$reg\t[get_property REF_NAME $reg]\t[get_nets -quiet -of_objects $q]\t[get_clocks -quiet -of_objects $c]\t[get_property INIT $reg]"
        }
        if {$kind in {ara_sequencer addrgen vldu acc_dispatcher}} {
            write_verilog -cell $cell -mode funcsim [file join $out ${kind}.v]
        }
    }
    puts $counts "$kind\t[llength $cells]\t$npins\t$nnets"
    puts "INVENTORY $kind CELLS=[llength $cells] PINS=$npins STATE_NETS=$nnets"
    flush $f
    flush $candidates
    flush $counts
    flush $registers
}
close $f
close $candidates
close $counts
close $registers
report_clocks -file [file join $out clocks.rpt]
set f [open [file join $out complete.txt] w]
puts $f "read_only_inventory_complete"
close $f
close_design
exit
