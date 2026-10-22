# Seed 1401 Archived Fault Analysis

Date: 2026-09-27. Scope: independent, read-only evidence investigation.
No RTL/checker changes, no VCS/Verilator/URG execution, no historical report
changes. This document is the only new artifact produced by this investigation.

## Verdict

**The 16 unknown bytes can be proved preserved using the saved traces. No new
probe is needed for this byte-preservation question. Do not clear the global
unknown mask or treat this document as a whole-case PASS.**

The bytes are `v20[byte 0..15]`. They are not X/Z in the DUT trace. The last
accepted writes before arch320 and the accepted writes during arch320 are all
known zero. There are no intervening writes to those physical locations.
An independent replay of accepted write events proves preservation of all 256
bytes, including the 128-byte EEW8-to-EEW64 reshuffle of v23.

There is also a narrower architectural proof that these 16 bytes had become
defined zero before the trap. The existing conservative unknown propagation
loses bit-level information about a predicate, and does not recover the
instruction-specific facts described below. Preservation evidence does not
depend on implementing that refinement in the checker.

## Evidence Identity

All artifact filenames below are relative to:

```
verification/out/batch-exploration-20260926-03/cases/
  load_store_slide-coverage300-seed1401-0166db9e7196/tests/
  ara_dsa_rvv1_load_store_slide_coverage300_0/
```

The actual path has no line breaks or indentation. Line numbers below are
one-based file lines, including the CSV header; Spike indices are zero-based
from ELF entry `0x80000000`.

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| input.elf | 165600 | f40ad664a3c7a8f826d52652e37d43627e2b91e64835f53e58c6b8b68f7d4087 |
| spike_commit.log | 760072 | df4b8cd31521a3c367fdb0a9c4609a827b519335e2a81ee9f59b811e85ee8c07 |
| ara_commit_trace.csv | 503076 | eb617ecbeb0297f25452f951e2250f81321919769f13d2ece1251ab83def3224 |
| ara_vector_trace.csv | 151281 | 50e7b938a8c887d4f29767b7c9a4e9e1650fbcc092c7e23b90d2064a0a51ffbe |
| trace_hart_0.log | 394944 | ea0bb1d750c3bef66ff05d425edd51ceef1d100b0833af173dc08b5f75042e8d |
| commit_comparison.json | 3149 | 01af133efe50e764e995afccdefa73fa384d05a7807d6f114cafdfda4540c5bc |
| vector_commit_comparison.json | 63937 | 92c8a0fa676a6ff0e04e493d8faf660d6c8e4d518c5a585dade85c788a65e01d |
| inputs.json | 14660 | 13a91aeea3b2c0291cbae5209c6b126cf46b759d107e062f14635b975f268d90 |

`inputs.json` records the image under
`verification/out/seed509-fix-20260926-01/sim/`; its recorded simv SHA-256 is
`1f9c4f3cf4735a503eeecc692f734fbe3ae4bd9cdee1d44f07ed1965130f6205`.
The source manifest in that directory matches the inspected probe sources:

- `hardware/tb/ara_commit_monitor.sv`:
  `38b7642703c49e31fd0493b81e948388f2dbc72f97da418f3ed76e73bd42c782`.
- `hardware/src/lane/operand_requester.sv`:
  `327291850e6d77797ab9e67c8d24dd7e8bca9019139d85518b0075fd80f5bca2`.

`operand_requester.sv:176` observes the final VRF arbitration grants, with source
order ALU=0, MFPU=1, MASKU=2, SLDU=3, VLDU=4. The monitor writes the corresponding
data/address/byte enables at `ara_commit_monitor.sv:215`. Thus these are accepted
write events, not merely offered requests. Byte enables must still be applied.

## Fault Timeline

Fault: arch320, CVA6 transaction ID 2, Spike index 799, PC `0x80000b90`, instruction
`0x2e238a07`, `vloxseg2ei8.v v20, (t2), v2`. Configuration: 4 lanes, VLEN=1024,
architectural SEW=64, LMUL=m2, VL=2, vstart=0, tu/mu. This is a **load**, not a
store. The segment micro-op's VL=1 is not architectural VL.

