# Immediate observation of an already programmed diagnostic image. No CPU reset,
# memory transactions, configuration readback capture, or programming commands.
namespace eval stall_capture {}
proc stall_capture::one {objects label} {
    if {[llength $objects] != 1} { error "Expected one $label, got [llength $objects]" }
    return [lindex $objects 0]
}
proc stall_capture::run {ltx out {width 579}} {
    if {![string is integer -strict $width] || $width < 1 || $width > 1024} {
        error "Invalid expected probe width"
    }
    if {![file isfile $ltx] || [file exists $out]} { error "Missing LTX or existing output" }
    file mkdir $out
    set manager 0
    set connected 0
    set opened 0
    set code [catch {
        open_hw_manager
        set manager 1
        connect_hw_server -url localhost:3121
        set connected 1
        set candidates {}
        foreach candidate [get_hw_targets] {
            if {[string match */xilinx_tcf/Digilent/210308A3B79F $candidate]} {
                lappend candidates $candidate
            }
        }
        set target [one $candidates "authorized JTAG target"]
        open_hw_target $target
        set opened 1
        set device [one [get_hw_devices -of_objects $target -filter {PART =~ xcvu9p*}] "VCU118 device"]
        current_hw_device $device
        set_property PROBES.FILE $ltx $device
        refresh_hw_device $device
        set ila [one [get_hw_ilas -of_objects $device -filter {CELL_NAME == i_stall_ila}] "stall ILA"]
        set f [open [file join $out core_properties.txt] w]
        puts $f [report_property -return_string $ila]
        close $f
        # This maps every physical probe bit explicitly, preserving alias decoding.
        create_hw_probe -map [format {probe0[%d:0]} [expr {$width-1}]] \
            [format {stall_raw[%d:0]} [expr {$width-1}]] $ila
        set_property CONTROL.DATA_DEPTH 1024 $ila
        set_property CONTROL.TRIGGER_POSITION 0 $ila
        set_property CONTROL.TRIGGER_MODE BASIC_ONLY $ila
        set_property CONTROL.CAPTURE_MODE ALWAYS $ila
        run_hw_ila -trigger_now $ila
        wait_on_hw_ila -timeout 0.5 $ila
        set data [upload_hw_ila_data $ila]
        write_hw_ila_data [file join $out capture.ila] $data
        write_hw_ila_data -csv_file [file join $out capture.csv] $data
        write_hw_ila_data -vcd_file [file join $out capture.vcd] $data
        set f [open [file join $out complete.txt] w]
        puts $f "captured_not_diagnosed target=$target core=$ila"
        puts $f "expected_width=$width depth=1024 input_pipeline=1"
        close $f
    } message options]
    if {$opened} { catch {close_hw_target $target} }
    if {$connected} { catch {disconnect_hw_server} }
    if {$manager} { catch {close_hw_manager} }
    if {$code} { return -options $options $message }
}
if {![info exists ::stall_capture_test]} {
    if {[catch {
        if {[llength $argv] ni {2 3}} { error "Expected matched observation LTX, new output directory, optional width" }
        stall_capture::run {*}$argv
    } message]} {
        puts stderr $::errorInfo
        exit 1
    }
    exit 0
}
