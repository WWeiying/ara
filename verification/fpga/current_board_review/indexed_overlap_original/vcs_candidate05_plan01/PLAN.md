# M5 Indexed Overlap Plan

Preparation only. No DUT, build, retry, source adaptation or RTL changes.
Only final reference03 is accepted; reference02's unaligned opcode read was a
fixture bug, not a DUT finding. The worker imports existing M5 image/runner,
private-copy, resource and abort-publication helpers without changing them.

## Scope And Budget

1. Pilot `d32m2_i64_fault_ov1`, full 50 rounds, jobs1, 4200s ceiling.
2. Only after its raw/CSV oracle passes: resident ov1 (2400s) and fault ov0
   (4200s), jobs2, full 50 rounds each. Resident retains its 51st masked helper.

Fault reference cost is 1595309 retired instructions, resident 840319. At the
reported 723 retired/s this estimates 2207s and 1162s, not a timing guarantee.
The common worker deadline is 8800s, regardless of remaining per-case budget;
it latches cancellation during simulation or checking and prevents the next
stage from starting. The direct systemd service ceiling is 9600s (2h40), leaving
800s for teardown. No partial scope can PASS. No automatic retry or timeout change.
Cap24 and MemAvailable>=32GiB are checked before admission. Reservations mean
only additional unused external slots; already live workers are counted once.
Do not reserve historical terminal services. Parent sets any future reservation.

## Independent Oracle

The actual SoC ELF, nm map, disassembly, load segments and unchanged 41 original
helper encodings are checked. All source/reference/raw Host/Spike/image/manifest
and checker inputs are hashed. Every retirement must have a pinned PC/opcode.
RVFI scalar memory accesses validate register-derived addresses, width/mask and
store values; unknown bytes cannot stand for zero.

Each helper's arguments, initialized inputs, original prologue and returned VL
are checked. Every post has 72 real check() calls, actual output/index/guard
loads and 39 result stores. Fault programs require 50 successful target retires,
1600 cause13 handlers, 32 starts0..31 per round, all CSR/record values, actual
old-PTE read0, correct PTE store, fence/SFENCE, real MRET and next accepted retry.
CVX requests/responses are paired by active transaction generation; their PC0
and result fields are NOT invented cause/PC evidence. Pure vector CSR reads are
allowed in the scalar handler, but vector data/configuration/reloads are not.
Fault mepc and scalar context are preserved; syscalls return to their original
ecall PC+4 (except original exit to M). No 1650-target-retirement requirement.

Final actual scalar reads cover all32768 backing words and all1536 PTE words.
Full firmware check totals are21595/5215; round/maps/unmaps/minor/original faults,
error/exit/magic, raw VECTOR_PASS and INDEXED_ORIGINAL_PASS and original CTRL0
store/parking are independent gates. No store-only shadow claim of unmodified
vector memory. Linux historical150 faults and this fixture1600 are distinct.

## Bounded Probe

Pilot uses existing image UCLI and +ARA_DEBUG_SOURCE_SNAPSHOT. `capture.tcl`
selects dispatcher, four lane snapshot/requester, AddrGen/MMU and actual VLDU
grant signals, not full SoC. Hard window start through1000000ns, then dump off
and all remaining rounds execute. Frozen M5 ClockPeriod=1ns; acceptance requires
first full checkpoint before cycle950000 and a closed nonempty FSDB. This covers
all first-round32 faults including starts1..5 if the gate passes. If incomplete,
report NOT_PASS/probe incomplete; no repeat or widened capture automatically.
Signal availability is statically checked against frozen source, not claimed
as a measured elaborated probe until authorized execution. Raw wave semantics
remain available for offline review; CSV alone does not prove partial VRF timing.

## Commands

Run host tests before sealing, then prepare using explicit M5 image:

```sh
python3 -B test_host.py --report host_final.json
python3 -B worker.py prepare --reference ../reference03 \
  --image /home/wangwy/fpga_runs/current_board_memory_candidate05/campaign/image \
  --out prepared01 --unused-reserved-slots 0
```

The new plan emits a `service_command.NOT_EXECUTED.json`. Parent reviews its
hash and explicitly authorizes that direct-worker command; preparation never
calls systemd-run. Worker checks its actual MainPID/cgroup using a trusted
explicit user-bus environment. Unreadable bus/resource state fails closed.
Terminal evidence contains exact raw CSV/privateELF/input/command/log/analysis
hashes, runner COMPLETE/exact membership and sticky-noabort. Service GC defaults
are never substituted for observed historical exit status.