| Vector CSV lines | Cycles | Observation |
| --- | --- | --- |
| 2049, 2066 | 3950, 3965 | First alloc/done, vd=20, EEW=3, VL=16 |
| 2050-2065 | 3958-3964 | 16 SLDU word writes, BE=ff, 128 accepted bytes to v20 |
| 2067, 2084 | 3967, 3982 | Second alloc/done, vd=23, EEW=3, VL=16 |
| 2068-2083 | 3975-3981 | 16 SLDU word writes, BE=ff, 128 accepted bytes to v23 |
| 2085, 2090 | 3984, 3996 | Third alloc/done, load micro-op, vd=20, VL=1 |
| 2086-2089 | 3994 | Four VLDU events, **BE=00**: zero accepted bytes |

Commit CSV line 2129 starts arch320; line 2139 is its trap-marked CVX response
at cycle 3998. The three uops allocate and complete in sequence, reusing Ara
vid=0 without overlap. Total accepted byte events = distinct written bytes =
256. There is no duplicate accepted byte and no same-cycle physical-byte
collision. There is no accepted load-result byte to confuse with maintenance.

Spike log line 805 records the faulting instruction with `c8_vstart=0`, no
vector-register write, and no memory access in that commit record. RTL's textual
exception at lines 800-801 is Load Address Misaligned, tval `0x80009c7f`.

## Origin of the Unknown Mask

Initial reconstruction used these matching parser pins:

- `vector_commit.py`: `997ee3fef903892d81e0bf98933ec12a38543997736ab49d4020be727e0d965f`
- `spike_trace.py`: `a51b88decd89cffe5fe48e613c759f5d4b73974c82246242ac48940875b467f5`

The parser was edited by concurrent work during this investigation. A later
call to `audit_archived_vector_faults.py` correctly refused the changed pin;
that invocation produced no successful audit report. A subsequent parser read
had vector_commit SHA-256
`7a5d0462628dd56b37f45ce49b51167d56b04be89e0c11bd03bd5422574a3821`.
The byte replay below imports no checker/parser and is unaffected by these
changes. No pins were changed for this investigation.

| Arch | Spike index / log line | Instruction | Relevant effect |
| --- | --- | --- | --- |
| 77 | 274 / 280 | `vmorn.mm v28, v24, v31`, 0x738fae57 | VL=2 mask result; bits 0-1 known one, bits 2+ mask-tail agnostic |
| 102 | 314 / 320 | `vxor.vv v0, v4, v28`, 0x2e4e0057 | Conservative element-wide source taint marks both low 64-bit results unknown |
| 104 | 316 / 322 | `vsra.vx v20, v28, t0`, 0xa7c2ca57 | v20 bytes 0-15 first become unknown from v28 mask-tail source bits |
| 116 | 338 / 344 | `viota.m v20, v6, v0.t`, 0x50682a57 | Actual bytes 0-15 overwritten with zero; coarse predicate taint persists |
| 118 | 341 / 347 | `vredminu.vs v20, v22, v21, v0.t`, 0x116aaa57 | Element 0 overwritten with zero, element 1 preserved; coarse taint persists |

No later instruction before arch320 writes v20. The reference mask at that
point has exactly its low 128 bits set for v20, and no other unknown byte in
the 256-byte maintenance footprint. The saved audit's 240 known identity bytes
plus 16 unknown bytes is reproducible. All 256 DUT byte values are known.

### Additional Semantic Proof

This proof is local to these dynamic instructions; it is not a license to clear
unknown bits elsewhere.

1. v31 is still its defined zero initialization (Spike index 125, PC
   `0x800001e8`). Therefore the two active result bits of `vmorn.mm` at arch77
   are both one, regardless of v24. Its tail remains agnostic.
2. Before arch102, v4 is still its defined zero initialization (index 44,
   PC `0x800000a4`). XOR preserves bit independence: v0 bits 0 and 1 are both
   definitely one. Unknown high bits of the 64-bit source do not make those
   two low result bits unknown. There is no intervening v0 writer before
   arch116 or arch118.
3. v6 remains its defined zero initialization (index 50, PC `0x800000bc`).
   Both active `viota` destinations at arch116 are enabled; the prefix counts
   of the zero source mask are zero. Hence both v20 elements 0 and 1 become
   defined zero, independently of the uncertain old v20 value.
