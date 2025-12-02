set rundate clock format clock seconds] -format %Y_%m_%d_%I:%M_%p]
echo "START : 03_powerplan $rundate" >> ../report/runtime.log

setMultiCpuUsage -localCpu 2

restoreDesign ../save/floorplan.enc.dat cortexa7core

clearGlobalNets

globalNetconnect VDD -type pgpin -pin {VDD} -inst *
globalNetConnect VDD -type tiehi -pin {VDD} -inst *
globalNetConnect VDD -type net -net VDD
globalNetConnect VSS -type pgpin -pin {VSS} -inst *
globalNetConnect VSS -type tielo -pin {VSS} -inst *
globalNetConnect VSS -type net -net VSS

#setViaGenMode -optimize cross_via true

#add_via_definition -name via12_usrdefine -via_rule VIAGEN12 -row_col {1 10}
#add_via_definition -name via23_usrdefine -via_rule VIAGEN23 -row_col {1 10}
#add_via_definition -name via34_usrdefine -via_rule VIAGEN34 -row_col {1 10}
#add_via_definition -name via45_usrdefine -via_rule VIAGEN45 -row_col {1 10}
#add_via_definition -name via56_usrdefine -via_rule VIAGEN56 -row_col {1 10}
#add_via_definition -name via67_usrdefine -via_rule VIAGEN67 -row_col {1 10}
#add_via_definition -name via78_usrdefine -via_rule VIAGEN78 -row_col {1 10}
#add_via_definition -name via89_usrdefine -via_rule VIAGEN89 -row_col {1 10}
#setviaGenwode -viarule_preferene {via12_usrdefine via23_usrdefine via34_urdefine via45_usrdefine via56_usrdefine via67_usrdefine via78_usrdefine via89_usrdefine}

#===== Create Stripe =====
#editDelete -type Special -shape STRIPE
addstripe -nets {VSS VDD} \
        -layer M8 \
        -direction vertical \
        -width 6 \
        -spacing 2 \
        -set_to_set_distance 30 \
        -start_from_left \
        -start_offset 1 \
        -uda power_stripe_M8

addstripe -nets {VSS VDD} \
        -layer M9 \
        -direction horizontal \
        -width 6 \
        -spacing 2 \
        -set_to_set_distance 30 \
        -start_from_bottom \
        -start_offset 1 \
        -uda power_stripe_M9


sroute -connect { corePin } \
        -layerChangeRange { M1(1) M8(8) } \
        -corePinTarget {none} \
        -allowJogging 1 \
        -crossoverViaLayerRange { M1(1) M8(8) } \
        -nets { VDD VSS} \
        -allowLayerChange 1 \
        -targetViaLayerRange { M1(1) M8(8) } \
        -uda power_rail_M1


verifyconnectivity -type special -noAntenna -noWeakConnect -noUnroutedNet -error 1000 -warning 50

verifyConnectivity -noAntenna -noSoftPGconnect -noUnroutedNet -error 1000000 -net VDD

verifyConnectivity -noAntenna -noSoftPGConnect -noUnroutedNet -error 1000000 -net VSS


verify_PG_short -no_routing_blkg




saveDesign ../save/powerplan.enc

set rundate [clock format [clock seconds] -format %Y_%m_%d_%I:%M_%p]
echo "END :03_powerplan $rundate" >> ../report/runtime.log


close
