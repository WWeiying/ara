#!/usr/bin/env bash
# Run HDV ablation sweeps without touching the default full-run
# kernel_sweep_out directory.
set -euo pipefail
cd "$(dirname "$0")"

PARALLEL=0
MODES="${HDV_ABLATION_MODES:-base pf_only haz pf_haz}"
OUT_PREFIX="${HDV_ABLATION_OUT_PREFIX:-kernel_sweep_out_ablate}"
SIM_PREFIX_BASE="${HDV_ABLATION_SIM_PREFIX:-sim_ablate}"

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  echo "usage: $0 [--parallel] [kernel_sweep.sh args]"
  echo "       $0 --parallel --skip-long all"
  echo "       $0 --skip-long all"
  echo "       HDV_ABLATION_MODES=\"base pf_only haz pf_haz\" $0 --parallel --skip-long all"
  echo "       HDV_ABLATION_MODES=\"base pf_only haz pf_haz\" $0 --parallel point vsaxpy_hdv 1024"
  echo "default modes: base pf_only haz pf_haz"
  echo "outputs: \${HDV_ABLATION_OUT_PREFIX:-kernel_sweep_out_ablate}_<mode>"
  echo "sim dirs: \${HDV_ABLATION_SIM_PREFIX:-sim_ablate}_<mode> (or sim_mc_ablate_<mode> when mc=1)"
  echo "logs: ablation_<mode>.log in parallel mode"
  exit 0
fi

POSITIONAL=()
while [ "$#" -gt 0 ]; do
  case "$1" in
    --parallel|-j|--jobs)
      PARALLEL=1
      shift
      ;;
    *)
      POSITIONAL+=("$1")
      shift
      ;;
  esac
done
set -- "${POSITIONAL[@]}"

SWEEP_ARGS=("$@")
if [ "${#SWEEP_ARGS[@]}" -eq 0 ]; then
  SWEEP_ARGS=(--skip-long all)
fi

validate_mode() {
  local mode=$1
  case "$mode" in
    full|base|vdu|ovlp|pf|pf_only|haz|pf_haz) ;;
    *)
      echo "ERROR: invalid ablation mode '$mode' (use full|base|vdu|ovlp|pf|pf_only|haz|pf_haz)" >&2
      exit 2
      ;;
  esac
}

mode_out_dir() {
  printf '%s_%s' "$OUT_PREFIX" "$1"
}

mode_sim_dir() {
  local sim_prefix="$SIM_PREFIX_BASE"
  if [ "${mc:-0}" = "1" ]; then
    sim_prefix="sim_mc_ablate"
  fi
  printf '%s_%s' "$sim_prefix" "$1"
}

run_mode() {
  local mode=$1 out sim_out
  validate_mode "$mode"
  out=$(mode_out_dir "$mode")
  sim_out=$(mode_sim_dir "$mode")

  echo "########## HDV ablation: ${mode} -> ${out} (${sim_out}) ##########"
  HDV_ABLATION="$mode" KERNEL_SWEEP_OUT="$out" sim_dir="$sim_out" \
    ./kernel_sweep.sh "${SWEEP_ARGS[@]}"
  ./kernel_sweep_sum.sh "$out"
}

for mode in $MODES; do
  validate_mode "$mode"
done

if [ "$PARALLEL" = "1" ]; then
  pids=""
  for mode in $MODES; do
    log="ablation_${mode}.log"
    (
      echo "[start] $(date) mode=$mode"
      run_mode "$mode"
      rc=$?
      echo "[done] $(date) mode=$mode rc=$rc"
      exit "$rc"
    ) > "$log" 2>&1 &
    pids="$pids $!"
    echo "[parallel] started $mode pid=$! log=$log out=$(mode_out_dir "$mode") sim=$(mode_sim_dir "$mode")"
  done

  rc=0
  for pid in $pids; do
    if ! wait "$pid"; then
      rc=1
    fi
  done
  exit "$rc"
fi

for mode in $MODES; do
  run_mode "$mode"
done
