# Gather11 Original Trigger Mapping

2026-10-14. Read-only historical recovery review. **No exact unreturned
trigger recovered (0/11); all eleven historical stalls remain unresolved.**
This is not a DUT failure finding or acceptance. No simulation, reference,
build, RTL change, live query, or repeated singles/prefix CSV parsing occurred.
sc0/sc3 first-error work remains with Aquinas and is not re-investigated here.

## Evidence Rechecked

Started from `gather_unknown_stall_recovery01.md`,
`gather_stall_exact_trigger_review01/{REPORT.md,evidence.json}`, and the later
`gather_missing11_dump_recovery02/{REPORT.md,evidence.json}`. Rechecked **139
distinct archived input SHA256s**, the union of the exact-trigger review's
campaign-local pins and the dump review's 67 metadata pins: all match. The
read-only verification command exited 0. Read the original C and existing
R168 decoder; did not execute the decoder on invented context.

The latest dump review already inventoried 4832 filenames in the eleven
recovery roots. Its negative inventory is reused, not repeated or promoted
into a claim that no external capture exists. No newly supplied register or
memory capture is identified by these evidence records. Current RTL and
accepted-prefix scope were not re-audited for this historical-state task.

## Eleven Identities And Recoverable Boundary

`C=/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01`.
Each suffix below means `rvv_permute_restart_<suffix>`. Canonical ELF is
`C/rvv_permute_partitions01/release/binaries/<name>`; archived serial and
snapshots are `C/rvv_recovery08_<R>/terminal_scene/`. Exact ELF/report/serial
hashes remain in the hash-verified `gather_stall_exact_trigger_review01/evidence.json`.
All PCs are hexadecimal. All last printed tuples below have seed0/scalar0/mask0.

| R | Original child | Last/head PC | Last complete DETAIL VL/start | Source ordinal of that returned tuple | Global retired, unchanged in both snapshots |
| --- | --- | --- | --- | --- | --- |
| 154 | e8_m4_ops1 | 105dc/105e0 | 256/128 | 66 | 1866992662 |
| 155 | e8_m4_ops2 | 10600/10604 | 256/128 | 66 | 1743062888 |
| 168 | e8_m4_ops3 | 1063e/10642 | 256/128 | 66 | 1955925713 |
| 169 | e8_m4_ops20 | 10980/10984 | 256/128 | 66 | 1689379256 |
| 171 | e8_m8_ops1 | 105dc/105e0 | 3/1 | 49 or 50 | 1682631608 |
| 172 | e8_m8_ops2 | 10600/10604 | 3/1 | 49 or 50 | 1683445858 |
| 173 | e8_m8_ops3 | 1063e/10642 | 3/1 | 49 or 50 | 1683081790 |
| 175 | e16_m8_ops1 | 105ee/105f2 | 256/128 | 66 | 1683111710 |
| 176 | e16_m8_ops2 | 1060e/10612 | 256/128 | 66 | 1683120794 |
| 177 | e16_m8_ops3 | 1064a/1064e | 256/128 | 66 | 1685606799 |
| 178 | e16_m8_ops20 | 10994/10998 | 256/128 | 66 | 1681333534 |

Ordinal mapping assumes the original VLEN1024 capacity (512 for e8m4/e16m8,
1024 for e8m8); snapshots do not capture vlenb. **None is the recovered
stalled ordinal.** R168 alone has recorded same-batch preceding processes:
ops8, ops9, ops10, ops11, each 2688 calls/exit0, then ops3. Their genuine
ELFs and Linux batch recipe exist; their live cross-process vector state does not.

## Why Serial, PC And RNG Do Not Identify The Stall

The original C is
`C/rvv_small_gather02/rvv_small_gather_restart_e16_m1_ops0/original.c`:

- Lines 57-64 initialize xorshift13/7/17 once per seed, starting with
  `0xe736815b449aec21 ^ seed`, and derive both index arrays. No RNG advances
  per helper call. Same-seed data therefore supplies no hidden call counter.
- Lines 57 and 65-68 order the selected child's 2688 calls as seed, scalar slot,
  VL slot, mask mode, trial. Even identical vi arguments are distinct calls
  with original predecessors; duplicate starts at VL3 explain the 49/50 ambiguity.
- Lines 76-79 print pre-call TRIAL only for op0. All eleven selected ops are
  nonzero, so this localization marker is unavailable for them.
- Line 80 invokes the helper; lines 81-94 print DETAIL afterward. The first
  20-error ceiling and unfinished UART lines are neither call-boundary markers
  nor evidence that the next invocation is the stalled one. R178's extra
  complete-field but unterminated fragment remains only a returned-call error.
