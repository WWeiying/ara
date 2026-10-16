# Read-only expansion of the scalar side implicated by the first ILA capture.
if {[catch {
    if {[llength $argv] ni {3 4}} { error "Expected package checkpoint output ?expanded?" }
    lassign $argv package checkpoint out expanded
    if {$expanded ni {{} expanded}} { error "Unknown inventory mode" }
    if {[file exists $out]} { error "Existing output" }
    file mkdir $out
    set_param board.repoPaths [linsert [get_param board.repoPaths] 0 [file join $package board_files]]
    set_param general.maxThreads 8
    open_checkpoint $checkpoint
    set base {i_cheshire_soc/gen_cva6_cores[0].i_core_cva6/ex_stage_i/lsu_i}
    set pins [open [file join $out pins.tsv] w]
    set regs [open [file join $out registers.tsv] w]
    set nets [open [file join $out nets.tsv] w]
    puts $pins "kind\tcell\tpin\tdirection\tnet"
    puts $regs "kind\tcell\tregister\tref\tq_net\tclock_net\tinit"
    puts $nets "kind\tcell\tnet"
    set selected [dict create lsu $base load $base/i_load_unit store $base/i_store_unit bypass $base/lsu_bypass_i]
    if {$expanded eq "expanded"} {
        set root {i_cheshire_soc/gen_cva6_cores[0].i_core_cva6/}
        set modules [open [file join $out modules.tsv] w]
        puts $modules "kind\tcell\tref"
        foreach candidate [get_cells -quiet -hierarchical -filter {IS_PRIMITIVE == 0}] {
            if {[string first $root $candidate] != 0} { continue }
            set ref [get_property REF_NAME $candidate]
            if {![regexp {^(wt_dcache|cva6_mmu|cva6_ptw|mmu|ptw|store_buffer)} $ref]} { continue }
            set kind "extra_[dict size $selected]"
            dict set selected $kind $candidate
            puts $modules [join [list $kind $candidate $ref] \t]
        }
        close $modules
    }
    dict for {kind path} $selected {
        set cell [get_cells -quiet [list $path]]
        if {[llength $cell] != 1} { error "Missing exact scalar cell: $kind" }
        foreach pin [get_pins -quiet -of_objects $cell] {
            puts $pins [join [list $kind $cell $pin [get_property DIRECTION $pin] [get_nets -quiet -of_objects $pin]] \t]
        }
        foreach net [get_nets -quiet ${cell}/*] {
            puts $nets [join [list $kind $cell $net] \t]
        }
        foreach child [get_cells -quiet ${cell}/* -filter {REF_NAME =~ FD*}] {
            set ref [get_property REF_NAME $child]
            if {![string match FD* $ref]} { continue }
            set q [get_pins -quiet -of_objects $child -filter {REF_PIN_NAME == Q}]
            set c [get_pins -quiet -of_objects $child -filter {REF_PIN_NAME == C}]
            if {[llength $q] != 1 || [llength $c] != 1} { continue }
            puts $regs [join [list $kind $cell $child $ref [get_nets -quiet -of_objects $q] [get_nets -quiet -of_objects $c] [get_property INIT $child]] \t]
        }
        if {$kind in {load store bypass}} { write_verilog -cell $cell -mode funcsim [file join $out $kind.v] }
        flush $pins
        flush $regs
        flush $nets
        puts "SCALAR_INVENTORY $kind complete"
    }
    close $pins
    close $regs
    close $nets
    close_design
    set f [open [file join $out complete.txt] w]
    puts $f "read_only_scalar_inventory_not_root_cause"
    close $f
} message]} {
    puts stderr $::errorInfo
    exit 1
}
exit 0
