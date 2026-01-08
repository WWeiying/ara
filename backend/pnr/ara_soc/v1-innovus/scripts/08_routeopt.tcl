set rundate [clock format [clock seconds] -format %Y_%m_%d_%I:%M_%p]
echo "START : 08_routeopt $rundate" >> ../reports/runtime.log

setMultiCpuUsage -localCpu 8

#restoreDesign ../save/route.enc.dat ara_soc 

setExtractRCMode -engine postRoute;
reset_parasitics
extractRC

timeDesign -postRoute -pathReports -drvReports -slackReports -numPaths 50 -prefix postRoute_before_setup_fix -outDir ../reports

setOptMode -fixDrc true -fixFanoutLoad true
optDesign -postRoute

timeDesign -postRoute -pathReports -drvReports -slackReports -numPaths 50 -prefix postRoute_after_setup_fix -outDir ../reports

saveDesign ../save/postRoute.enc


timeDesign -postRoute -hold -pathReports -slackReports -numPaths 50 -prefix postRoute_before_hold_fix -outDir ../reports

setOptMode -fixDrc true -fixFanoutLoad true
optDesign -postRoute -hold
#optDesign -postRoute -hold -incr

timeDesign -postRoute -hold -pathReports -slackReports -numPaths 50 -prefix postRoute_after_hold_fix -outDir ../reports

saveDesign ../save/postRoute_final.enc

set rundate [clock format [clock seconds] -format %Y_%m_%d_%I:%M_%p]
echo "END : 08_routeopt $rundate" >> ../reports/runtime.log


#close
