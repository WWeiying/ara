file mkdir ../reports

set rundate [clock format [clock seconds] -format %Y_%m_%d_%I:%M_%p]
echo "START : 01_innovus_import_design $rundate" > ../reports/runtime.log

#========== Environment setting ==========
setMultiCpuUsage -localCpu 8 -cpuAutoAdjust true

source -echo ../scripts/ara_soc.globals
init_design

checkDesign -netlist

saveDesign ../save/init_design.enc


set rundate [clock format [clock seconds] -format %Y_%m_%d_%I:%M_%p]
echo "END : 01_innovus_import_design $rundate" >>../reports/runtime.log

close