4. v21 element 0 remains its defined zero initialization (index 95,
   PC `0x80000170`). An unsigned-min reduction seeded with zero returns zero
   for every possible source value. At arch118, only destination element 0
   is the reduction result; tu preserves element 1 from arch116. Both are zero.

This also explains why blindly equating every Spike numeric value with a known
value would be wrong, while the particular 16-byte recovery here is justified.
The inspected local Spike `riscv/insns/viota_m.h` implements the masked prefix
count; `riscv/insns/vredminu_vs.h` implements unsigned minimum. The raw traces
independently show the concrete writes required by this argument.

## Direct Preservation Proof

This stronger-for-preservation argument does not need to refine the unknown
propagation at all. Track accepted physical bytes by `(addr, lane, byte)` from
the saved CSV, keeping the last writer and respecting BE.

| Bytes | Last accepted writer before arch320 | Write at arch320 | Result |
| --- | --- | --- | --- |
| v20 bytes 0-7 | line 1069, cycle 1877, arch118, source0, addr80/lane0, EEW3, BEff, data=0 | line 2050, cycle3958, same addr/lane, EEW3, BEff, data=0 | 8/8 preserved |
| v20 bytes 8-15 | line 1052, cycle1840, arch116, source2, addr80/lane1, EEW3, BEff, data=0 | line 2051, cycle3958, same addr/lane, EEW3, BEff, data=0 | 8/8 preserved |
| v20 bytes 16-127 | arch21 initialization, EEW3 | lines 2052-2065, EEW3 | 112/112 preserved |
| v23 bytes 0-127 | arch96 whole-register load, lines 925-940, EEW0 | lines 2068-2083, EEW3 | 128/128 preserved after deshuffle |

The first 16 bytes need no layout inference: both predecessor and maintenance
writes use EEW3 and the exact same physical locations. Replay of all earlier
accepted events finds no intervening writer. No reset value or unobserved SRAM
contents are assumed.

For v23, comparing the same physical slot would be incorrect: it is a real
EEW0-to-EEW3 layout conversion. With four lanes and four words per register,
the architectural offset within a 32-byte word is:

- EEW0: `4 * reverse3(byte_in_lane_word) + lane`.
- EEW3: `8 * lane + byte_in_lane_word`.

Deshuffle the complete pre-state with its old layout and the maintenance writes
with their new layout. Every byte matches. Keeping a separate concrete DUT
history for identity checking does **not** make that history a Spike oracle for
ordinary arithmetic, and does **not** clear architectural unknown bits.

## Reproduce Without Mutable Parsers

Run from the worktree root. This only reads the CSV and prints a result.

```python
import csv
import hashlib
from pathlib import Path

p = Path("verification/out/batch-exploration-20260926-03/cases/"
         "load_store_slide-coverage300-seed1401-0166db9e7196/tests/"
         "ara_dsa_rvv1_load_store_slide_coverage300_0/ara_vector_trace.csv")
assert hashlib.sha256(p.read_bytes()).hexdigest() == (
    "50e7b938a8c887d4f29767b7c9a4e9e1650fbcc092c7e23b90d2064a0a51ffbe")
with p.open() as f:
    rows = list(csv.DictReader(f))
assert rows[0]["nr_lanes"] == "4" and rows[0]["vlen_bits"] == "1024"
assert all(int(a["cycle"]) <= int(b["cycle"])
           for a, b in zip(rows, rows[1:]))

def natural(addr, lane, byte, eew):
    assert eew in (0, 3)
    offset = (int(format(byte, "03b")[::-1], 2) * 4 + lane
              if eew == 0 else lane * 8 + byte)
    return addr // 4, (addr % 4) * 32 + offset

physical, layouts, after, events = {}, {}, {}, []
for line, row in enumerate(rows, 2):
    if row["event"] != "write":
        continue
    cycle, arch, addr, lane, eew = (
        int(row[k]) for k in ("cycle", "arch_seq", "addr", "lane", "eew"))
    be = int(row["be"], 16)
    if arch == 320 and be:
        assert row["source"] == "3" and addr // 4 in (20, 23)
    if addr // 4 not in (20, 23) or cycle > 3998 or not be:
        continue
    assert cycle < 3950 or arch == 320
    if cycle < 3950:
        layouts[addr // 4] = eew
    raw = row["wdata"].rjust(16, "0")
    for byte in range(8):
        if not (be >> byte) & 1:
            continue
        value = int(raw[14 - 2 * byte:16 - 2 * byte], 16)  # Reject X/Z.
        if cycle < 3950:
            physical[(addr, lane, byte)] = (value, line, cycle, arch)
        else:
            key = natural(addr, lane, byte, eew)
            assert key not in after
            after[key] = value
            events.append(key)
before = {natural(a, l, b, layouts[a // 4]): v
          for (a, l, b), v in physical.items()}
assert layouts == {20: 3, 23: 0}
assert len(before) == len(after) == len(events) == 256
assert all(before[k][0] == v for k, v in after.items())
assert all(before[(20, b)][0] == after[(20, b)] == 0 for b in range(16))
assert {before[(20, b)][1] for b in range(8)} == {1069}
assert {before[(20, b)][1] for b in range(8, 16)} == {1052}
print("256/256 preserved; 16/16 formerly unknown preserved; no mask cleared")
```

