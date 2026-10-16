# Check effective timing exceptions before physical work, not just source text.
proc dual_cdc_preflight {out {require_marker true}} {
    if {$require_marker && (![info exists ::ara_cdc::application_complete] ||
                           !$::ara_cdc::application_complete)} {
        error "CDC constraints did not finish loading; implementation forbidden"
    }
    file mkdir $out
    set vio [get_clocks -quiet -of_objects [get_pins -quiet i_vio/clk]]
    set hub [get_clocks -quiet -of_objects [get_pins -quiet dbg_hub/clk]]
    if {[llength $vio] != 1 || $hub ne $vio || abs([get_property PERIOD $vio]-20.0)>0.001} {
        error "Debug hub is not connected to the same 50 MHz clock as VIO: $hub / $vio"
    }
    set checked 0
    foreach wrapper {i_dram_wrapper gen_ddr2.i_dram_wrapper_c2} label {c1 c2} {
        if {[llength [get_pins -quiet $wrapper/soc_clk_i]] != 1} {error "Missing DDR: $wrapper"}
        foreach channel {aw w ar b r} {
            if {$channel in {aw w ar}} {set source src; set dest dst} else {set source dst; set dest src}
            set root $wrapper/gen_cdc.i_axi_cdc_mig
            set src $root/i_axi_cdc_$source/i_cdc_fifo_gray_src_$channel
            set dst $root/i_axi_cdc_$dest/i_cdc_fifo_gray_dst_$channel
            set launch [get_clocks -quiet -of_objects [get_pins $src/src_clk_i]]
            set capture [get_clocks -quiet -of_objects [get_pins $dst/dst_clk_i]]
            set spill [get_cells -quiet -hierarchical -filter \
                "NAME =~ $dst/i_spill_register/*gen_spill_reg.a_data_q_reg* && REF_NAME =~ FD*"]
            set data [get_pins -quiet -of_objects $spill -filter {REF_PIN_NAME == D}]
            foreach half [list $dst $src] name {forward reverse} {
                set regs [get_cells -quiet -hierarchical -filter "NAME =~ $half/gen_sync* && REF_NAME =~ FD*"]
                set first [filter -regexp $regs {NAME =~ .*/reg_q_reg\[0\]$}]
                if {[llength $regs]!=12 || [llength $first]!=6} {error "Gray synchronizer inventory changed: $half"}
                set $name [get_pins -quiet -of_objects $first -filter {REF_PIN_NAME == D}]
            }
            foreach pins [list $forward $reverse $data] clock [list $launch $capture $launch] kind {forward reverse data} {
                if {![llength $pins] || [llength $clock]!=1} {error "Missing CDC endpoints/clock"}
                set report [report_timing -from $clock -to $pins -delay_type max -max_paths 1 \
                    -return_string -file [file join $out ${label}_${channel}_${kind}.rpt]]
                if {![regexp {Timing Exception:\s+MaxDelay Path[^\r\n]*-datapath_only} $report] ||
                    ![regexp {Requirement:\s+3\.000ns} $report]} {
                    error "Effective 3 ns datapath-only exception missing: $label/$channel/$kind"
                }
                incr checked
            }
        }
    }
    if {$checked!=30} {error "Incomplete dual-DDR exception check"}
    set f [open [file join $out completed.txt] w]
    puts $f "30 effective DDR exceptions; debug hub on 50 MHz. Not routed timing signoff."
    close $f
    puts "DUAL_CDC_PREFLIGHT PASS: 30 effective exception groups and debug clock"
}
if {![info exists ::dual_cdc_preflight_library_only]} {
    dual_cdc_preflight [file join [pwd] constraint_preflight]
}
