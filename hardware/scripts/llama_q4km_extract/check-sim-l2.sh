#!/usr/bin/env bash
set -euo pipefail

if (( $# != 2 )); then
  echo "usage: $0 SIM_DIR ELF" >&2
  exit 2
fi

sim_dir=$1
elf=$2
readelf_bin=${READELF:-/usr/bin/readelf}
dram_base=$((0x80000000))

[[ -x ${readelf_bin} ]] || {
  echo "missing non-ZCC readelf: ${readelf_bin}" >&2
  exit 1
}
[[ -f ${elf} ]] || {
  echo "missing ELF: ${elf}" >&2
  exit 1
}

sim_l2_bytes=${LLAMA_ATTN_SIM_L2_BYTES:-}
evidence=environment_override
if [[ -z ${sim_l2_bytes} && -f ${sim_dir}/simulator.conf ]]; then
  sim_l2_bytes=$(sed -n 's/^sim_l2_bytes=//p' "${sim_dir}/simulator.conf" | tail -n 1)
  evidence=simulator_manifest
fi
if [[ -z ${sim_l2_bytes} && -f ${sim_dir}/comp.vcs.log ]]; then
  filelist=$(awk '$1 == "-f" { print $2; exit }' "${sim_dir}/comp.vcs.log")
  if [[ -n ${filelist:-} && -f ${filelist} ]]; then
    sim_l2_bytes=$(sed -n 's/^+define+SIM_L2_SIZE_BYTES=//p' "${filelist}" | head -n 1)
    if [[ -z ${sim_l2_bytes} ]]; then
      sim_l2_bytes=$((1024 * 1024))
    fi
    evidence=compile_filelist
  fi
fi
if [[ -z ${sim_l2_bytes} ]]; then
  echo "cannot determine simulator L2 capacity; set LLAMA_ATTN_SIM_L2_BYTES" >&2
  exit 1
fi
if [[ ! ${sim_l2_bytes} =~ ^[1-9][0-9]*$ ]]; then
  echo "invalid simulator L2 capacity: ${sim_l2_bytes}" >&2
  exit 1
fi

max_end=${dram_base}
load_count=0
while read -r address memory_size; do
  start=$((address))
  size=$((memory_size))
  if (( start < dram_base )); then
    echo "ELF LOAD segment starts below simulated DRAM: ${address}" >&2
    exit 1
  fi
  end=$((start + size))
  (( end > max_end )) && max_end=${end}
  ((load_count += 1))
done < <("${readelf_bin}" -lW "${elf}" | awk '$1 == "LOAD" { print $3, $6 }')

if (( load_count == 0 )); then
  echo "ELF has no LOAD segment: ${elf}" >&2
  exit 1
fi
required_bytes=$((max_end - dram_base))
if (( required_bytes > sim_l2_bytes )); then
  printf 'ELF requires %d bytes above 0x80000000, simulator provides %d bytes\n' \
    "${required_bytes}" "${sim_l2_bytes}" >&2
  exit 1
fi

printf 'sim_l2_bytes=%d\n' "${sim_l2_bytes}"
printf 'elf_l2_required_bytes=%d\n' "${required_bytes}"
printf 'sim_l2_evidence=%s\n' "${evidence}"