## Closure Guidance to the Main Thread

1. Close the **arch320 maintenance-byte preservation obligation** using this
   input-bound evidence: 240 reference-known identity bytes plus 16 independently
   proved preservation bytes. Keep `pre_unknown` unchanged in general state
   propagation. Alternatively, implement separately reviewed, instruction-aware
   bit-level refinements; do not special-case a seed or whitelist unknown data.
2. A load-fault identity rule must still establish the fault boundary. Do not
   turn arbitrary partial-fault loads into identity traps. For this case, bind
   PC/encoding/index, the 3/3 uop lifetimes, first-element misalignment, all
   accepted writes and byte enables, and the saved trap CSR evidence. Source4
   rows with BE=00 are real trace rows but not four architectural writes.
3. Re-run the authorized owner-side comparison into a **new** report with pinned
   parsers and the complete stream, keeping the historical VECTOR_INCOMPLETE
   result intact. Existing reports show scalar `TERMINAL_MATCH`, 3025 matched
   instructions, 4096 signature bytes, and no vector byte mismatch; the vector
   report remains `PREFIX` with unretired request 320. Those reports alone do
   not constitute a new PASS.

### Trap CSR Boundary and Probe Scope

The saved handler actually reads and matches:

| CSR | Value | RTL commit CSV line | Spike log line |
| --- | --- | ---: | ---: |
| mcause | 4 | 2177 | 843 |
| mepc | 0x80000b90 | 2180 | 846 |
| mtval | 0x80009c7f | 2204 | 870 |

Do not claim that the archived comparison's aligned-fault entry itself records
all these values; the values above were checked in the raw saved traces.

The handler does **not** explicitly read architectural vstart before the first
signature store. Spike's fault commit records vstart=0. The first post-trap Ara
allocation (arch321, vector CSV line 2091, cycle4379, instruction 0x02828027)
also records vstart=0. This is useful downstream evidence, but it is not a
direct trap-time CSR sample. The faulting uop's own input vstart=0 is likewise
not proof of the exception output CSR.

If signoff requires a direct exception-time vstart observation, that obligation
is still separate: either close it by proving the archived image's exact
CSR-to-first-store metadata path without an intervening clear/truncation, or
add one focused non-invasive probe in an authorized later run. Do not assert
that such a direct probe was present here. The current dispatcher hash differs
from the build manifest, so current-source inspection alone cannot certify
that archived path. The manifest does match the monitor and writeback probe
sources used for the byte proof.

A minimal additional probe, if required for full exception signoff, should tag
arch320/trans_id=2 and sample exception cause/tval/vstart plus architectural
`csr_vstart_q` at the fault-response update and before arch321. Keep the existing
accepted-VRF trace and use a bounded cycle window around 3947-4379. There is no
need to recapture the 16 byte predecessors or rerun broad coverage to resolve
their preservation; those predecessors are already archived at cycles1840/1877.

Final classification: **BYTE_PRESERVATION_PROVEN_FROM_ARCHIVE; no global unknown
mask change; whole-case status intentionally not promoted.**
