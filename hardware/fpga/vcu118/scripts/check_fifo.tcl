# Isolated native synthesis check. No board project or IP is opened/reset.
if {[catch {
    if {[llength $argv] != 1} { error "Use scripts/check_fifo.ps1" }
    set root [file normalize [file join [file dirname [info script]] ..]]
    set out [file normalize [lindex $argv 0]]
    source [file join $root scripts config.tcl]
    create_project -in_memory -part $fpga_part
    set_param general.maxThreads $max_threads
    set_property include_dirs [list [file join $root rtl common_cells include] \
        [file join $root rtl axi include]] [current_fileset]
    set_property verilog_define SYNTHESIS [current_fileset]
    read_verilog -sv [file join $root rtl axi src axi_pkg.sv]
    foreach name {sync gray_to_binary binary_to_gray spill_register_flushable spill_register cdc_fifo_gray} {
        read_verilog -sv [file join $root rtl common_cells src ${name}.sv]
    }
    read_verilog -sv [file join $root scripts fifo_probe.sv]
    # Do not accept the constant-driver substitution seen before the crash.
    foreach id {{Synth 8-6858} {Synth 8-6859}} {
        set_msg_config -id $id -new_severity ERROR
    }
    synth_design -top fifo_probe -part $fpga_part -mode out_of_context -flatten_hierarchy none
    report_drc -checks {MDRV-1 LUTLP-1} -name fifo_probe -file [file join $out drc.rpt]
    if {[llength [get_drc_violations -name fifo_probe]]} { error "FIFO structural DRC failed" }
    foreach name {i_w i_w_const i_r} width {579 579 525} {
        foreach side {src dst} gen {write read} {
            set regs [get_cells -quiet -hierarchical -filter \
                "NAME =~ $name/i_$side/*gen_fpga_${gen}*select_q_reg* && REF_NAME =~ FD*"]
            set expected [expr {32 * (($width+63)/64)}]
            if {[llength $regs] != $expected} { error "Missing selector replicas: $name/$side" }
        }
    }
    report_utilization -hierarchical -file [file join $out utilization.rpt]
    write_checkpoint [file join $out fifo_probe.dcp]
    close_project
    puts "PASS: FIFO native synthesis and structural DRC; not routed timing signoff"
} message]} {
    puts stderr $::errorInfo
    exit 1
}
exit 0
