#!/usr/bin/env bash
# AVL sweep for HDV 1D streaming kernels.
#
# Each kernel's application vector length (AVL) is driven by the unified `avl`
# Makefile knob (see hardware/Makefile).  Data arrays are static, so AVL is
# capped per kernel by its array size (MAXAVL below); regenerate the data via
# the app gen scripts (apps/<orig>/script/gen_data.py) to raise a cap.
#
# Usage:
#   ./avl_sweep.sh                          # all wired kernels, default AVL list
#   ./avl_sweep.sh vsdot_hdv                # one kernel, default AVL list
#   ./avl_sweep.sh vsdot_hdv "32 64 128"    # one kernel, custom AVL list
#   ./avl_sweep.sh all "16 64 256 1024"     # all kernels, custom AVL list
#
# Output: avl_sweep_out/<kernel>.csv (per kernel) + avl_sweep_out/all.csv
# (combined) + a live console table.

set -uo pipefail
cd "$(dirname "$0")"            # hardware/

# Per-kernel max AVL = static data-array element limit.
# 数组元素数（= data.S 提供的存储）。vsaxpy/vscopy/vsscal 的 data.S 实为 4096，
# 其余 TOTAL_ELEMENTS=1024。超出即越界（vsswap 4096 实测 FAIL）。
# 数组元素数（data.S 实际存储）。vsswap/vsdot 本就 4096；vmc/vvaddint32 已平铺到
# 4096。dropout 改造为干净 HDV 核（main 极简、task 落在 0x80001000、a1/a2/a3 4KB 对齐
# 不跨页）后已能随 AVL 缩放，放开到 4096。
# fdotp 已退出 sweep：它的预取对自身地址/时序病态敏感（非单调），任何描述符消费时
# 序的改动都会大幅改变其命中率；点积类由 vsdot 覆盖（vsdot 对所有改动逐位一致）。
declare -A MAXAVL=(
  [vsaxpy_hdv]=4096   [vscopy_hdv]=4096   [vsscal_hdv]=4096
  [vsswap_hdv]=4096   [vsdot_hdv]=4096    [vvaddint32_hdv]=4096
  [vmc_hdv]=4096      [dropout_hdv]=4096
)
ALL_KERNELS="vsaxpy_hdv vvaddint32_hdv vscopy_hdv vsswap_hdv vsdot_hdv vsscal_hdv vmc_hdv dropout_hdv"
DEFAULT_AVLS="8 16 32 64 128 256 512 1024 2048 4096"

# Which xrf reg holds the AVL per kernel (a0=A0, a2=A2).  Injected at RUNTIME via
# the scalar backend's +HDV_A<n> plusarg (see cva6_hdv_scalar_backend.sv), so the
# simv is NOT re-elaborated per AVL point (VCS keeps it "up to date"); only the
# first run of each kernel recompiles its address defines.
declare -A AVLREG=( [vsdot_hdv]=A2 )   # others default to A0

ARG_K="${1:-all}"
AVLS="${2:-$DEFAULT_AVLS}"
if [ "$ARG_K" = "all" ]; then KERNELS="$ALL_KERNELS"; else KERNELS="$ARG_K"; fi

OUT=avl_sweep_out
mkdir -p "$OUT"
COMBINED="$OUT/all.csv"
echo "kernel,avl,result,cycles,cyc_per_elem,eps,packets,avg_cyc_per_pkt,pf_ar,pf_hit" > "$COMBINED"

extract() {  # $1=log $2=pat -> first integer after pat
  grep -oE "$2[0-9]+" "$1" 2>/dev/null | head -1 | grep -oE '[0-9]+'
}

for k in $KERNELS; do
  max=${MAXAVL[$k]:-1024}
  csv="$OUT/${k}.csv"
  echo "avl,result,cycles,cyc_per_elem,eps,packets,avg_cyc_per_pkt,pf_ar,pf_hit" > "$csv"
  echo "==================== $k  (max AVL=$max) ===================="
  printf "%-7s %-7s %-8s %-8s %-6s %-7s %s\n" "AVL" "result" "cycles" "cyc/el" "EPs" "avg/pk" "pf_ar→hit"
  for n in $AVLS; do
    if [ "$n" -gt "$max" ]; then continue; fi
    log=/tmp/avl_${k}_${n}.log
    reg=${AVLREG[$k]:-A0}
    # +HDV_EXPECTED_EP huge: don't cap the task at the compile-time EP count;
    # let the kernel run its full AVL and `ret` naturally.
    timeout 600 make sim app="$k" hdv_plusargs="+HDV_${reg}=${n} +HDV_EXPECTED_EP=8000000" > "$log" 2>&1
    r=$(grep -E 'mock host' "$log" | head -1 | grep -oE 'PASSED|FAILED')
    [ -z "$r" ] && r="ERR"
    c=$(extract "$log" 'total_task_cycles=')
    got=$(grep -E 'mock host' "$log" | head -1 | grep -oE 'got [0-9]+' | grep -oE '[0-9]+')
    pk=$(grep "IPU-PERF] serve" "$log" | grep -oE 'packets=[0-9]+' | head -1 | grep -oE '[0-9]+')
    ac=$(grep "IPU-PERF] serve" "$log" | grep -oE 'avg_cycles_per_pkt=[0-9]+' | head -1 | grep -oE '[0-9]+')
    pfa=$(grep "PERF-ADDRGEN]" "$log" | grep -oE 'pf_ar=[0-9]+' | head -1 | grep -oE '[0-9]+')
    pfh=$(grep "PERF-ADDRGEN]" "$log" | grep -oE 'pf_hit=[0-9]+' | head -1 | grep -oE '[0-9]+')
    cpe="-"; if [ -n "$c" ]; then cpe=$(echo "scale=3; $c/$n" | bc); fi
    printf "%-7s %-7s %-8s %-8s %-6s %-7s %s\n" "$n" "$r" "${c:--}" "$cpe" "${got:--}" "${ac:--}" "${pfa:--}→${pfh:--}"
    echo "$n,$r,${c:-},$cpe,${got:-},${pk:-},${ac:-},${pfa:-},${pfh:-}" >> "$csv"
    echo "$k,$n,$r,${c:-},$cpe,${got:-},${pk:-},${ac:-},${pfa:-},${pfh:-}" >> "$COMBINED"
  done
  echo "  -> $csv"
done
echo ""
echo "combined: $COMBINED"
