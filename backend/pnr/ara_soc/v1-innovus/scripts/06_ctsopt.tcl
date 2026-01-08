set rundate [clock format [clock seconds] -format %Y_%m_%d_%I:%M_%p]
echo "START : 06_ctsopt $rundate" >> ../reports/runtime.log

setMultiCpuUsage -localCpu 8

#restoreDesign ../save/CTS.enc.dat ara_soc

setExtractRCMode -engine preRoute;

#Timing Derate
#set_analysis_view -setup {cortexa7core_view_cmax} -hold {cortexa7core_view_cmin}
set_analysis_view -setup [list func_tt_rctypical_25c] \
                  -hold [list func_tt_rctypical_25c]

set_interactive_constraint_modes [all_constraint_modes -active];
set_propagated_clock [all_clocks]


set_clock_uncertainty -setup 0.09 [all_clocks]
set_clock_uncertainty -hold 0.05 [all_clocks]

timeDesign -postCTS -pathReports -drvReports -slackReports -numPaths 50 -prefix postCTS_opt_before_setup_fix -outDir ../reports

setOptMode -fixDrc true -fixFanoutLoad true
optDesign -postCTS

timeDesign -postCTS -pathReports -drvReports -slackReports -numPaths 50 -prefix postCTS_opt_after_setup_fix -outDir ../reports


timeDesign -postCTS -hold -pathReports -slackReports -numPaths 50 -prefix postCTS_opt_before_hold_fix -outDir ../reports

setOptMode -fixDrc true -fixFanoutLoad true
optDesign -postCTS -hold

timeDesign -postCTS -hold -pathReports -slackReports -numPaths 50 -prefix postCTS_opt_after_hold_fix -outDir ../reports

checkFPlan -reportUtil

set cts_inv_cells            [list CKND2BWP12T40P140 CKND3BWP12T40P140 CKND4BWP12T40P140 CKND6BWP12T40P140 CKND8BWP12T40P140 CKND12BWP12T40P140 CKND16BWP12T40P140 ] 
set cts_gate_cells        [list CKLNQD3BWP12T40P140 CKLNQD4BWP12T40P140 CKLNQD6BWP12T40P140 CKLNQD8BWP12T40P140 CKLNQD12BWP12T40P140 CKLNQD16BWP12T40P140] 

foreach libraryname $cts_inv_cells {
  echo "setDontUse $libraryname true"
  setDontUse $libraryname true
}

foreach libraryname $cts_gate_cells {
  echo "setDontUse $libraryname true"
  setDontUse $libraryname true
}

saveDesign ../save/postCTS.enc

set rundate [clock format [clock seconds] -format %Y_%m_%d_%I:%M_%p]
echo "END : 06_ctsopt $rundate" >> ../reports/runtime.log

#close
