set rundate [clock format [clock seconds] -format %Y_%m_%d_%I:%M_%p]
echo "START : 07_route $rundate" >> ../reports/runtime.log

setMultiCpuUsage -localCpu 8

#restoreDesign ../save/postCTS.enc.dat ara_soc

setNanoRouteMode -quiet -routeTopRoutingLayer 9
setNanoRouteMode -quiet -routeBottomRoutingLayer 2


setNanoRouteMode -quiet -routeWithTimingDriven true
setNanoRouteMode -quiet -routeWithSiDriven true



setNanoRouteMode -quiet -drouteFixAntenna true
setNanoRouteMode -quiet -routeInsertAntennaDiode true
setNanoRouteMode -quiet -routeAntennaCellName "ANTENNABWP12T40P140"


setNanoRouteMode -quiet -drouteUseMultiCutViaEffort medium
setNanoRouteMode -quiet -drouteMinSlackForWireOptimization 0.1

setNanoRouteMode -quiet -drouteEndIteration default

routeDesign -globalDetail

saveDesign ../save/route.enc

set rundate [clock format [clock seconds] -format %Y_%m_%d_%I:%M_%p]
echo "END : 07_route $rundate" >> ../reports/runtime.log


#close
