#!/usr/bin/env bash

# Build an isolated VCS gate-level simulator for SAIF capture.  This script
# never touches hardware/build, sim, sim_mc, or the RTL synthesis outputs.

set -euo pipefail

if (($# != 4)); then
  echo "usage: $0 <rvv|qbs_akv> <mapped-netlist.v> <app> <run-dir>" >&2
  exit 2
fi

mode=$1
netlist=$2
app=$3
run_dir=$4

case "$mode" in
  rvv) feature_defs=() ;;
  qbs_akv)
    feature_defs=(
      --define ARA_QBS_ENABLE=1
      --define ARA_AKV_ENABLE=1
      --define ARA_AKV_V2_ENABLE=1
    )
    ;;
  *)
    echo "unsupported mode: $mode" >&2
    exit 2
    ;;
esac

repo_root=$(git -C "$(dirname "$0")/../.." rev-parse --show-toplevel)
hw_root=$repo_root/hardware
bender=$hw_root/bender
run_dir=$(realpath -m "$run_dir")
netlist=$(realpath "$netlist")
mkdir -p "$run_dir/sim/incremental_db" "$run_dir/vcd" "$run_dir/logs"

filelist=$run_dir/ara_tb_gate.f
(
  cd "$hw_root"
  "$bender" script verilator --no-default-target \
    -t verilator -t rtl -t cv64a6_imafdcv_sv39 \
    -t tech_cells_generic_include_tc_sram \
    -t tech_cells_generic_include_tc_clk \
    -t exclude_first_pass_decoder -t ara_test -t cva6_test \
    -t notsynthesis -t sram_mc \
    --define NR_LANES=4 --define VLEN=1024 \
    --define ARIANE_ACCELERATOR_PORT=1 \
    --define SAIF --define TARGET_GATESIM \
    "${feature_defs[@]}" \
    --define COMMON_CELLS_ASSERTS_OFF \
    > "$run_dir/bender.raw.f"
)

# The mapped top replaces both RTL wrappers.  Their subordinate RTL files are
# retained because the testbench still imports the package/type definitions;
# only the duplicate top-level implementations must be removed.
grep -vE '/(ara|ara_soc)\.sv([[:space:]]*)$' "$run_dir/bender.raw.f" > "$filelist"
printf '%s\n' "$netlist" >> "$filelist"
if [[ "$mode" == rvv ]]; then
  # The no-QBS mapped netlist flattens generated DRAM instance names to
  # gen_dram_N__i_dram; the gate testbench selects that spelling below.
  printf '%s\n' '+define+RVV_GATESIM' >> "$filelist"
fi

find \
  /home/wangwy/ara/backend/library/mem \
  /home/wangwy/technical_library/tsmc28nm/Memory/tsn28hpcpd127spsram_20120200_180a/AN61001_20180416/tsn28hpcpd127spsram_20120200_180a/TSMCHOME/sram/Compiler/tsn28hpcpd127spsram_20120200_180a/tsn28hpcpd127spsram_20120200_180a \
  /home/wangwy/technical_library/tsmc28nm/Memory/tsn28hpcpuhdspsram_20120200_170a/AN61001_20180125/tsn28hpcpuhdspsram_20120200_170a/TSMCHOME/sram/Compiler/tsn28hpcpuhdspsram_20120200_170a/tsn28hpcpuhdspsram_20120200_170a \
  -type f -name '*tt0p9v25c.v' -print >> "$filelist"

stdcell=/home/wangwy/technical_library/tsmc28nm/logic/tcbn28hpcplusbwp12t40p140_180a/AN61001_20180514/tcbn28hpcplusbwp12t40p140_170a_vlg/TSMCHOME/digital/Front_End/verilog/tcbn28hpcplusbwp12t40p140_170a/tcbn28hpcplusbwp12t40p140.v
stdcell_hvt=/home/wangwy/technical_library/tsmc28nm/logic/tcbn28hpcplusbwp12t40p140hvt_180a/AN61001_20180514/tcbn28hpcplusbwp12t40p140hvt_170a_vlg/TSMCHOME/digital/Front_End/verilog/tcbn28hpcplusbwp12t40p140hvt_170a/tcbn28hpcplusbwp12t40p140hvt.v
stdcell_lvt=/home/wangwy/technical_library/tsmc28nm/logic/tcbn28hpcplusbwp12t40p140lvt_180a/AN61001_20180514/tcbn28hpcplusbwp12t40p140lvt_170a_vlg/TSMCHOME/digital/Front_End/verilog/tcbn28hpcplusbwp12t40p140lvt_170a/tcbn28hpcplusbwp12t40p140lvt.v
stdcell_cg=/home/wangwy/technical_library/tsmc28nm/logic/tcbn28hpcplusbwp12t40p140cg_110c/AN61001_20180123/tcbn28hpcplusbwp12t40p140cg_110a_vlg/TSMCHOME/digital/Front_End/verilog/tcbn28hpcplusbwp12t40p140cg_110a/tcbn28hpcplusbwp12t40p140cg.v

cat > "$run_dir/compile.cmd" <<EOF
cd $run_dir/sim
vcs -full64 -sverilog +v2k -Mlib=./incremental_db -Mupdate -j64 -lca -kdb \\
  -debug_access+all +nospecify +notimingchecks +lint=TFIPC-L +vpi \\
  +lint=PCWM +error+30 -top ara_tb -timescale=1ns/100fs \\
  +define+SIMULATION +define+no_warning +define+TSMC_NO_WARNING \\
  -f $filelist $hw_root/build/work-dpi/elfloader.o \\
  -l $run_dir/logs/compile.vcs.log \\
  -v $stdcell -v $stdcell_hvt -v $stdcell_lvt -v $stdcell_cg
EOF

echo "built filelist: $filelist"
echo "run: cd $run_dir/sim && ./simv -l $run_dir/logs/sim.vcs.log +TESTCASE=$app +PRELOAD=$hw_root/../apps/bin/$app"
cd "$run_dir/sim"
bash "$run_dir/compile.cmd"