- Line 94 increments `cases` after full output/guard checks. That software
  counter could locate an in-helper stop, but it was not exported in snapshots.

All eleven two-snapshot intervals have unchanged scalar retirement/last/head
PC with 559824418..598691642 advancing cycles (about 11.2..12.0 seconds at
recorded 50 MHz). This is real no-retirement evidence, not merely a costly
scalar oracle. However, the global retired counter includes Linux and other
work; no per-child baseline or interrupt/context trace permits conversion
to an ordinal. Every call uses the same target PC and subsequent `csrr a0,vstart`.
An unqualified head-PC probe is not an accepted-request record. DDR idle,
old trap metadata, zero marker and zero mailbox do not supply GPRs or a VID.

Thus deterministic inputs are recoverable **given** an ordinal, but the
inverse mapping from these observations is underdetermined. No call67,
later full-VL boundary, companion op0 stop, or arbitrary short prefix is nominated.

## Exact Missing Input And Existing Recovery Entry

The most actionable existing entry is `r168_context_decoder01/decode.py`.
Its original ELF is SHA256
`a68279eaedf724eaf3efa03c71c6d039f40bc1d0c6d128b552d04e6e7ba4706b`.
It checks original caller/helper bytes and requires one authentic same-incident
context, not the existing counter snapshot:

1. Halted PC, SP, RA and s4/s7/s8/s9/a3/a4/a6/a7, tied to that ELF/run.
   Expected helper PC is 1063e or 10642, caller RA 103ce.
2. Actual little-endian bytes SP..SP+31: four 64-bit slots for mode, seed,
   cap+1, completed calls. Original count update is load/addiw/store at
   104d2/104d4/104d6; its storage slot is eight bytes, not a four-byte dump.
3. Provenance that registers and stack were captured together before reset
   or context loss. Physical RAM instead requires the captured task's SATP,
   SP and relevant page tables. Optional vlenb strengthens capacity checking.

For completed count k, the next ordinal is k+1; seed=k//896,
scalar-slot=(k%896)//112, VL-slot=(k%112)//16, mask=(k%16)//4, trial=k%4.
The decoder cross-checks these against loop registers and helper arguments.
This recovers the deterministic intra-child sequence, not physical pipeline
state or Linux context history. Never reuse R168 stack offsets on another ELF
without checking its own compiled caller layout.

Concrete external archive locator from saved launch/state metadata:
`D:\fpga_runs\ara_rvv_recovery08_20261009_168`; the other ten roots use the
same prefix and their R suffixes, as recorded in the dump-review evidence.
Request an **already saved** debugger transcript, halted context, or mapped
RAM/core attachment from those original directories. These Windows locations
were not accessed; existence of additional dumps there is unknown. Boot CPIO,
scene-preserved labels and busD debug reads are not saved process RAM.

An authentic ordinal/context would permit trigger preparation. Root-cause
proof additionally needs PC/VID-linked accepted request, architectural
VL/vstart/vtype/vm/scalar, MaskM acceptance, gather index FIFO/OOR/end tokens,
per-lane MaskB request/data handshakes, final grants and same-VID completion.
No such historical trace is present in the reviewed evidence. Full VRF is
not required merely to decode the ordinal; it cannot be inferred from RNG
for a hardware-corrupted state.

## Decision And Identity Anchors

**HOLD exact historical reproduction pending original runtime context.**
No additional test, longer arbitrary prefix, or full-child launch is proposed.
Existing numerical acceptances stay valid at their declared scopes and do not
close these eleven unknown stalls. This report creates no new PASS or common
RTL-root-cause assertion.

| Reused input | SHA256 |
| --- | --- |
| Original C | b6e5fa032dfdc58ec621d0377f93cf824f27ad460d6bd102e173e244a65ec5ca |
| exact-trigger REPORT.md | ec438e600f3d430a187b3d98263f7c7492bd98162a938b3262686edda599ac08 |
| exact-trigger evidence.json | f6f0d2b76c64e017de31bcb3d95482186ba657a89e75687c6172663a6227c0dd |
| missing11 REPORT.md | 0462adc85bd6e8d6af7e8056659770562dc72d83089b42036048946639be963c |
| missing11 evidence.json | 9623ef05b6162b8f3c102455a5d1f586a0434f804881451b9a01eb0ac7346527 |
| R168 decoder READY.json | e429fd9ea55dc67e7cfdbcc6dd723d69f3d9d07071d40e50ef510e5d8548e145 |
| R168 decode.py | 221a42416a6d255192785872584de334919a89832e872e7d80bb8368403ed9d5 |
