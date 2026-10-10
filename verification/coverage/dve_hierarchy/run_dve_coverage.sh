#!/usr/bin/env bash
set -euo pipefail

if (( $# < 2 )); then
    printf 'Usage: bash %s OUTPUT_DIR DESIGN_VDB [TEST_VDB ...]\n       bash %s OUTPUT_DIR --inputs-file VDB_LIST\n' "$0" "$0" >&2
    exit 2
fi

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
out=$(realpath -m -- "$1")
shift
if [[ "$1" == --inputs-file ]]; then
    (( $# == 2 )) || { printf 'Expected --inputs-file FILE\n' >&2; exit 2; }
    mapfile -t input_paths < "$2"
else
    input_paths=("$@")
fi
for tool in dve xvfb-run Xvfb xauth timeout python3; do
    command -v "$tool" >/dev/null || { printf 'Missing tool: %s\n' "$tool" >&2; exit 2; }
done
duration=${DVE_COVERAGE_TIMEOUT:-180}
[[ "$duration" =~ ^[1-9][0-9]*$ ]] || { printf 'DVE_COVERAGE_TIMEOUT must be positive integer seconds\n' >&2; exit 2; }
vdbs=()
for path in "${input_paths[@]}"; do
    path=${path%$'\r'}
    [[ -z "$path" || "$path" == \#* ]] && continue
    path=$(realpath -e -- "$path")
    test -d "$path/snps/coverage/db" || { printf 'Not a VCS coverage database: %s\n' "$path" >&2; exit 2; }
    [[ "$path" == *.vdb ]] || { printf 'Database directory must end in .vdb: %s\n' "$path" >&2; exit 2; }
    [[ "$out" != "$path" && "$out" != "$path/"* ]] || { printf 'Output must not be inside an input database: %s\n' "$out" >&2; exit 2; }
    for previous in "${vdbs[@]}"; do
        [[ "$path" != "$previous" ]] || { printf 'Duplicate input database: %s\n' "$path" >&2; exit 2; }
    done
    vdbs+=("$path")
done
(( ${#vdbs[@]} > 0 )) || { printf 'No input databases\n' >&2; exit 2; }
mkdir -p -- "$(dirname -- "$out")"
# mkdir without -p claims the final directory atomically, including concurrent runs.
if ! mkdir -- "$out"; then
    printf 'Cannot create output directory; it may already exist: %s\n' "$out" >&2
    exit 2
fi
printf '%s\n' "${vdbs[@]}" > "$out/inputs.txt"
export DVE_COVERAGE_OUTPUT="$out"
unset DVE_REVIEWED_WAIVERS
waiver_status=$(python3 "$script_dir/../prepare_dve_waivers.py" --design "${vdbs[0]}" --output "$out" --mode "${DVE_WAIVERS:-auto}")
if [[ "$waiver_status" == PREPARED ]]; then
    export DVE_REVIEWED_WAIVERS="$script_dir/../dve_waivers.tcl"
fi
cd -- "$out"
status=0
# Signal the entire process group on timeout, then force termination if necessary.
timeout --kill-after=10s "${duration}s" \
    xvfb-run -a -e "$out/xvfb.log" -s '-screen 0 1280x1024x24' \
    dve -full64 -cov \
    -script "$script_dir/export_dve_coverage.tcl" > launcher.log 2>&1 || status=$?

# Fail closed: DVE can return zero while rejecting coverage data with a warning.
logs=(launcher.log)
[[ ! -f DVEfiles/dve_gui.log ]] || logs+=(DVEfiles/dve_gui.log)
diagnostic_pattern='(^|[[:space:]])(Warning|Error|Fatal)([[:space:]:-]|$)|DVE_COVERAGE_EXPORT_FAILED|Database mismatch|will not be merged|Version Check Error|(checksum mismatches|Total unmappable exclusions|Total exclusions need to review)[[:space:]]*:[[:space:]]*[1-9]'
diagnostics=0
if grep -Ein "$diagnostic_pattern" "${logs[@]}" > diagnostics.txt; then
    diagnostics=1
else
    grep_status=$?
    if (( grep_status != 1 )); then
        printf 'Cannot inspect DVE diagnostics (grep status %s)\n' "$grep_status" >&2
        diagnostics=1
    fi
fi
if (( status != 0 || diagnostics != 0 )) || [[ ! -s summary.csv.partial ]] || ! grep -qx 'DVE_COVERAGE_EXPORT_DONE' DVEfiles/dve_gui.log; then
    printf 'Export failed; inspect %s/launcher.log and DVEfiles/dve_gui.log\n' "$out" >&2
    printf 'Process exit status: %s; diagnostic matches: %s\n' "$status" "$diagnostics" >&2
    exit 1
fi
mv -- summary.csv.partial summary.csv
if [[ "$waiver_status" == PREPARED ]]; then
    grep -qx DVE_WAIVER_EXPORT_DONE DVEfiles/dve_gui.log
    test -s exclusions.el
    test -s summary_waived.csv.partial
    mv -- summary_waived.csv.partial summary_waived.csv
fi
printf 'DVE coverage summary: %s/summary.csv\n' "$out"
python3 "$script_dir/../prepare_dve_waivers.py" --design "${vdbs[0]}" --output "$out" --finalize
