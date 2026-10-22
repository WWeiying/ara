# Existing-Wave Descriptor Evidence

This supplements the immutable `first_error.json` and README. It decodes only
the previously recorded `compact.vcd`; no new simulation was run. Confucius
identified the relevant fields independently; `wave_fields.py` reproduces and
asserts the observations in `wave_fields.json`.

## Request Versus Fault Vstart

The final observed CVX exception is attempt16, but its AddrGen request begins
with **vstart=15**. The exception reports **vstart=16** after advancing within
that request. Thus the first-error ledger's vstart16 is the fault CSR, not a
claim that an additional request was issued beginning at element16.

| Recorded time (ns) | AddrGen request vstart | eew_vs2 | old_eew_vs2 | MMU virtual address |
| ---: | ---: | ---: | ---: | --- |
| 367660.5 | 15 | 3 (EW64) | 2 (EW32) | Not used as an address event in this row |
| 367664.5 | 15 | 3 (EW64) | 2 (EW32) | 0x4000a000, correct element15 |
| 367678.5 | 15 | 3 (EW64) | 2 (EW32) | 0x0000400040017000, bad element16 |

Both `idx_final_vaddr_q` and `mmu_vaddr_o` contain the bad address at 367678.5ns,
before the CVX exception response at CSV cycle367681 and the scalar mtval read.
This locates an incorrect address upstream of translation/handler checking.
These samples do not assert an MMU request handshake or the earliest-ever
appearance of a speculative/retained bad address.

Across these three samples, dispatcher `eew_q[4]=2` and `eew_q[5]=3`, while
AddrGen keeps the single request's `old_eew_vs2=2`. Its
`source_snapshot_capture`, `source_snapshot_replay_vs1`,
`source_snapshot_replay_vs2`, and `overlap_use_snapshot` are all zero. The
correct initial snapshot is therefore not evidence that this late retry is
still consuming that snapshot.

## Interpretation Boundary

Frozen M5 `addrgen.sv:296` uses `pe_req_q.old_eew_vs2` to deshuffle the entire
four-lane operand word before extracting a 64-bit index. The mixed v4/v5 EEW
records, fixed request-wide old EEW, and exactly paired bad offset strongly
support a physical-layout/descriptor mismatch when advancing from index15 to
index16. They do not independently prove the actual input operand bytes or
the first layout-changing write. Those are distinct from the now-proven
pre-MMU bad address and architectural counterexample.

`wave_fields.json` binds the decoder, compact wave, raw-wave metadata, frozen
AddrGen source, and first-error ledger by SHA256. The architectural source
oracle and original scope remain unchanged: failed first round of the pilot,
two controls NOT_RUN, no full-program or Linux acceptance.
