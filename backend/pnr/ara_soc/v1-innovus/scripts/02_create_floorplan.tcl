set rundate [clock format [clock seconds] -format %Y_%m_%d_%I:%M_%p]
echo "START :02_create_floorplan $rundate" >> ../report/runtime.log

setMultiCpuUsage -localCpu 2

restoreDesign ../save/init_design.enc.dat cortexa7core


set dontuse_cell [list DEL* \
                       BHD* \
                       CK*  \
                       DCCK*\
                       *D24BWP* \
                       *D20BWP* \
                       *D0BWP* \
                       G* \
                       INVD21* \
                 ]

foreach lib_cell $dontuse_cell {
        foreach libraryname [dbget head.libcells.name $lib_cell] {
        echo "setDontUse $libraryname true"
        setDontUse $libraryname true
        }



#====== floorplan setting ========
set CORE_W 1004.8
set CORE_H 702.9

set CORE_to_DIE "2 2 2 2.7"

floorPlan -site core -S "$CORE_W $CORE_H $CORE_to_DIE"

defIn ../../input/floorplan_macro.def

addHaloToBlock {8 8 8 8} -allBlock

# endcap cell

set endcap_right  "BOUNDARY_LEFTBWP4OP140"
set endcap_left   "BOUNDARY_RIGHTBWP40P140"
set endcap_top    "BOUNDARY_LEFTBWP40P140 FILL2BWP40P140"
set endcap_bottom "BOUNDARY_LEFTBWP40P140 FILL2BWP40P140"

setEndCapMode -reset
setEndcapMode -leftEdge $endcap_left -rightEdge $endcap_right -topEdge $endcap_top -bottomEdge $endcap_bottom -prefix ENDCAP

addEndcap
# tap cell

addWellTap -cell TAPCELLBWP40P140 -cellInterval 60 -prefix WELLTAP

saveDesign ../save/floorplan.enc

set rundate [clock format [clock seconds] -format %Y_%m_%d_%I:%M_%p]
echo "END : 02_create_floorplan $rundate" >> ../report/runtime.log


close
