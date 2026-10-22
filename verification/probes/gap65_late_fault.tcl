# Read-only, case-specific observer. Tcl 8.4 syntax; no HDL writes or callbacks.
# APIs: installed VCS UCLI guide, Breakpoint / Simulation Advancing / get.
if {[catch {
    set root ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_qbs_engine
    set ce $root.i_compute_engine
    set signals [list ara_tb.clk ara_tb.rst_n ara_tb.wall_cycle \
        $ce.state_q $ce.state_d $ce.fault_i $ce.m_q $ce.n_q \
        $ce.k_blocks_q $ce.row_base_q $ce.integer_busy \
        $ce.i_profile_engine_int.compute_active_q $ce.i_profile_engine_int.issue_active_q \
        $root.commit_start_valid $root.ldu_result_req_o]
    set fd [open gap65-observer.tsv {WRONLY CREAT EXCL}]
    puts $fd "phase\tclk\trst_n\tcycle\tstate\tnext_state\tfault\tm\tn\tk_blocks\trow_base\tinteger_busy\tcompute_active\tissue_active\tcommit\tvrf_req"
    flush $fd
    set bp [stop -negedge ara_tb.clk -condition \
        {ara_tb.rst_n == 1 && ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_qbs_engine.i_compute_engine.fault_i == 1}]
    run 100000 ns
    stop -delete $bp
    # Step away from the clock event before reading settled combinational data.
    run 1 ps
    foreach phase {before after} {
        set values [list $phase]
        foreach signal $signals {lappend values [get $signal -radix decimal]}
        puts $fd [join $values "\t"]
        flush $fd
        if {$phase eq "before"} {run 1 ns}
    }
    puts $fd "END"
    close $fd
    run
} error]} {
    puts "FAILED: gap65 observer $error"
}
quit
