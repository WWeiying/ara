set APP_LIST                            "fft imatmul"

if {$APP_LIST != "" } {
    foreach APP $APP_LIST {
#        exec make -C /home/wangwy/ara/hardware saif mc=1 app=$APP
        set GUI_SAIF_FILE "/home/wangwy/ara/hardware/saif/$APP.saif"
        if { [info exists GUI_SAIF_FILE] && $GUI_SAIF_FILE != "" } {
            if { [file exists $GUI_SAIF_FILE] } {
                saif_map -start
                read_saif -input $GUI_SAIF_FILE -auto_map_names -instance_name ara_tb/dut/i_ara_soc -verbose
                report_saif -hierarchy -rtl_saif -missing > ../reports/saif_coverage_$APP.rpt

                report_power -hierarchy -verbose > ../reports/power_$APP.rpt
                report_power -hierarchy -levels 2 -verbose  > ../reports/power_level2_$APP.rpt
                report_power -hierarchy -levels 1 -verbose  > ../reports/power_level1_$APP.rpt
                reset_switching_activity
            } else {
                puts "Warning: SAIF file $GUI_SAIF_FILE not found!"
            }
        }
    }
}

