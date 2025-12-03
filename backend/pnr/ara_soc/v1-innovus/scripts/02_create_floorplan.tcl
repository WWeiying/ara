set rundate [clock format [clock seconds] -format %Y_%m_%d_%I:%M_%p]
echo "START :02_create_floorplan $rundate" >> ../report/runtime.log

setMultiCpuUsage -localCpu 8 -cpuAutoAdjust true

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
}


#====== floorplan setting ========
set CORE_W 2665
set CORE_H 2200

set CORE_to_DIE "1 1 1 1"

floorPlan -site core12T -S "$CORE_W $CORE_H $CORE_to_DIE"

defIn ../../input/floorplan_macro.def

addHaloToBlock {8 8 8 8} -allBlock

# endcap cell

set endcap_right  "BOUNDARY_LEFTBWP12T40P140"
set endcap_left   "BOUNDARY_RIGHTBWP12T40P140"
set endcap_top    "BOUNDARY_LEFTBWP12T40P140 FILL2BWP12T40P140"
set endcap_bottom "BOUNDARY_LEFTBWP12T40P140 FILL2BWP12T40P140"

setEndCapMode -reset
setEndCapMode -leftEdge $endcap_left -rightEdge $endcap_right -topEdge $endcap_top -bottomEdge $endcap_bottom -prefix ENDCAP

addEndCap
# tap cell

addWellTap -cell TAPCELLBWP12T40P140 -cellInterval 60 -prefix WELLTAP

saveDesign ../save/floorplan.enc

set rundate [clock format [clock seconds] -format %Y_%m_%d_%I:%M_%p]
echo "END : 02_create_floorplan $rundate" >> ../report/runtime.log


close
