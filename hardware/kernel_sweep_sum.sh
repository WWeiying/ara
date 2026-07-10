#!/usr/bin/env bash
# Rebuild kernel_sweep_out/kernel_sweep.csv from per-point sweep logs.
#
# Usage:
#   ./kernel_sweep_sum.sh [1d|blas|gemm|fixed|blas_groups|all] [csv_path]
#   ./kernel_sweep_sum.sh [--rows|--wide|--split] [1d|blas|gemm|fixed|blas_groups|all] [csv_path]
#   OUT_DIR=kernel_sweep_out_name ./kernel_sweep_sum.sh --split
#   POINT_FILTER="app:tag ..." ./kernel_sweep_sum.sh --split all
#
# Behavior:
#   - discovers every performance key appearing in selected logs;
#   - default output generates two csv files: ideal and real.
#   - --wide output keeps per-kernel rows with ideal.* and real.* columns;
#   - --rows output keeps the previous row-grouping format with run_mode/status.
#   - --split output generates two csv files: ideal and real.
#   - keeps status for each mode and falls back to NA if a key is missing.
#   - for real logs without an Ara perf report, fills total_cycles from hw-cycles.
set -uo pipefail

cd "$(dirname "$0")"
HW="$(pwd)"
OUT="${OUT_DIR:-$HW/kernel_sweep_out}"
case "$OUT" in
  /*) ;;
  *) OUT="$HW/$OUT" ;;
esac

OUTPUT_STYLE="split"
GROUP="all"
CSV=""

for arg in "$@"; do
  case "$arg" in
    --rows)
      OUTPUT_STYLE="rows"
      ;;
    --wide)
      OUTPUT_STYLE="wide"
      ;;
    --split)
      OUTPUT_STYLE="split"
      ;;
    1d|blas|gemm|fixed|blas_groups|all)
      GROUP="$arg"
      ;;
    *.csv)
      CSV="$arg"
      ;;
    *)
      # Backward-compatible positional form: first non-option arg as group, second as csv path.
      if [ -z "${GROUP_SET:-}" ] && [ "$arg" != "" ]; then
        GROUP="$arg"
        GROUP_SET=1
      fi
      ;;
  esac
done

CSV="${CSV:-$OUT/kernel_sweep.csv}"
AVLS_1D="${AVLS_1D:-32 64 128 256 512 1024 2048 4096}"
AVLS_BLAS="${AVLS_BLAS:-32 64 128}"
BLAS_LMULS="${BLAS_LMULS:-2 4 8}"
GEMM_ROWS_L="${GEMM_ROWS_L:-1 2 4}"
BLAS_GROUP_N="${BLAS_GROUP_N:-128}"
BLAS_GROUPS="${BLAS_GROUPS:-2 4 8}"
BLAS_GROUP_LMULS="${BLAS_GROUP_LMULS:-4}"

gen_points() {
  local g=$1 k a L r n groups
  if [ "$g" = 1d ] || [ "$g" = all ]; then
    for k in ${KERNELS_1D:-vsaxpy vscopy vsswap vsdot vsscal vvaddint32 vmc vsdwt vstencil3 vfir5}; do
      for a in $AVLS_1D; do echo "${k}_asm|avl${a}|$a|||"; done
    done
  fi
  if [ "$g" = blas ] || [ "$g" = all ]; then
    for k in ${KERNELS_BLAS:-vssymv vsgemv vssyrk vstrsm}; do
      echo "${k}_asm|m1|32|1||"
      for L in $BLAS_LMULS; do
        for a in $AVLS_BLAS; do echo "${k}_asm|m${L}_avl${a}|$a|$L||"; done
      done
    done
    for a in 32 64 128; do echo "vsger_asm|n${a}|$a|||"; done
  fi
  if [ "$g" = gemm ] || [ "$g" = all ]; then
    for r in $GEMM_ROWS_L; do echo "vsgemm_asm|m1_${r}row|32|1|$r|"; done
    echo "vsgemm_asm|m1_4row_n64|64|1|4|"
    echo "vsgemm_asm|m1_4row_n128|128|1|4|"
    for r in $GEMM_ROWS_L; do
      for a in $AVLS_BLAS; do echo "vsgemm_asm|m4_${r}row_avl${a}|$a|4|$r|"; done
    done
  fi
  if [ "$g" = fixed ] || [ "$g" = all ]; then
    echo "vsspmv_asm|fixed32|1024|||"
    echo "fconv2d_asm|r64_c32_f3|2048|||"
    echo "jacobi2d_asm|r128_c64|8192|||"
    echo "lavamd_asm|npar256|256|||"
    echo "softmax_asm|ch3_inner256|768|||"
  fi
  if [ "$g" = blas_groups ] || [ "$g" = all ]; then
    for k in ${KERNELS_BLAS_GROUPS:-vsgemv vssymv}; do
      for L in $BLAS_GROUP_LMULS; do
        for n in $BLAS_GROUP_N; do
          for groups in $BLAS_GROUPS; do
            echo "${k}_asm|m${L}_n${n}_g${groups}|$n|$L|$groups|"
          done
        done
      done
    done
  fi
}

discover_log_points() {
  local base stem app tag

  find "$OUT" -maxdepth 1 -type f \( -name '*__real.log' -o -name '*__ideal.log' \) -printf '%f\n' \
    | sort -u \
    | while IFS= read -r base; do
        case "$base" in
          *__real.log)
            stem="${base%__real.log}"
            ;;
          *__ideal.log)
            stem="${base%__ideal.log}"
            ;;
          *)
            continue
            ;;
        esac

        app="${stem%%__*}"
        tag="${stem#*__}"
        if [ -z "$app" ] || [ -z "$tag" ] || [ "$app" = "$stem" ]; then
          continue
        fi
        case "$app" in
          fconv2d|jacobi2d|lavamd|softmax)
            continue
            ;;
        esac
        case "${app}|${tag}" in
          fconv2d_asm\|hdv_*|jacobi2d_asm\|hdv_*|lavamd_asm\|hdv_*|softmax_asm\|hdv_*)
            continue
            ;;
        esac

        printf '%s|%s||||\n' "$app" "$tag"
      done
}

word_has() {
  local needle="$1" word
  shift
  for word in "$@"; do
    [ "$word" = "$needle" ] && return 0
  done
  return 1
}

point_selected() {
  local app="$1" tag="$2" point

  if [ -n "${POINT_FILTER:-}" ]; then
    for point in $POINT_FILTER; do
      case "$point" in
        "$app:$tag"|"$app|$tag") return 0 ;;
      esac
    done
    return 1
  fi

  if [ -n "${APP_FILTER:-}" ] && ! word_has "$app" $APP_FILTER; then
    return 1
  fi
  if [ -n "${TAG_FILTER:-}" ] && ! word_has "$tag" $TAG_FILTER; then
    return 1
  fi
  return 0
}

trim() {
  local s="$1"
  s="${s#"${s%%[![:space:]]*}"}"
  s="${s%"${s##*[![:space:]]}"}"
  printf '%s' "$s"
}

has_timeout() {
  grep -Eq "SIM_TIMEOUT|LOG_LIMIT|TIMEOUT/FAIL|a_invalid_instruction_fetch|Fatal:" "$1" 2>/dev/null
}

has_build_fail() {
  grep -qF "BUILD_FAIL" "$1" 2>/dev/null
}

status_for_log() {
  local log="$1"
  if [ ! -f "$log" ]; then
    echo "NO_LOG"
  elif has_build_fail "$log"; then
    echo "BUILD_FAIL"
  elif has_timeout "$log"; then
    echo "TIMEOUT"
  else
    echo "OK"
  fi
}

csv_escape() {
  local val="$1"
  if [[ "$val" == *$','* || "$val" == *$'"'* || "$val" == *$'\n'* || "$val" == *$'\r'* || "$val" == *$'\t'* ]]; then
    val="${val//\"/\"\"}"
    printf '"%s"' "$val"
  else
    printf '%s' "$val"
  fi
}

declare -A IDEAL_VALS REAL_VALS
declare -A IDEAL_STATUS REAL_STATUS
declare -A ALL_KEYS

collect_metrics() {
  local mode=$1
  local log="$2"
  local app=$3
  local tag=$4
  local line body key val

  if [ "$mode" = ideal ]; then
    IDEAL_STATUS["$app|$tag"]="$(status_for_log "$log")"
  else
    REAL_STATUS["$app|$tag"]="$(status_for_log "$log")"
  fi

  [ ! -f "$log" ] && return
  [ ! -r "$log" ] && return

  while IFS= read -r line; do
    if [[ "$line" == "[PERF]"* && "$line" == *":"* ]]; then
      body="${line#\\[PERF\\] }"
      body="${body#\[*\]}"  # drop leading token if malformed spacing is inconsistent
      key="${body%%:*}"
      val="${body#*:}"
      key="$(trim "$key")"
      val="$(trim "$val")"
    elif [[ "$line" == "["*"]:"* ]]; then
      key="${line%%]:*}"
      key="${key:1}"
      val="${line#*]:}"
      key="$(trim "$key")"
      val="$(trim "$val")"
    else
      continue
    fi

    if [[ -z "$key" || "$val" == "" ]]; then
      continue
    fi
    if [[ "$key" == *"===="* ]]; then
      continue
    fi

    if [ "$mode" = ideal ]; then
      IDEAL_VALS["$app|$tag|$key"]="$val"
    else
      REAL_VALS["$app|$tag|$key"]="$val"
    fi
    ALL_KEYS["$mode:$key"]=1
  done < "$log"
}

if [ ! -d "$OUT" ]; then
  echo "error: missing output directory: $OUT" >&2
  exit 1
fi

# Collect points for selected group.  In all mode, include every log already
# present in kernel_sweep_out so ad-hoc benchmark points are summarized too.
declare -a GEN_POINTS=()
declare -a LOG_POINTS=()
declare -a POINTS=()
declare -A POINT_SEEN

mapfile -t GEN_POINTS < <(gen_points "$GROUP")
if [ "$GROUP" = all ]; then
  mapfile -t LOG_POINTS < <(discover_log_points)
fi

for p in "${GEN_POINTS[@]}" "${LOG_POINTS[@]}"; do
  IFS='|' read -r app tag _ <<<"$p"
  [ -z "$app" ] && continue
  [ -z "$tag" ] && continue
  if ! point_selected "$app" "$tag"; then
    continue
  fi
  if [ -n "${POINT_SEEN["$app|$tag"]:-}" ]; then
    continue
  fi
  POINT_SEEN["$app|$tag"]=1
  POINTS+=("$p")
done
unset POINT_SEEN

if [ "${#POINTS[@]}" -eq 0 ]; then
  echo "error: no points selected for group=$GROUP" >&2
  exit 1
fi

for p in "${POINTS[@]}"; do
  IFS='|' read -r app tag avl bl gr _ <<<"$p"
  [ -z "$app" ] && continue
  collect_metrics ideal "$OUT/${app}__${tag}__ideal.log" "$app" "$tag"
  collect_metrics real "$OUT/${app}__${tag}__real.log" "$app" "$tag"
done

# Some benchmark-wrapper real logs only print bracket counters such as
# [hw-cycles] and [sw-cycles], and do not emit a perf_report_* block with
# [PERF] total_cycles.  Keep the raw hw-cycles column and also expose it under
# total_cycles so real tables have a comparable cycle column for these points.
for p in "${POINTS[@]}"; do
  IFS='|' read -r app tag _ <<<"$p"
  [ -z "$app" ] && continue
  if [ -z "${REAL_VALS["$app|$tag|total_cycles"]:-}" ] && \
     [ -n "${REAL_VALS["$app|$tag|hw-cycles"]:-}" ]; then
    REAL_VALS["$app|$tag|total_cycles"]="${REAL_VALS["$app|$tag|hw-cycles"]}"
    ALL_KEYS["real:total_cycles"]=1
  fi
done

declare -a IDEAL_KEYS=() REAL_KEYS=()
for k in "${!ALL_KEYS[@]}"; do
  if [[ $k == ideal:* ]]; then
    IDEAL_KEYS+=("${k#ideal:}")
  else
    REAL_KEYS+=("${k#real:}")
  fi
done

trim_keyset() {
  local k=$1
  k="${k#"${k%%[![:space:]]*}"}"
  k="${k%"${k##*[![:space:]]}"}"
  printf '%s' "$k"
}

declare -a IDEAL_KEYS_CLEAN=()
declare -a REAL_KEYS_CLEAN=()
for k in "${IDEAL_KEYS[@]}"; do
  k="$(trim_keyset "$k")"
  [ -z "$k" ] && continue
  IDEAL_KEYS_CLEAN+=("$k")
done

for k in "${REAL_KEYS[@]}"; do
  k="$(trim_keyset "$k")"
  [ -z "$k" ] && continue
  REAL_KEYS_CLEAN+=("$k")
done

IDEAL_KEYS=("${IDEAL_KEYS_CLEAN[@]}")
REAL_KEYS=("${REAL_KEYS_CLEAN[@]}")
unset IDEAL_KEYS_CLEAN REAL_KEYS_CLEAN

mapfile -t IDEAL_KEYS < <(printf '%s\n' "${IDEAL_KEYS[@]}" | sort -u)
mapfile -t REAL_KEYS < <(printf '%s\n' "${REAL_KEYS[@]}" | sort -u)

declare -A KEY_UNION
for k in "${IDEAL_KEYS[@]}" "${REAL_KEYS[@]}"; do
  [ -n "$k" ] && KEY_UNION["$k"]=1
done
unset ALL_KEYS
declare -a ALL_KEYS=()
mapfile -t ALL_KEYS < <(printf '%s\n' "${!KEY_UNION[@]}" | sort -u)
unset KEY_UNION

emit_mode_rows() {
  local mode=$1
  shift
  local keys=("$@")
  local avl bl gr status k

  for p in "${POINTS[@]}"; do
    IFS='|' read -r app tag avl bl gr _ <<<"$p"
    [ -z "$app" ] && continue

    if [ "$mode" = "ideal" ]; then
      status="${IDEAL_STATUS["$app|$tag"]:-NO_LOG}"
    else
      status="${REAL_STATUS["$app|$tag"]:-NO_LOG}"
    fi

    printf "%s,%s,%s,%s,%s,%s,%s" \
      "$(csv_escape "$app")" \
      "$(csv_escape "$tag")" \
      "$(csv_escape "$avl")" \
      "$(csv_escape "$bl")" \
      "$(csv_escape "$gr")" \
      "$(csv_escape "$mode")" \
      "$(csv_escape "$status")"

    if [ "$mode" = "ideal" ]; then
      for k in "${keys[@]}"; do
        printf ",%s" "$(csv_escape "${IDEAL_VALS["$app|$tag|$k"]:-NA}")"
      done
    else
      for k in "${keys[@]}"; do
        printf ",%s" "$(csv_escape "${REAL_VALS["$app|$tag|$k"]:-NA}")"
      done
    fi

    printf "\n"
  done
}

emit_mode_csv() {
  local output_csv="$1"
  local mode="$2"
  shift 2
  local -a keys=("$@")

  local avl bl gr status k

  mkdir -p "$(dirname "$output_csv")"
  {
    printf "kernel,tag,avl,blas_lmul,gemm_rows,status"
    for k in "${keys[@]}"; do
      printf ",\"%s\"" "$k"
    done
    printf "\n"

    for p in "${POINTS[@]}"; do
      IFS='|' read -r app tag avl bl gr _ <<<"$p"
      [ -z "$app" ] && continue

      if [ "$mode" = "ideal" ]; then
        status="${IDEAL_STATUS["$app|$tag"]:-NO_LOG}"
      else
        status="${REAL_STATUS["$app|$tag"]:-NO_LOG}"
      fi

      printf "%s,%s,%s,%s,%s,%s" \
        "$(csv_escape "$app")" \
        "$(csv_escape "$tag")" \
        "$(csv_escape "$avl")" \
        "$(csv_escape "$bl")" \
        "$(csv_escape "$gr")" \
        "$(csv_escape "$status")"

      if [ "$mode" = "ideal" ]; then
        for k in "${keys[@]}"; do
          printf ",%s" "$(csv_escape "${IDEAL_VALS["$app|$tag|$k"]:-NA}")"
        done
      else
        for k in "${keys[@]}"; do
          printf ",%s" "$(csv_escape "${REAL_VALS["$app|$tag|$k"]:-NA}")"
        done
      fi
      printf "\n"
    done
  } > "${output_csv}.tmp"
  mv "${output_csv}.tmp" "$output_csv"
}

tmp="${CSV}.tmp"
mkdir -p "$(dirname "$CSV")"
if [ "$OUTPUT_STYLE" = "split" ]; then
  ideal_csv="${CSV%.csv}_ideal.csv"
  real_csv="${CSV%.csv}_real.csv"
  emit_mode_csv "$ideal_csv" ideal "${IDEAL_KEYS[@]}"
  emit_mode_csv "$real_csv" real "${REAL_KEYS[@]}"
  echo "wrote $ideal_csv and $real_csv"
else
  {
    if [ "$OUTPUT_STYLE" = "rows" ]; then
      printf "kernel,tag,avl,blas_lmul,gemm_rows,run_mode,status"
      for k in "${ALL_KEYS[@]}"; do
        printf ",\"%s\"" "$k"
      done
      printf "\n"

      emit_mode_rows ideal "${ALL_KEYS[@]}"
      emit_mode_rows real "${ALL_KEYS[@]}"
    else
      printf "kernel,tag,avl,blas_lmul,gemm_rows"
      printf ",ideal_status"
      for k in "${IDEAL_KEYS[@]}"; do
        printf ",\"ideal.%s\"" "$k"
      done
      printf ",real_status"
      for k in "${REAL_KEYS[@]}"; do
        printf ",\"real.%s\"" "$k"
      done
      printf "\n"

      for p in "${POINTS[@]}"; do
        IFS='|' read -r app tag avl bl gr _ <<<"$p"
        [ -z "$app" ] && continue
        printf "%s,%s,%s,%s,%s" \
          "$(csv_escape "$app")" \
          "$(csv_escape "$tag")" \
          "$(csv_escape "$avl")" \
          "$(csv_escape "$bl")" \
          "$(csv_escape "$gr")"

        printf ",%s" "$(csv_escape "${IDEAL_STATUS["$app|$tag"]:-NO_LOG}")"
        for k in "${IDEAL_KEYS[@]}"; do
          printf ",%s" "$(csv_escape "${IDEAL_VALS["$app|$tag|$k"]:-NA}")"
        done

        printf ",%s" "$(csv_escape "${REAL_STATUS["$app|$tag"]:-NO_LOG}")"
        for k in "${REAL_KEYS[@]}"; do
          printf ",%s" "$(csv_escape "${REAL_VALS["$app|$tag|$k"]:-NA}")"
        done
        printf "\n"
      done
    fi
  } > "$tmp"

  mv "$tmp" "$CSV"
  echo "wrote $CSV"
fi
