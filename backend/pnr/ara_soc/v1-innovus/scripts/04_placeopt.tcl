set rundate [clock format [clock seconds] -format %y_%m_%d_%i:%m_%p]
echo "START : 04_placeopt $rundate" >> ../report/runtime.log

setMultiCpuUsage -localCpu 2

restoreDesign ../save/powerplan.enc.dat cortexa7core


#=OCV Analysis
setAnalysisMode -analysisType onChipVariation -cppr both
setDelaycalMode -siAware true

#=Timing Derate
set_analysis_view -setup {cortexa7core_view_cmax} -hold {cortexa7core_view_cmax}
set_timing_derate -delay_corner {cortexa7core_corner_cmax) -early 0.952 -late 1.048 -clock
set_timing_derate -delay_corner {cortexa7core_corner_cmax} -late 1.081 -data
set_timing_derate -delay_corner {cortexa7core_corner_cmin} -early 1 -late 1.151 -clock

set_interactive_constraint_modes [all_constraint_modes -active];
set_clock_uncertainty -setup 0.180 [get_clocks CLKIN]

# Group path
# Reset all existing path groups, including basic path groupsreset_path_group -#? Reset all options set on all path groups.resetpathGroupptions? (CUI :reset_path_group_options)
reset_path_group -all
### get sequentials
set reg [filter_collection [all_registers ] "is_integrated_clock_gating_cell != true"]
set inp [all_inputs]
set out [all_outputs]
set mem [get_cells -q -hier -filter "@is_hierarchical == false && @is_macro_cell == true"]
set ckgating [filter_collection [all_registers] "is_integrated_clock_gating_cell == true"]

set ignore_path_groups [list inp2reg reg2out feedthr]

### create path groups
group_path -name reg2reg -from $reg -to $reg
group_path -name mem2reg -from $mem -to $reg
group_path -name mem2cg -from $mem -to $ckgating
group_path -name reg2mem -from $reg -to $mem
group_path -name mem2mem -from $mem -to $mem
group_path -name reg2cg -from $reg -to $ckgating
group_path -name in2reg -from $inp
group_path -name reg2out -to $out
group_path -name feedthr -from $inp -to $out

### set weight
setPathGroupoptions reg2reg -effortLevel high
setPathGroupoptions mem2reg -effortLevel high
setPathGroupoptions mem2cg  -effortLevel high
setPathGroupoptions reg2mem -effortLevel high
setPathGroupoptions mem2mem -effortLevel high
setPathGroupoptions reg2cg  -effortLevel high
setPathGroupoptions in2reg  -effortLevel low 
setPathGroupoptions reg2out -effortLevel low 
setPathGroupoptions feedthr -effortLevel low 


#setPathGroupoptions? $name? -effortLevel $effort -weight $welght -slackAdjustment $slack_adj
puts "ignore path groups for hold : \{$ignore_path_groups\} ."
setOptMode -ignorePathGroupsforHold $ignore_path_groups



# Place Mode
setPlaceMode -reset
setPlaceMode -place_global_ignore_scan true
setPlaceMode -place_global_reorder_scan false
setPlaceMode -place_global_place_io_pins false
setPlaceMode -place_detail_legalization_lost_gap 2

#global route layer
setRouteMode -earlyGlobalMinRouteLayer 2 -earlyGlobalMaxRouteLayer 9


setDesignMode -process 28

place_opt_design

reportCongestion -overflow

==== Add Tie cell =====
setTieHiLoMode -prefix Tie -maxFanout 8 -cell "TIEHBWP4OP140 TIELBWP40P140"
addTieHiLo

saveDesign ../save/placement.enc


timeDesign -precTs -idealclock -pathReports -drvReports -slackReports -numpaths 50 -prefix precTs -outDir ../report

#setOptMode -fixDrc true -fixFanoutLoad true
#optDesign -precTs -drv
#optDesign -precTs


#timeDesign -precTs -idealclock -pathReports -drvReports -slackReports -numpaths 50 -prefix precTs_opt -outDir ../report

#setOptMode -fixDrc true -fixFanoutLoad true
#optDesign -precTs -incr

#timeDesign -precTs -idealclock -pathReports -drvReports -slackReports -numPaths 50 -prefix precTs_opt_incr -outDir ../report


saveDesign ../save/preCTS.enc

set rundate [clock format [clock seconds] -format %y_%m_%d_%i:%m_%p]
echo "END : 04_placeopt $rundate" >> ../report/runtime.log


close
